#!/bin/sh
# Local-only wrapper: compile existing established libfdt, outside checkout.
set -eu
src=${CM5_DTC_SOURCE:-/home/aweso/cm5-phase3-kernel/linux-62a56e350fcfd1c5e204c62dac4ea4ee205eb24e/scripts/dtc/libfdt}
out=${CM5_DTC_TOOLS:-/tmp/cm5-phase10f2-tools}
umask 077
mkdir -p "$out"
python3 - "$src" <<'PYVERIFY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
references = pathlib.Path('experiments/cm5-phase10f2/references.json')
for name, digest in json.loads(references.read_text())['libfdt']['local_source_hashes'].items():
    if hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
        raise SystemExit('pinned libfdt source mismatch: '+name)
PYVERIFY
cc -shared -fPIC -O2 -I "$src" "$src"/*.c -o "$out/libfdt.so"
