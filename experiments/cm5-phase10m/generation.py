"""Private local sealed-generation policy; no upstream use or auto-acceptance."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'experiments/cm5-phase10l'))
import lab_profile as original_profile

GOLDEN_SHA = 'e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87'
FSW_SHA = 'b0b4dd5af15b4cbfd8005da10551cf4dc9f9ce45166299c4996d238a5362fbc3'
USER_BYTES = 15634268160
MODE = 'verified-fsw-partition'
ELF_PATH = '/opt/fsw/RpiDeployment.elf'
SCHEMA = 'cm5-phase10m-sealed-generation-v1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def regular(path, readonly=False):
    path = Path(path)
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
        raise ValueError('Require unaliased regular file: '+str(path))
    if readonly and s.st_mode & 0o222:
        raise ValueError('Sealed artifact must have no write permission: '+str(path))
    return path


def file_sha(path):
    regular(path)
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def artifact(g, key):
    name = g['artifacts'][key]['name']
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
        raise ValueError('Artifact must be a generation-local basename')
    return Path(g['_directory'])/name


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def load(path, expected_sha, verify_image=True):
    path = regular(Path(path), readonly=True)
    data = path.read_bytes()
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha or '') or sha(data) != expected_sha:
        raise ValueError('Explicit generation manifest SHA256 mismatch')
    g = json.loads(data)
    payload = dict(g); claimed = payload.pop('generation_id')
    if g['schema'] != SCHEMA or sha(canonical(payload)) != claimed:
        raise ValueError('Invalid sealed generation identity/schema')
    if g['original_golden']['sha256'] != GOLDEN_SHA or g['installed_elf']['sha256'] != FSW_SHA:
        raise ValueError('Unexpected golden/approved ELF identity')
    if g['kernel_sha256'] != original_profile.KERNEL_SHA or g['execution_mode'] != MODE:
        raise ValueError('Unexpected generation kernel/execution policy')
    required = dict(format=1,algorithm='sha256',data_block_size=4096,hash_block_size=4096,
                    data_blocks=131072,hash_start_block=1,fec_roots=2,fec_start=0,fec_blocks=132105)
    if any(g['verification'].get(k) != v for k,v in required.items()):
        raise ValueError('Unexpected FSW verification geometry')
    if g['artifacts']['image']['bytes'] != USER_BYTES or g['boot_profile'] != 'operational':
        raise ValueError('Unexpected sealed image size/profile')
    g['_directory'] = str(path.parent.resolve())
    g['_manifest_sha256'] = expected_sha
    for key, meta in g['artifacts'].items():
        p = regular(artifact(g, key), readonly=True)
        if p.stat().st_size != meta['bytes'] or ((key != 'image' or verify_image) and file_sha(p) != meta['sha256']):
            raise ValueError('Generation artifact mismatch: '+key)
    return g


def construct_initramfs(original, fsw_root):
    if not re.fullmatch(r'[0-9a-f]{64}', fsw_root):
        raise ValueError('FSW root must be a SHA256 hex digest')
    base = original_profile.construct(original)
    pin = 'etc/cm5-verity/fsw.roothash'
    roots = [b for n, b in original_profile.cpio_entries(original) if n == pin]
    if len(roots) != 1:
        raise ValueError('Original FSW pin is not unique')
    body = fsw_root.encode()+(b'\n' if roots[0].endswith(b'\n') else b'')
    extra = original_profile.newc(pin, body, 920001, 0o100600)
    extra += original_profile.newc('TRAILER!!!', b'', 0)
    result = base+bytes(-len(base) % 4)+extra
    original_profile.initramfs(result)
    return result


def approve(original, candidate, g, kernel_sha):
    if kernel_sha != original_profile.KERNEL_SHA or candidate != construct_initramfs(original, g['fsw_root']):
        raise ValueError('Not the exact sealed-generation initramfs/kernel')
    if sha(candidate) != g['artifacts']['initramfs']['sha256']:
        raise ValueError('Mixed initramfs generation')
    roots = dict(original_profile.cpio_entries(original))
    if (g['expected_tables']['os_table'][11] != roots['etc/cm5-verity/os.roothash'].decode().strip() or
            g['expected_tables']['fsw_table'][11] != g['fsw_root']):
        raise ValueError('Expected tables do not match the trusted root pins')
    return dict(profile='operational', policy='phase10m-exact-sealed-root-v1',
                generation_id=g['generation_id'], manifest_sha256=g['_manifest_sha256'],
                original_initramfs_sha256=original_profile.ORIGINAL_SHA,
                effective_initramfs_sha256=sha(candidate), fsw_root=g['fsw_root'],
                original_boot_acceptance_preserved=True,
                derivative_matches_original_boot_manifest=False)


def canonical_table(table):
    parts = table.split()
    if len(parts) < 16 or parts[2] != 'verity':
        raise ValueError('Incomplete verity table')
    parts[4:6] = ['DATA_DEVICE', 'HASH_DEVICE']
    parts[parts.index('use_fec_from_device')+1] = 'FEC_DEVICE'
    return parts


def maps_match(record, g):
    try:
        return all(canonical_table(record[k]) == g['expected_tables'][k] and
                   record[k.replace('table', 'status')].endswith('verity V')
                   for k in ('os_table', 'fsw_table'))
    except (KeyError, ValueError, IndexError):
        return False
