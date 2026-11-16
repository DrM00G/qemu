# Phase 10E native RP1 laboratory

AI-assisted local experiments, not for upstream contribution under QEMU's
code-provenance policy. Commands run on local WSL in `/home/aweso/projects/qemu`.
They write only local source/build files, ignored evidence and disposable regular
media outside the checkout. No physical CM5, host block device, golden/boot-file
write, root/hash/parity replacement or EEPROM operation occurs.

## Build and focused tests

Choose fresh output IDs each time. The configured build and private captured
inputs from prior phases are reused; no production kernel/module rebuild occurs.

```sh
ninja -C build-arm64-phase1 -j 8 qemu-system-aarch64 qemu-img qemu-io \
 tests/qtest/cm5io-test tests/qtest/rp1-test tests/qtest/bcm2712-mip-test \
 tests/qtest/bcm2712-sdhci-test tests/qtest/qos-test
mkdir -p experiments/cm5-phase10e/artifacts/qtests-repro01/images
export QTEST_QEMU_BINARY="$PWD/build-arm64-phase1/qemu-system-aarch64"
export CM5_PHASE8_IMAGE_DIR="$PWD/experiments/cm5-phase10e/artifacts/qtests-repro01/images"
for name in cm5io rp1 bcm2712-mip bcm2712-sdhci; do
 build-arm64-phase1/tests/qtest/$name-test \
  > experiments/cm5-phase10e/artifacts/qtests-repro01/$name.log 2>&1
done
python3 -m unittest discover -s experiments/cm5-phase10e -v
python3 -m unittest discover -s experiments/cm5-phase10a -v
python3 -m unittest discover -s experiments/cm5-phase10d -v
python3 experiments/cm5-phase10a/matrix.py \
 --output experiments/cm5-phase10e/artifacts/synthetic-repro01
```

cm5io tests include native link/reset, secondary bus numbers, missing BDFs,
BAR0/1/2 sizing/relocation, bridge decode, 32/64-bit CPU apertures, window ends,
SSI-origin MSI-X masking/pending/rearm, bus-master disable, MIP masks, wrong MSI
addresses, other-host isolation, translated RAM writes, disabled inbound decode,
and clock/PLL/gate/reset behavior. RP1/MIP/SDHCI fallback tests remain.

## Original physical kernel, original initramfs, clean golden overlay

```sh
python3 experiments/cm5-phase10c/run.py --native-rp1-test --recovery-case clean \
 --dma --batch --profile native --debug-shell --poweroff-after-validation \
 --timeout 420 --output experiments/cm5-phase10e/artifacts/native-repro01
python3 experiments/cm5-phase10e/report.py \
 --run experiments/cm5-phase10e/artifacts/native-repro01 \
 --output experiments/cm5-phase10e/artifacts/report-repro01
```

`--recovery-case clean` reuses only Phase 10D's no-fault overlay/persistence
checks. This does not run its corruption matrix. Every invocation makes a new
QCOW2 under `~/cm5-v8-lab/phase10c/OUTPUT_BASENAME`, with the unchanged golden raw
backing. The original full verified OS scan remains. Captured roots2, original
initramfs/module, verified OS/FSW, systemd, two multi-user observations, LOGS
persistence and normal shutdown are checked. Header debug UART remains an
explicit PL011 substitute. All trace bytes are the synthetic SPI fixture data.

The observer runs through stock systemd's debug UART. It mmap-reads chip ID,
checks Linux PCI resource sizes, and writes/restores the first/last four bytes
of modeled BAR2 scratch RAM. It loads original captured OS `spi-dw-mmio` and
`spidev` modules. `driver_override` attaches the spidev *protocol* driver to the
explicit synthetic slave; it does not bypass a failed controller/MFD/clock probe.
A bounded child uses original OS Python ioctl calls, with DMA absent and the
real controller's PIO/interrupt path. The runner never replaces kernel/initramfs
or modifies the captured root filesystem.

The current SPI workload uses mode0/eight bits at **10 kHz**, three repetitions
of 4/64/65/128/257/4096 bytes. Every received byte must equal MOSI XOR0xa5. IRQ
counts must increase on the actual RP1 SPI interrupt and multi-user must remain
active. `report.py` additionally matches each CS-delimited trace segment to the
submitted message's length and both hashes; correct bytes alone do not pass.
The CS traces are logical framing evidence, not electrical pin waveforms.
Use `--native-spi-hz 100000` or `--native-spi-hz 1000000` to repeat
the retained higher-rate limitations on fresh runs. Earlier 1 MHz/100 kHz evidence is retained; do not use its coarse byte/IRQ-only
native status as a claim of complete CS framing. The strict report is authoritative.
`guest-observer.py`, when present, is the exact public code submitted in RAM;
old source hash inventories taken after execution are labeled accordingly.

One targeted 6.18.62/GPEX clean regression, without injecting corruption:

```sh
python3 experiments/cm5-phase10a/controls.py --cases clean \
 --output experiments/cm5-phase10e/artifacts/gpex-repro01
```

The earlier complete Phase 9/10D fault results are preserved, not represented as
rerun here. No additional full FEC campaign is requested or scheduled.

## Native implementation boundary

Domain0002 at0x1000120000 has an actual QEMU PCI root port and RP1 secondary
endpoint at bus1/dev0/function0. Domain0001 is separate and has no endpoint.
Logical training requires a connected endpoint, programmed reference clock,
bridge/PERST release, no forced reset, no secondary-bus reset and Link Disable
clear. Completion uses a 1ms virtual timer, a lab convention rather than PHY
measurement. Config goes through the +0x9000 index/+0x8000 data interface and
normal PCI bridge bus-number semantics. RP1 contains device-relative registers;
Linux PCI config assigns its BAR addresses.

Outbound window registers decode four CPU base/limit and PCI-base descriptors
inside the measured platform apertures, forwarding to PCI-core bridge/BAR
memory. Inbound descriptors decode supported nonlinear size values and UBUS
remaps into actual RAM or the connected controller's MIP doorbell. DMA is not
an identity alias. RAM is bounded by modeled installed RAM, even though the
physical DT describes a larger potential RAM aperture. The physical self/peer
PCI peripheral DMA alias is omitted/unsupported to avoid recursive I/O. Other
host MIPs and non-RAM/non-MIP CPU addresses are rejected. PCI bus-master gating
is retained. Only the outbound forwarding region is marked reentrancy-safe for
legitimate synchronous CPU->SSI->MSI transactions; inbound targets cannot recurse
back through that aperture.

MSI-X remains RP1's table/PBA/vector mechanism; MIP independently decodes the
translated address/data into its configured edge IRQ. Pending masked MSI-X is
replayed by PCI core on unmask. RP1's level-source ACK rearms delivery. MIP
unsupported level/VPU behavior is unchanged; no internal generic MSI bypass is
used. No native hotplug, peer DMA, autonomous LTSSM, ATS or migration claim.

The native RP1 clock subset supports SYS/SLOW mux/divider/gate state plus three
PLL register banks, with derived lock and read-only parent status. It feeds the
DW serializer's logical input frequency. Boot presets (50MHz xosc, SYS200MHz)
are explicit lab initialization, not RP1 firmware execution or a captured register
dump. Other clock-manager registers remain unimplemented/logged. The real
clk-rp1 driver registers the provider; only this SPI/SYS path is exercised.

SPI0 is deliberately enabled in the generated *lab* DT; it was disabled in the
captured live tree. Logical wires connect a synthetic SSI slave. GPIO/pinctrl,
SPI DMA and general RP1 subdevices remain unimplemented. No physical connector,
signal-integrity, throughput or timing equivalence is established.

[STATUS.md](STATUS.md) identifies observed results and retained failures.
[PHASE10F-BOOT-HANDOFF.md](PHASE10F-BOOT-HANDOFF.md) describes the separate bounded
BOOT-reader integration required before selected virtual BOOT bytes can replace
pristine host boot inputs.
