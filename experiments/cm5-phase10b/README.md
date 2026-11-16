# Phase 10B: captured physical kernel and native PCIe probe groundwork

AI-assisted **local experiments only**, not for upstream contribution under
`docs/devel/code-provenance.rst`. No physical devices, EEPROM, original kernel,
initramfs, golden user area, root hashes, trees or parity are changed.

The default `cm5io-dev` GPEX path remains available. Opt-in `native-pcie=on`
requires `native-mip=on` and substitutes two BCM2712 **probe-only frontends**
at the physical controller register addresses. This is not a functioning
native PCIe host implementation and has no downstream RP1 endpoint. Its PHY,
link training, address translation, configuration transactions and interrupt
delivery remain unsupported. Unsupported MDIO is visible as a real driver
timeout, not hidden with a successful completion flag.

RP1 on the GPEX path now has a 64 KiB BAR2 scratchpad. PCI configuration assigns
its address normally; no physical guest-assigned BAR address is hardcoded into
the endpoint. Byte/word/dword accesses, bounds, relocation, decode disable and
zero-on-reset are tested. Zero-on-reset is an explicit lab policy, not an
observed silicon reset guarantee. Mailboxes, shared-memory ownership, RP1
firmware, atomics/coherency and SRAM aliases are not emulated. The device remains
unmigratable; no migration compatibility is claimed.

## Reproduce

From `/home/aweso/projects/qemu`; choose fresh output names on every invocation.
Python 3.11+, `zstd`, the existing cross compiler/build prerequisites, private
assets and Phase 9 staging dependencies are needed. No filesystem mounting is
performed. Disk writes go to fresh qcow2 files in `~/cm5-v8-lab/phase10b/` or
the established Phase 9 lab. The asset audit writes generated virtual DTBs to
that private lab and records only selected derived properties in the checkout.

```sh
ninja -C build-arm64-phase1 -j 8 qemu-system-aarch64 \
  tests/qtest/rp1-test tests/qtest/cm5io-test \
  tests/qtest/bcm2712-mip-test tests/qtest/bcm2712-sdhci-test

mkdir -p experiments/cm5-phase10b/artifacts/qtests-repro01/images
export QTEST_QEMU_BINARY="$PWD/build-arm64-phase1/qemu-system-aarch64"
export CM5_PHASE8_IMAGE_DIR="$PWD/experiments/cm5-phase10b/artifacts/qtests-repro01/images"
for name in rp1 cm5io bcm2712-mip bcm2712-sdhci; do
  "build-arm64-phase1/tests/qtest/$name-test" \
    > "experiments/cm5-phase10b/artifacts/qtests-repro01/$name.log" 2>&1
done

python3 -m unittest discover -s experiments/cm5-phase10a -v
python3 experiments/cm5-phase10a/matrix.py \
  --output experiments/cm5-phase10b/artifacts/phase10a-synthetic-repro01
python3 experiments/cm5-phase10b/audit.py \
  --output experiments/cm5-phase10b/artifacts/asset-audit-repro01

# Exact physical kernel and matching initramfs, generated virtual DT, GPEX:
python3 experiments/cm5-phase10b/smoke.py --profile gpex --timeout 120 \
  --output experiments/cm5-phase10b/artifacts/physical-gpex-repro01

# Same unmodified physical assets; native driver reaches MDIO boundary:
python3 experiments/cm5-phase10b/smoke.py --profile native --timeout 900 \
  --output experiments/cm5-phase10b/artifacts/physical-native-repro01

python3 experiments/cm5-phase10a/controls.py \
  --output experiments/cm5-phase10b/artifacts/phase9-controls-repro01
```

The smoke driver uses only the captured physical `kernel_2712.img` and
`initramfs_2712-osverified-v8`, not the differently built Windows unified
kernel or the 6.18.62 development kernel. It retains the captured root/verity
command line, adding only UART console/earlycon/verbose logging arguments.
It records input identities, exact QEMU command, serial/hardware logs, timeout,
process return code, milestones and post-run input/overlay identities. A killed
timeout is not a successful boot or a demonstrated permanent hang. A script
exit of zero means evidence collection finished: inspect `result.json`.

The first two captured runs predate adding executable identity and PID fields
to the smoke script. Their QEMU executable hash at launch was not recorded;
the final evidence manifest labels the current compiled binary hash separately.
Their full physical-asset/golden identities were captured before and after.
For the native run, `running-executable.json` separately fingerprints its
actual executable inode through `/proc/PID/exe` while it was still running.

## DT and probe contract

Passing the captured live/base DTB unchanged would advertise unimplemented
firmware clocks, reset controllers, power domains, pin controllers, native
PCIe, DMA and RP1 peripherals. `cm5io-dev` still rejects external `-dtb` and
firmware. **No external DTB relaxation was needed to enter the actual kernel**:
its real eMMC driver probes against the existing machine-generated tree.
The opt-in native nodes are added to that generated tree. `dumpdtb` exports
the machine tree for comparison, not a hash of the ARM loader's final tree
after `/chosen`, PSCI, initrd and seed fixups.

The physical eMMC node's parent range translates to `0x1000fff000`, with cfg
at `0x1000fff400`, SPI 273, 8-bit width and `sw_sdio`. Those addresses and IRQ
match the generated node. Firmware clocking and HS400/ADMA64/CQE16 do not:
the lab uses a fixed clock and the existing PIO-only SDHCI wrapper. The
disabled secondary 4-bit MMC node is not used as the main controller.

Native controller addresses are `0x1000110000` (expansion, domain 1, x1) and
`0x1000120000` (RP1, domain 2, x4), register aperture `0x9310`. The disabled
third controller is absent. INTx DT assignments are SPI 219–222 and 229–232;
controller/MSI IRQ descriptors are SPI 223/224 and 233/234. External MIP
phandles are published, matching the physical external-MIP topology, but no
native PCIe interrupt transaction has been implemented or tested. Existing
GPEX-to-MIP tests exercise the fallback, not the new frontend.

The native tree uses explicit lab fixed clocks and the driver's optional-reset
MMIO fallback rather than inventing firmware reset providers. Memory-window
descriptors are reduced to lab apertures/RAM, and are **storage-only register
latches**, not functional inbound/outbound translation. Root-complex mode is
reported; PHYLINKUP and DL_ACTIVE remain zero. There is no root-port config
space, PCI bus hierarchy or downstream RP1 in native mode, and its RP1 DT
children are omitted. Native mode cannot accept fallback PCI devices.

The implemented register contract follows the available pinned 6.18.62
Raspberry Pi `drivers/pci/controller/pcie-brcmstb.c` (BCM2712/7712 offsets).
It is not represented as the exact physical kernel's source. The captured
6.18.50 executable's actual MMIO trace corroborates the exercised setup path:
bridge init, SCB, window descriptors, RC mode, and MDIO. MDIO address is at
`+0x1100`, write data at `+0x1104`, read data at `+0x1108`; the write to PHY
register `0x1f` with `0x1600` remains busy. Its driver returns `-ETIMEDOUT`
before host enumeration or MSI setup. This is the deliberate unsupported
boundary, not a claimed hardware failure.

## Verification interpretation

The initramfs is concatenated newc plus a zstd-compressed newc payload; `file`
alone describes only its first archive. The audit parses both without mounting
or extracting paths. It finds the actual matching `updates/dm-verity.ko`, its
vermagic and FEC symbols. The guest logs its out-of-tree module load. Stock
`CONFIG_DM_VERITY_FEC` being unset therefore does not establish missing FEC.
Conversely, module presence/load alone does not prove a successful correction.

The original `scripts/local-top/cm5-fsw-verity` uses captured RECOVERY metadata,
requests roots2 on both mappings, and performs forty 256 MiB verified OS reads
before root mount. No scan bypass, module replacement, or parity regeneration
is applied. A timeout while this path is running leaves root/functional
survival unvalidated. Host process IO counters, when sampled, are labeled as
host counters and do not identify guest sectors or prove the exact blocked
instruction. No physical timing or FEC-delay claim follows from them.

See [STATUS.md](STATUS.md) for actual completed results and residual blockers.
