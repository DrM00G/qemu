#!/usr/bin/env python3
"""Precisely constructed local initramfs derivative; never upstream content."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'experiments/cm5-phase10c'))
from diagnostic import newc
sys.path.insert(0, str(ROOT/'experiments/cm5-phase10f'))
from validate import initramfs
sys.path.insert(0, str(ROOT/'experiments/cm5-phase10b'))
from audit import cpio_entries

ORIGINAL_SHA = 'fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b'
KERNEL_SHA = '154f0ea1e14bb1075077dfd1bdc63c1502bc0b17b0354628d515b4fbd3a4198d'
HOOK = 'scripts/local-top/cm5-fsw-verity'
PARAMETER = 'cm5_lab_os_scan=operational'

CONTROL = '''CM5_LAB_OS_SCAN=strict
CM5_LAB_SCAN_SEEN=0
for CM5_LAB_ARG in $(cat /proc/cmdline); do
    case "$CM5_LAB_ARG" in
        cm5_lab_os_scan=*)
            [ "$CM5_LAB_SCAN_SEEN" = 0 ] || os_fail 'Duplicate lab OS scan parameter'
            CM5_LAB_SCAN_SEEN=1
            CM5_LAB_OS_SCAN=${CM5_LAB_ARG#cm5_lab_os_scan=}
            case "$CM5_LAB_OS_SCAN" in
                strict|operational) ;;
                *) os_fail 'Invalid lab OS scan profile' ;;
            esac
            ;;
    esac
done
printf '%s\\n' "$CM5_LAB_OS_SCAN" > /run/cm5-phase10l-profile || os_fail 'Cannot record lab scan profile'
if [ "$CM5_LAB_OS_SCAN" = strict ]; then
'''
SKIP = '''else
    os_log '[4/6] PHASE10L_OPERATIONAL: exhaustive OS scan NOT performed; on-demand verity/FEC retained'
fi
'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def patch_hook(body):
    """Keep mapper creation, table checks, status check and handoff verbatim."""
    text = body.decode('ascii')
    begin = "os_log '[4/6] Full 10 GiB verified read (first-boot assurance; 40 x 256 MiB)'\n"
    end = 'STATUS="$(dmsetup status cm5_os_verified)"'
    passed = "os_log '[5/6] Verified OS full read PASS; mapper will remain active'"
    if any(text.count(x) != 1 for x in (begin, end, passed)):
        raise ValueError('Unexpected captured scan structure')
    a, b = text.index(begin), text.index(end)
    block = text[a:b]
    if not all(x in block for x in ('while [ "$I" -lt 40 ]', 'bs=4194304', 'count=64', 'os_fail')):
        raise ValueError('Unexpected full scan implementation')
    result = text[:a]+CONTROL+block+SKIP+text[b:]
    result = result.replace(passed, 'if [ "$CM5_LAB_OS_SCAN" = strict ]; then\n'+passed+
        "\nelse\n    os_log '[5/6] OS verity status valid; exhaustive scan not requested (operational)'\nfi")
    return result.encode('ascii')


def construct(original):
    if sha(original) != ORIGINAL_SHA:
        raise ValueError('Not the pinned independently accepted V8 initramfs')
    initramfs(original)
    hooks = [b for n, b in cpio_entries(original) if n == HOOK]
    if len(hooks) != 1:
        raise ValueError('Expected one original verity hook')
    replacement = patch_hook(hooks[0])
    # Linux supports concatenated initramfs archives. Preserve the original
    # byte prefix in full; the sole later entry overrides this one existing
    # script. Uncompressed newc makes the derivative byte reproducible without
    # a compressor version dependency. No root hashes/metadata are regenerated.
    extra = newc(HOOK, replacement, 910001)+newc('TRAILER!!!', b'', 0)
    derived = original+bytes(-len(original) % 4)+extra
    initramfs(derived)
    return derived


def approve(original, candidate, kernel_sha):
    if kernel_sha != KERNEL_SHA:
        raise ValueError('Operational profile refuses a changed V8 kernel')
    expected = construct(original)
    if candidate != expected:
        raise ValueError('Initramfs is not the precisely constructed operational derivative')
    return dict(profile='operational', policy='phase10l-exact-construction-v1',
                original_initramfs_sha256=ORIGINAL_SHA, effective_initramfs_sha256=sha(candidate),
                kernel_sha256=KERNEL_SHA, cmdline_parameter=PARAMETER,
                original_boot_acceptance_preserved=True,
                derivative_matches_original_boot_manifest=False,
                change='One later newc entry overrides only '+HOOK,
                builder_sha256=sha(Path(__file__).read_bytes()))


def regular_bytes(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('Require a regular file, no symlink or block device')
    return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='fresh private directory')
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT):
        parser.error('output must be outside checkout')
    os.umask(0o077)
    original = regular_bytes(args.original)
    derived = construct(original)
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    target = args.output/'initramfs-operational'
    with target.open('xb') as stream:
        stream.write(derived)
    target.chmod(0o400)
    policy = approve(original, regular_bytes(target), KERNEL_SHA)
    policy.update(source=str(args.original.resolve()), artifact=str(target.resolve()),
                  original_bytes=len(original), effective_bytes=len(derived))
    (args.output/'provenance.json').write_text(json.dumps(policy, indent=2)+'\n')
    print(json.dumps(policy, indent=2))


if __name__ == '__main__':
    main()
