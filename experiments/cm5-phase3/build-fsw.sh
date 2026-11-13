#!/usr/bin/env bash
# Synthetic local research software, not real FSW and not an upstream patch.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
output=${PHASE3_FSW_OUTPUT:-$here/artifacts/prototype-build}
mkdir -p "$output"
aarch64-linux-gnu-gcc -O2 -Wall -Wextra -Werror -fPIC -shared \
    -Wl,-z,max-page-size=65536 "$here/flightmath.c" -o "$output/libflightmath.so"
aarch64-linux-gnu-gcc -O2 -Wall -Wextra -Werror -fPIE -pie \
    -Wl,-z,max-page-size=65536 "$here/prototype.c" -ldl -o "$output/prototype-fsw"
aarch64-linux-gnu-readelf -lW "$output/prototype-fsw" > "$output/program-headers.txt"
aarch64-linux-gnu-readelf --version-info "$output/prototype-fsw" > "$output/library-versions.txt"
file "$output/prototype-fsw" "$output/libflightmath.so"
sha256sum "$output/prototype-fsw" "$output/libflightmath.so" > "$output/SHA256SUMS"
