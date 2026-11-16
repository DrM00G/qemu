# Comparison evidence contract

`comparison-event.schema.json` is the small common envelope for a later physical
logger. It separates Linux/analyzer observations, internal emulator diagnostics,
synthetic stress and unavailable fields. No physical logger or hardware access
was performed. comparison-manifest.json identifies the actual qtest examples. A null field is unknown, not zero or a passing measurement.

Every run also needs a manifest containing source and executable SHA256, exact
argv/clock/CPU profile, kernel/initramfs/runtime-DT identities, BOOT-selection
provenance, fresh disposable media identity, payload fixture identity and the
full ordered message hashes/counts. Existing G runner manifests/reports retain
these in private directories; H publishes sanitized results and qtest source/
executable hashes. A physical manifest would instead identify actual running
software, board/wiring/voltage, slave implementation, analyzer and trigger.

`sequences-validated/*.jsonl` preserves every selected synthetic qtest command,
reply and device event with a monotonically increasing index. MMIO payloads
include addresses, writes and read results. Device fields retain original names
and explicit virtual_ns where emitted. Transfer and CS events lack timestamps;
they retain execution order and must not acquire an invented measured time.
`dw_apb_ssi_boundary` before/after snapshots include word, epoch, segment, TX/RX,
raw IRQ, mask and encoded state (SER bits0..3, SSIENR bit4, shifter/BUSY bit5,
IRQ bit6, TX threshold bits8..13, RX threshold bits16..21). `dw_apb_ssi_timer`
adds baud/input_hz and arm/deadline/callback virtual ns. `rp1_spi_state` has
mask/PBA/outstanding; `bcm2712_mip_timed` has controller/vector/delivery decision;
`bcm2712_pcie_dma_write` has actual transaction result.

These snapshots are internal diagnostics, even for registers a physical logger
could theoretically read. A trace observes the transition synchronously;
a later Linux register read may perturb or miss it. Only independently collected
Linux-visible information belongs in `observable`. Physical RX/TX FIFOs and
shifter state, QEMU scheduling lateness, MMIO reply barriers and internal segment
identity may be unavailable. A later collector must not subtract QEMU virtual
ns from physical analyzer/host/guest-monotonic time. Record separate clock origins
and synchronization evidence before any latency comparison.

The synthetic SPI fixture remains CS0, 8-bit mode0, MISO=MOSI XOR0xa5.
Requested speed, divider-derived speed and externally measured SCLK are separate.
Keep every first/failed message and unequal observation windows. Internal
notifications, accepted PCI DMA writes, MIP pulses, parent pending and Linux IRQ
service counts are different quantities; none substitutes for another.
