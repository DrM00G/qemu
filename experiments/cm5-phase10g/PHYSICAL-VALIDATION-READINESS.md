# Physical comparison readiness

Local experimental model. No physical CM5 measurements were collected in Phase
10G. Existing captured kernel/initramfs/DT/config bytes remain physical-reference
inputs; they do not establish current SPI wiring or measured electrical timing. Physical access, approved wiring and a matching peripheral fixture are
prerequisites for later electrical comparisons. Do not attach arbitrary SPI
hardware or assume the physical captured tree enables SPI0.

| Measurement | Available virtual evidence | Later physical requirement |
| --- | --- | --- |
| Kernel / driver identity | Captured kernel SHA256, 6.18.50 version, original OS modules and bound-driver paths | Hash running kernel/modules; establish build correspondence to pinned source |
| Boot provenance | Exact active-QCOW2 selected kernel/initramfs hashes; fixture policy trace | Capture actual EEPROM version/config/BOOT_ORDER through approved read-only procedure |
| Runtime DT | Guest FDT SHA256 and node/property hashes; generated lab substitutions | Capture running FDT and distinguish boot-file DT from firmware-transformed runtime tree |
| PCIe | Native Gen2 x4 link, BDFs, BAR sizes/addresses, RP1 chip ID | Read link negotiated speed/width, hierarchy and assigned resources; retain raw observation |
| MSI-X / MIP | 61 vectors, SPI vector19, driver counts, modeled MSI-X and MIP traces | Read vector allocation, interrupt counters and error state; no claim of access to equivalent internal timestamps |
| Clock and SSI config | RP1 SYS 200MHz, BAUDR, requested rate, width/mode, FIFO thresholds, enable/SER state | Approved read-only register/clock observations; verify pinctrl and actual external SCLK |
| SPI workload | Original driver ioctl, exact message order/length/hash, synthetic XOR0xa5 response | Identical approved payloads, response and CS reset/state behavior with a documented matching fixture |
| CPU service budget | Host-clock and fixed/adaptive instruction-clock traces expose different refill margins | Measure approved IRQ-to-refill/CPU-instruction or cycle timing and PCIe/MMIO costs; calibrate CPU/bus timing before physical timing claims |
| CS framing | Independent QEMU CS/byte oracle, FIFO/refill/IRQ/timer correlation | Logic analyzer SCLK/CS/MOSI/MISO capture, decoder settings and trace identity |
| Completion / errors | ioctl result, RX identity, IRQ deltas, no observed idle IRQ stream | Same definitions and observation windows; retain errors and failed first messages |
| System survival | roots2/V mappings, verified OS/FSW, PID1, two active multi-user samples, LOGS persistence | Approved matching boot/media baseline and read-only post-run evidence |

The virtual slave is `ssi-test-slave`, CS0, eight-bit mode0, response
`MISO = MOSI XOR 0xa5`. It is fixed logical wiring, without GPIO/pinctrl,
propagation delay or electrical behavior. Physical wiring, voltage, connector,
pin assignments, slave implementation/version and analyzer setup are UNKNOWN.
A physical run without a comparable fixture is not a failure of the simulator.
Do not infer electrical equivalence from matching byte streams.

`comparison-schema.json` defines a small common result envelope. Unknown values
are null, with a reason in limitations. Preserve raw reports alongside normalized
fields. Record requested and divider-derived/electrically measured speed
separately. Guest virtual_ns, guest uptime, host monotonic_ns and analyzer time
have separate origins; never subtract across those clocks without a documented
synchronization experiment. Instruction-count virtual time is an explicit
execution convention, not a measured ARM cycle duration.

A later approved comparison should pin the kernel/module/DT identities, fixture
and workload first; repeat the same cold-initialized workload independently;
compare CS segment count and message-boundary hashes before timing distributions;
then compare clock/divider and interrupt/error states. Keep all failing messages.
No physical collector toolkit or hardware-settings changes are implemented here.

The observer currently repeats18-message batches until two independent active
multi-user observations. Run lengths can exceed90 messages. A future comparison
must match the entire submitted sequence/count and its definition hash; do not
trim early failures or compare unequal observation windows as identical tests.
