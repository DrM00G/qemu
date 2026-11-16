# Phase 10F.2: boot-policy proxy and DT evidence

AI-assisted **local experiments only**, not for QEMU upstream contribution.
Read [STATUS.md](STATUS.md) for executed results and [NEXT-SESSION.md](NEXT-SESSION.md)
for private inputs and continuation. Preserve all earlier evidence. No physical
media, EEPROM/OTP/RPMB, production images or captured files are written.

`0xf14` remains an **UNCONFIRMED physical EEPROM fixture**. This software proxy
reads rightmost nibble first: USB-MSD, SD/eMMC, restart. `None` means explicit
operator-declared absence; it performs no USB probing. Only that absence permits
fallback. A present source's partition, filesystem, config, read, file or digest
error stops selection. Unknown firmware fallback is never guessed. Restart is
bounded to 0..3 additional cycles, a laboratory budget without physical timing.

Each present source needs its own independently accepted filename/digest map.
Missing manifests stop before logical reads. Wrong/stale manifests and changed
selected bytes fail integrity. Active source aliases, including hardlinks and
an active source reused as another source's backing node, are rejected. Shared
immutable backing data is allowed; each selection opens a separately locked,
read-only graph, validates its regular-file chain, and verifies it unchanged.
The shared Phase 10F reader retains its limits and prelaunch integrity gate.
This assumes a cooperative host/exclusive ownership of disposable media; it does
not protect against hostile concurrent mutation of host files.

Selection statuses are distinct from guest outcomes. The runner wraps a policy
stop as `BOOT_SELECTION_STOPPED`, `process.launched=false`. No original host
kernel/initrd fallback occurs. `BOUNDED_RESTART` is a policy result; it is not a
kernel, guest verity or userspace failure. Per-source trace classifications are
`DEVICE_UNAVAILABLE`, `MISSING_ACCEPTANCE_MANIFEST`, `UNREADABLE_MEDIA`,
`INVALID_PARTITION_OR_FILESYSTEM`, `UNSUPPORTED_FIRMWARE_BEHAVIOR`,
`SELECTED_FILE_FAILURE`, `INVALID_CONFIGURATION`, and `SELECTED`.

## Reproduce with fresh names

Run from the repository root. Build with modest parallelism:

```sh
ninja -C build-arm64-phase1 -j 2 qemu-system-aarch64 \
 tests/qtest/rp1-test tests/qtest/cm5io-test \
 tests/qtest/bcm2712-mip-test tests/qtest/bcm2712-sdhci-test
sh experiments/cm5-phase10f2/build-dt-tools.sh
CM5_BOOT_READER=qemu-io python3 -m unittest discover -s experiments/cm5-phase10f2 -v
```

`build-dt-tools.sh` verifies pinned libfdt source hashes before compilation.
`toolchain.json` pins the local accepted libfdt/dtc/fdtoverlay executables.
A compiler/tool change requires explicit review and renewed acceptance, not an
automatic hash refresh. Existing pinned libfdt emits two const-qualifier warnings.
Its ABI predates `fdt_check_full`: the wrapper uses the shared full Python DT
structure validator and `fdt_check_header`, with explicit ctypes signatures,
owned writable buffers, immediate copies of borrowed pointers, bounded lengths
and checked return codes. Fixups must identify unique aligned property words.

Hardware qtests need `QTEST_QEMU_BINARY` set to the absolute executable. SDHCI
also requires `CM5_PHASE8_IMAGE_DIR` pointing to a fresh private scratch directory.
Omitting it aborts before hardware execution. All artifacts use fresh names.

The exact fresh full-guest command is in the current evidence directory's
`v8-command.json`. It uses the existing Phase 10C runner with:

```text
--control-pipes --dma --batch --profile native
--boot-selection-policy eeprom-fixture-0xf14
--boot-config-profile cm5-headless-lab
--boot-overlay PRIVATE_FRESH_GOLDEN_BACKED_QCOW2
--boot-expected /home/aweso/cm5-v8-lab/phase10f2/accepted-01/accepted-hashes.json
--debug-shell --poweroff-after-validation --recovery-case clean
--native-rp1-test --native-spi-hz 10000 --timeout 600 --output FRESH_OUTPUT
```

Only a disposable active QCOW2 is writable. The exported kernel and initramfs
are exact selected bytes from that image. `emmc-only` remains available. The
independent Phase 10E report checks all messages and CS boundaries; the Phase
10F.1 evaluator checks selected-byte/argv/runtime provenance and persistence.

`synthetic_usb.py --work PRIVATE_FRESH --output FRESH_JSON` executes distinct
USB-selected ARM64 fixture bytes. It is a non-Linux PSCI/UART smoke program,
not a USB hardware boot. The modeled storage remains eMMC; the USB policy label
selects the payload only. No USB enumeration or initramfs execution is claimed.

## Device Tree scope

`reference_audit.py` reads the selected physical tree, map and accepted overlays
from an active read-only QCOW2. `dwc2,dr_mode=host` and `nospi10` can be applied
independently to that physical reference. Each operation retains source hashes,
parameters, required symbols, normalized before/after DTS diff and output hash
privately. Skipping unsupported earlier operations cannot establish a complete
firmware-equivalent tree. Dormant graphics fragments, arbitrary overrides,
audio semantics and discovery remain unsupported.

The runtime board explicitly rejects `-dtb` (`hw/arm/cm5io-dev.c`). The physical
USB, graphics and SoC SPI10 declarations do not describe modeled lab hardware.
They must not be injected. The generated tree explicitly enables independent
RP1 SPI0 and its synthetic slave. `runtime_compat.py` compares every observed
runtime node/property hash against the selected physical reference and records
an exact structural compatibility diff. The guest observer records the actual
runtime FDT hash and property inventory. The comparison requires an independent
`--expected-runtime-sha256` acceptance value, rather than inferring runtime identity
from a host-generated candidate.

The tested minimal `nospi10` runtime slice verifies the correct lab board,
absence of physical SPI10 and enabled native RP1 SPI0, then makes **no change**.
This is a validated absence substitution, not an installed transformation.
Unexpected physical SPI10, wrong board, disabled/incompatible RP1 SPI and output
hash mismatch fail closed. USB/graphics/audio retain explicit lab substitutions.
An installed runtime transform needs a separate opt-in board loader design,
compatible binding validation and another full guest gate; none is claimed here.

Evidence levels remain separate: source inspection, host units, hardware qtest,
synthetic guest, actual original-kernel guest, and actual modeled peripheral
function. No EEPROM instructions, secure boot, tryboot, proprietary firmware
choices, electrical USB/SPI behavior or physical timing are established.
