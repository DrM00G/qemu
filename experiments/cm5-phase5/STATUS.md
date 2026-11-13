# Hardware implementation status

Local research fork, AI-assisted, not intended for upstream contribution.
Physical timing/electrical equivalence has not been validated.

| Subsystem | Status | Verified scope |
| --- | --- | --- |
| RP1 PCIe enumeration/configuration | IMPLEMENTED_AND_GUEST_VALIDATED | 1de4:0001 revision 2, BAR assignment and real RP1 driver binding |
| BAR1 decode and SYSINFO | IMPLEMENTED_AND_GUEST_VALIDATED | C0 chip/platform ID and SPI0 aperture |
| MSI-X and RP1 interrupt domain | IMPLEMENTED_AND_GUEST_VALIDATED | 61 vectors advertised; actual SPI0 IRQ 19 through real Linux domain |
| DW SPI0 full-duplex 8-bit PIO | IMPLEMENTED_AND_GUEST_VALIDATED | 72 ioctl messages, 5,448 frames; real spidev and DW driver |
| Deterministic SSI slave | IMPLEMENTED_AND_GUEST_VALIDATED | TX XOR 0xa5; configurable echo used by V8 diagnostic |
| Mode/clock register configuration | IMPLEMENTED_AND_GUEST_VALIDATED | Linux modes 0–3 at 100 kHz, 1 MHz, 5 MHz; no physical edge validation |
| TX/RX FIFO normal behavior | IMPLEMENTED_AND_GUEST_VALIDATED | 64-entry experimental synthesis, including transfers larger than FIFO |
| 4/16/32-bit frame masking, transmit-only | IMPLEMENTED_QTEST_ONLY | qtest coverage; Linux guest exercised 8-bit full duplex |
| CS0 selection | IMPLEMENTED_AND_GUEST_VALIDATED | Native SER and SSI CS GPIO; logical transfer activity traced |
| Other CS lines / error and reset cases | IMPLEMENTED_QTEST_ONLY | CS1 isolation, TX/RX overflow, RX underflow, clearing, disable flush, pending-timer reset, zero baud divisor |
| Full RP1 PCI configuration and internal interrupt block | PARTIALLY_IMPLEMENTED | Tested SPI level/IACK path, not every physical capability or edge source |
| RP1 clock/reset/pinmux controllers | NOT_IMPLEMENTED | Fixed-clock experimental DT and direct SSI wiring instead |
| Receive-only / EEPROM / multi-I/O / DMA | NOT_IMPLEMENTED | Unsupported configurations do not fabricate successful transfers |
| Other RP1 peripherals, shared SRAM/BAR2 | NOT_IMPLEMENTED | No Ethernet/USB/UART/I2C/GPIO/PIO/SDIO models in this endpoint |
| Linux timeout/recovery under injected hardware hang | NOT_IMPLEMENTED | Zero-baud non-progress is qtested; no guest timeout test claim |
| Migration/savevm | NOT_IMPLEMENTED | Device explicitly unmigratable |
| BCM2712 / cm5-dev machine | NOT_IMPLEMENTED | Evaluated below; virt remains the provisional host |

## Evidence

Artifacts are retained under `experiments/cm5-phase5/artifacts/` and excluded
from source control. Actual new C sources are under `hw/` and `tests/qtest/`.

* `device-help.txt`: QEMU exposes `rp1-pci` and `ssi-test-slave`.
* `build-validation-final.log`: final controller/endpoint/qtest build.
* `qtest.log`: five tests pass on the final binary.
* `stage-a.serial.log`: first genuine guest enumeration. Linux assigned BAR1
  at `0x10000000` and BAR0 at `0x10400000`, enabled PCI, read the expected chip
  ID, then failed probe with `failed to find RP1 DT node`, error -22. The earlier
  BAR0 prototype was 64 KiB; final BAR0 is 16 KiB, corroborated by physical logs.
  The failed probe is retained as evidence, not counted as driver compatibility.
* `spi-driver.serial.log`: DT probe succeeds, but the initial disposable init
  omitted `/proc` and `/sys` mountpoints. SPI protocol binding therefore failed.
* `spi-driver-v2.serial.log`: corrected mountpoints; first full 72-message pass.
* `spi-verified.serial.log` and `spi-verified.unimplemented.log`: final guest
  matrix and actual hardware trace. `spi-verified.command.json` records invocation.
* `validation.json`: independent correlation of all bytes plus input/source hashes.
* `v8-rp1/`: retained launch failure from invalid `-nic ...,addr=7` syntax.
* `v8-rp1-v2/`: full V8 boot and original diagnostic passed; SPI hook failed
  because sysfs had already moved under `/newroot/sys`. No controller bypass
  or driver patch was used to correct it.
* `v8-rp1-v3/`: corrected binding path; full V8 and existing SPI diagnostic pass.
* `v8-verified/`: final-binary rerun, with `command.json`, `inputs.json`, serial
  log, QEMU peripheral trace, network evidence, fresh overlay and result JSON.
* `checkpatch-final.log`: zero errors with `--no-signoff`, one MAINTAINERS warning.
  This is an unsigned local experiment, not an upstream patch submission.

The original kernel identifies itself as `6.18.62-cm5-surrogate-16k`. Matching
installed modules and public Raspberry Pi sources are in
`~/cm5-phase3-kernel/`; the source directory is
`linux-62a56e350fcfd1c5e204c62dac4ea4ee205eb24e`.
`CONFIG_MFD_RP1=y`, `CONFIG_SPI_DESIGNWARE=m`, `CONFIG_SPI_DW_MMIO=m`,
`CONFIG_SPI_SPIDEV=m`, PCI MSI and GICv3 ITS were already enabled.
No original kernel, module, golden disk or Phase 4 source was modified.

## Concrete transfer evidence

The guest uses a real devtmpfs character device, major 153:

```text
../../../../../bus/pci/drivers/rp1
SPI_DEVICE=/sys/bus/spi/devices/spi0.0
crw------- ... 153, 0 /dev/spidev0.0
SPI_IOC_MESSAGE(1) mode=0 hz=100000 len=4 TX=10203040
SPI_RESULT ret=4 errno=0 RX=b58595e5
SPI_INVALID_BPW ret=-1 errno=22
SPI_DIAGNOSTIC=PASS failures=0
```

Corresponding QEMU peripheral activity:

```text
dw_apb_ssi_cs selected=0x1
dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x00000010 rx=0x000000b5
dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x00000020 rx=0x00000085
dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x00000030 rx=0x00000095
dw_apb_ssi_transfer cs=0x1 bits=8 tx=0x00000040 rx=0x000000e5
dw_apb_ssi_cs selected=0x0
rp1_msix vector=19
```

These trace lines show the transferred words; native CS can also deassert
between FIFO refills. The complete trace, rather than this excerpt, records
all CS transitions. Final standalone guest IRQ 19 recorded actual interrupts
through `rp1_irq_chip`, with GIC error counter zero.

The existing Phase 4 diagnostic is intentionally unchanged. In the V8 run
`xor-mask=0` configures the hardware-side SSI fixture to return the transmitted
bytes, satisfying its existing loopback contract:

```text
V8_RP1_SPI_DIAGNOSTIC_EXIT=0
{"test":"spi_loopback","status":"PASS","errno":0,"bytes":4,...}
V8_DIAGNOSTIC_EXIT=0
V8_TARGET=active
```

The SPI hook runs after mounting V8's actual root and executes the diagnostic
with its native dynamic loader. Systemd then boots that same root normally.
UART, network and storage remain the Phase 4 generic virt regression paths;
those are not counted as newly implemented RP1 peripherals.

## Register contract and fidelity limits

The Linux `spi-dw.h` register offsets are used without translation. SPI0 is
BAR1 + `0x50000`, and RP1 interrupt configuration is BAR1 + `0x108000`.
SPI IRQ is vector 19; the driver requires exactly `RP1_INT_END=61` MSI-X vectors.
The model provides that driver-required subset, not an asserted physical count.

| Register/region | Implemented behavior |
| --- | --- |
| CTRLR0 `0x00` | DFS32 at bits 20:16, mode bits 7:6, standard SPI, full-duplex/transmit-only, internal loopback |
| CTRLR1 `0x04` | 16-bit storage, not an automatic RX/EEPROM engine |
| SSIENR `0x08` | Enable bit; disable cancels transfer and flushes FIFOs/errors |
| SER `0x10` | Four native select bits; actual SSI CS GPIOs select attached slaves |
| BAUDR `0x14` | Even 16-bit divisor; zero stalls transfer progression |
| TXFTLR/RXFTLR `0x18/1c` | Six implemented bits for the experimental 64-entry synthesis |
| TXFLR/RXFLR `0x20/24` | Actual queued word counts |
| SR `0x28` | Busy, TX space/empty, RX nonempty/full derived from actual state |
| IMR/ISR/RISR `0x2c/30/34` | Masked/raw FIFO threshold and latched FIFO errors |
| TXOICR/RXOICR/RXUICR/ICR | Read-to-clear supported sticky errors; level threshold causes remain level-driven |
| IDR / VERSION `0x58/5c` | Experimental ID 0, documented v4.02a ASCII component version `0x3430322a` |
| DR `0x60..ec` | Aliases of FIFO data port, 32-bit MMIO accesses |
| RX_SAMPLE_DLY `0xf0` | Stored field, no electrical sample-point behavior |
| PCIE_APBS `+0x8+4*n` | ENABLE/IACK_EN, IACK and TEST subset, SET `+0x800` / CLR `+0xc00` |
| PCIE_APBS `+0x108/10c` | Internal active IRQ bitmap |

The experimentally selected reset image is CTRLR0 `7<<16`, IMR `0x3f`, other
stored implemented registers zero, empty FIFOs, disabled SSI and inactive CS.
Status then reads `0x6`. Tests distinguish fixed/read-only component identity,
disabled/empty state and this model's chosen configurable reset image.
**The whole image is not claimed to match RP1 silicon reset values.** FIFO
64, IDR 0, fixed 200 MHz clock, table/PBA placement in BAR0 at `0/0x1000`, PCIe
capability offsets and the absence of optional capabilities are experimental
choices or simplifications. BAR0/1 sizes are corroborated by the physical
boot logs linked in README; the complete physical PCI configuration is unverified.

IRQ generation includes level acknowledgement/retrigger and QEMU MSI-X vector
masking/PBA. Only the SPI level path is guest validated. Every other source,
concurrency case and edge-triggered interrupt behavior remains unvalidated.
Raw TX-empty is gated by SSI enable in this subset. Timer scheduling approximates
frame duration with divisor, word size and fixed input clock. It does not model
wire edges, setup/hold, pinmux, board wiring, physical maximum throughput, DMA,
clock gating or PCIe transport latency. CPOL/CPHA are configuration bits, not
physical waveforms.

Unimplemented BAR1 accesses read zero and are logged; unsupported DW writes
are logged. Missing read-only/controller registers generally read zero.
Unsupported automatic receive/EEPROM/multi-I/O modes do not progress. Software
using them may time out; this is not evidence that those features work. The
current milestone establishes the specified full-duplex programmed-I/O path.

## Machine evaluation and next hardware work

A new name wrapping `virt` would add no BCM2712 compatibility, so no `cm5-dev`
machine was introduced. Cortex-A76 CPUs are available, but RAM topology, PCI
host, GICv3/ITS, PL011 console, RTC, timers, virtio storage/network, PSCI boot and
the base DT remain generic. None is claimed as BCM2712-specific here.

The next integration work should make PCI-associated DT resource relocation
robust, model the RP1 clock/reset and pinmux blocks from authoritative register
specifications, and verify a physical RP1 PCI config/reset dump. Then add the
BCM2712 host bridge, interrupt and boot topology before introducing a CM5 machine.
SPI receive-only/EEPROM modes, controlled guest timeout/recovery tests, and
physical waveform comparison are further steps. Storage-corruption sweeps and
FEC redesign were not part of this hardware implementation.
