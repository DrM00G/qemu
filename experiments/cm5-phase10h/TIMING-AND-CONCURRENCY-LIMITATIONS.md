# Timing and concurrency limits

The fixed 1ns instruction profile counts aggregate guest instructions and idle
warp under single-thread TCG/SMP4. It is not BCM2712 physical cycle calibration.
QEMU documents icount as incompatible with MTTCG. No result here establishes
deterministic multithreaded TCG or calibrated physical throughput.

Category A uses qtest, stopped CPUs and controlled virtual clock steps. All
commands and replies are barriers; timestamps in device events are virtual ns.
Normalized sequences strip host elapsed timestamps and TAP/process identifiers,
retaining every MMIO command/reply and selected device event in execution order.
QMP system_reset handler entry/exit is retained separately; acceptance of a
request is not a reset-completed barrier. Device-state assertions follow reset.
Repeated-input hashes compare entire sequences, with all first events retained.
This tests device ordering, not Linux instruction execution or SMP races.

Category B uses the actual kernel and four CPUs under host-clock TCG. The optional
`--phase10h-smp-stress` adds three disposable guest workers pinned to CPUs1,2,3,
performing private-RAM SHA256 and read-only RP1 chip-ID MMIO during the unchanged
SPI workload. Workers stop on parent request or after 30 guest-monotonic seconds;
parent reaps them. Per-worker affinity, loop count, digest and start/end times
allow overlap to be checked against the SPI observer interval. This is bounded
software competition, not a controller dispatch-delay model. Parent SPI child
retains its existing 20-second timeout. A stress timeout/fragmentation needs
classification from traces; late software service alone is not a hardware bug.
Default-off; ordinary baselines do not enable it. Host-clock execution is not
deterministic; worker checksums may differ because loop counts vary.

The delayed-service qtest needs no production-device timing knob. It withholds
software RX reads and RP1 IACK for exactly24000 virtual ns after the first
completion. Serializer timers and native notification machinery continue.
It models delayed service at the software boundary. It does not delay MSI-X
transport, MIP propagation, or serializer callback dispatch and does not claim
any such physical latency. The 8001ns refill test models expected starvation.

Late serializer callback dispatch remains a separate limitation. qtest clock
advancement dispatches intermediate deadlines; neither a large `clock_step` nor
fixed icount demonstrates a late timer callback reproduction. Queued serializer
frames still rearm relative to callback execution time. No global scheduler,
catch-up loop or absolute-deadline policy was introduced. MMIO arriving after a
deadline but before its callback needs a defined/tested contract in Phase10I.

Record/replay docs were read (`docs/devel/replay.rst`, `docs/system/replay.rst`).
No recorded-and-replayed CM5 run was attempted or validated. Custom RP1, SSI,
MIP and PCIe advertise unmigratable VMState; snapshots are unavailable. A future
replay audit must independently check reset initialization, UART input/output,
block `blkreplay` wiring, eMMC asynchronous completion and external control input.
Unmigratable declarations alone do not prove from-reset replay impossible, but
there is no basis to advertise support without a complete recorded/replayed run.

GPIO/pinctrl, SPI DMA, electrical SCLK/CS edges, bus posting/latency, CPU cache/
coherency timing and full RP1 registers remain outside the tested subset.
MIP level/VPU delivery and undocumented pending/clear silicon behavior remain
unsupported. No physical CM5 was accessed; hardware metrics remain uncollected.
No maximum physical SPI rate follows from the functional guest profiles.

Fresh fixed1ns1MHz strict framing is PARTIAL (126 messages/134 segments), despite
the historical G single pass. This profile does not make the full interactive
guest deterministic: external UART observer launch times, initial state and
background service execution are not record/replayed. Two failed messages show
actual FIFO drain, zero callback lateness and late refills; all3322 notifications
pair with native MIP delivery. Software service-delay cause is not fully isolated,
and there is no matched pre-H executable control. See stretch-failure-analysis.json.
No rate/timing tuning or retry was used to erase this result.

The completed host-clock MTTCG stress run passes90/90 strict messages, all
original V8 gates, and15 independently recomputed worker hashes with expected
affinities and full native-observer overlap. Four guest CPUs are online.
This validates one bounded concurrent workload, not exhaustive SMP race/reset
handling. No live SMP reset or IRQ-affinity migration stress was run.
