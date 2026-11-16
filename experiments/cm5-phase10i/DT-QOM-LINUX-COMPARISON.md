# DT, QOM and actual Linux correspondence

The selected physical BOOT DT is a declaration reference, not executable virtual
hardware or a newly measured physical result. The captured live DT records a
different firmware/overlay stage. The generated compatible tree is the runtime
base; a source-backed, opt-in generator delta adds only the bounded GPIO slice.
No external physical DT was installed. Firmware policy remains a software proxy.

| Item | Physical declaration | Virtual implementation | Actual original Linux evidence |
| --- | --- | --- | --- |
| RP1 GPIO | /axi/pcie@1000120000/rp1/gpio@d0000, three banks | /pcie@1000120000/rp1/gpio@d0000; three windows, only20/21 supported | pinctrl-rp1 bound; cdev operations and native IRQ0 PASS |
| GPIO resources | d0000/e0000/f0000, each c000 bytes | RP1 BAR1 offsets match; unimplemented access returns error | driver maps three physical binding descriptors |
| GPIO IRQ | bank0/1/2 physical IRQ descriptors | only bank0 IRQ0 level-high exposed; MSI-X0→MIP0→GIC | four native events per four edges, correct cdev records |
| GPIO range |54 compiled pins and alternate functions | self gpio-ranges0..53; reserved0..19 and22..53 |52 invalid lines; bounded requests accepted/rejected correctly |
| RP1 SPI | original DW SPI node | unchanged logical controller/slave fixture, IRQ19 | dw_spi_mmio and spidev, strict CS/data gate PASS |
| RP1 clocks | physical provider/dependencies | tested SYS/SLOW register subset; broader outputs not proven | rp1-clk bound, SYS200MHz tested; other outputs flagged |
| Native PCIe/MIP | original compatibles and routing | endpoint/translation/MSI-X/MIP modeled subset | brcm-pcie, rp1 and mip_msi bound; BAR/native IRQ operation |
| eMMC/pinctrl | SoC-specific dependencies | existing SDHCI-compatible and lab pinctrl substitutions | unchanged original verity/FEC metadata and normal boot |
| Other physical peripherals | DT nodes and dependencies recorded | no wholesale node import or provider stubs | unsupported/unvalidated entries stay explicit |

Only three pre-existing properties change: header-gpio status and implementation,
and the connector pinmux description. The added provider property names/types,
reg lengths/cells, phandles, self-range, parent IRQ and valid lines are checked.
The F.2 libfdt pipeline reader is reused; this is a real changed generator profile,
not a no-op advertised as a physical overlay implementation.

Generated snapshots use stopped CPUs,2GiB,4CPUs and the same native eMMC/PCIe/MIP
profile as Linux. ARM boot fixups add/change other runtime properties later.
Compare the live GPIO property hashes semantically; record full live FDT hash
separately. Raw node count changes across these stages do not establish peripheral
coverage. Explicit feature matching flattens physical /axi and accounts for the
console/eMMC lab paths; unrelated nodes are not equated by numeric phandle alone.

The manifest includes physical reg/ranges/interrupt/cell bindings and resolved
clock/reset/pinctrl providers, selected/captured-live statuses, symbols identity,
realized QOM queries plus private qtree/mtree, actual bus-driver symlinks and
functional outcomes. Realized true does not imply fully implemented. Null means
not established. AMBA bindings were outside the captured bus enumeration, so UART
and RTC driver fields remain null; console operation and realization are distinct.

Identity SHA256 values:

- Selected reference: b297f9516345eb4eb22d22f4c364fcb3705970f28b6d87875583dadf37fbb3ac
- Captured live reference: 783d064376d6694b642a5efef08a17b361514f0ff99083c1eeb58d036551d3d0
- Generated fallback: 77191490723725bedc92d6f4ee06da8751b6a2c09e29bb845b12b2ac0b1b0396
- Generated GPIO target: c42a0b926b508526a1e59ed8e2d7535ee29238b4f5ade9d31354935b0f5264db
- Host10k actual runtime FDT: ce8ff79740dd8236cb71eccf78340fc101749c34d2b85e81510f3620123b10a7
- QEMU executable: f94c29959930a78c39d147d568d14e32f8d1128e32b6cf7a31c30ccae906d3dc

Full commands, specification/source hashes and property-level runtime checks are
in integration-results.json/ordering-results.json and the private contract/run
evidence. Original physical captures, raw QOM/Linux logs and image contents stay
outside the checkout. No physical GPIO waveform, filter/synchronizer/electrical
latency or FSW application requirement has been measured.
