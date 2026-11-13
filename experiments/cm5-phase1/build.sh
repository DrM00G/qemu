#!/usr/bin/env bash
# Local research experiment; not intended for upstream QEMU contribution.
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$repo/build-arm64-phase1"
cd "$repo/build-arm64-phase1"
if [[ ! -f build.ninja ]]; then
    "$repo/configure" --target-list=aarch64-softmmu --disable-docs \
        --disable-gtk --disable-sdl --disable-vnc --disable-werror --enable-slirp
fi
ninja -j "${JOBS:-4}" qemu-system-aarch64 qemu-img
