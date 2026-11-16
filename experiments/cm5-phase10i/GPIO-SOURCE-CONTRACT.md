# Bounded RP1 GPIO contract

Local AI-assisted experiment, not upstream-eligible. Source references:
[pinned Linux GPIO/pinctrl driver](https://raw.githubusercontent.com/raspberrypi/linux/cff533aec2fa601846766b32ff57204e0a61bed7/drivers/pinctrl/pinctrl-rp1.c),
its DT binding and gpiolib valid-mask/cdev code at the same revision;
[RP1 Peripherals](https://datasheets.raspberrypi.com/rp1/rp1-peripherals.pdf),
sections2.4,3.1,3.3. Private source hashes and reference copies accompany the run.
No captured DT or proprietary image bytes are copied into these instructions.

The original driver fixes ngpio54 and normally has three banks. The lab profile
reserves0..19 and22..53 through standard gpio-reserved-ranges. Pinned gpiolib.c
initializes this valid mask before querying directions; cdev rejects reserved
requests before hardware access. Only GPIO20 and21 are implemented. The full
compiled pinctrl alternative-function/debug interface is not claimed functional:
unsupported pin/bank/register accesses produce MEMTX_ERROR. Do not bulk-read all
pinmux/pad debug files. No physical GPIO hogs or unsupported children are imported.

The opt-in profile creates the real compatible provider with the physical three
resource descriptors, one bank0 level-high RP1 IRQ0, self gpio-ranges, and explicit
reserved lines. It is a compatible lab substitution, not a full RP1 GPIO claim.
The machine's default remains the previous generated tree without this provider.
An allowlisted generator delta and independent live-node hashes prove what was
installed; arbitrary external -dtb remains rejected.

| BAR1 offset | Implemented register behavior |
| --- | --- |
| d0000 + GPIO*8 | STATUS and CTRL for20/21 only |
| d0100 / d011c / d0120 / d0124 | INTR / PCIe enable / force / masked status |
| e0000 / e0004 / e0008,e000c | RIO output latch / direction-enable / input samples |
| f0000 / f0054 / f0058 | Voltage metadata / pad20 / pad21 |

Each block uses RW/XOR/SET/CLEAR aliases at0/1000/2000/3000. CTRL supports SYS_RIO
function5 or NULL31, input/output/enable/IRQ overrides and raw rising/falling/high/
low enables. Edge latches clear with self-clearing IRQRESET; levels follow the
sample and cannot be acknowledged away while active. Bank enable and force
produce the parent level. FIFO/SPI state is independent. State is committed before
RP1 notification; it follows the existing PCI MSI-X and native MIP path.

CTRL reset9f preserves the published NULL function/filter-field defaults. Pads
reset92 preserves documented fixed fields; pull-none is an explicit lab choice
where per-pin silicon defaults are not established. RIO/masks/latches reset to a
quiescent lab state. IE/OD, GPIO direction and overrides affect digital samples;
drive/slew/Schmitt/voltage fields are register metadata, not analog simulation.
Conflicting pulls, alternate functions, filtered IRQ modes and changing the
unimplemented filter constant are rejected. SYS clock-off APB accesses also
return an explicit error; this is an unsupported-clock convention, not measured
silicon clock-gating timing. Parent reset clears GPIO state and pending source;
a previously delivered parent GIC edge has its own acknowledgement lifecycle.

The synthetic fixture drives GPIO21 from GPIO20 only while20 is an enabled
output; a pin driven as output reads its own logical value. Undriven inputs use
logical configured pull or0. There is no reverse wire, electrical contention,
propagation, metastability, debounce or synchronizer timing model. Both sampled
RIO input registers use a documented zero-delay convention. SPI0 remains its
previous logical wiring and is not routed through these GPIO pins.

Focused tests cover aliases, direction/latch/sample, errors, edge/level status,
mask/ack/rearm/PBA, BME blocking, SPI isolation, clock-off rejection and reset.
A native-board test observes GPIO IRQ0 as MIP0/GIC pending and verifies PERST.
Actual guest evidence must additionally show the unchanged original driver,
GPIO cdev value/edge operations and reserved-line/ownership rejection. Qtests
alone do not count as Linux driver verification or physical measurements.
