# Native RP1 readiness: source inspection only in Phase 10D

The recovery campaign has priority. Phase 10D does not change PCIe hardware or
claim downstream/native MSI progress. Existing native root/MDIO and GPEX/RP1
qtests are rerun; all original-kernel campaign boots use the native profile.
The expansion controller may remain disconnected. The RP1 controller must not
be declared operational merely by setting link-up bits.

Inspected source: official Raspberry Pi `stable_20260911`, commit
`cff533aec2fa601846766b32ff57204e0a61bed7`, private pinned
`~/cm5-v8-lab/phase10c/reference-stable-20260911/pcie-brcmstb.c`.
Its recorded SHA-256 is
`212ec09ab522c2e7b81638be3db833bb7e3ad62b201a08f9858092f6130ec787`.
The physical `/axi/pcie@1000120000` and MIP descriptors were re-read directly
from private `reference/live-v8.dtb`, without copying the DTB into the repo.

Minimum coherent next slice:

1. Attach a real RP1 PCI endpoint to the root port's secondary bus for domain
   0002 only. Model PERST/reset, endpoint presence and enabled bridge state.
   Link PHY/DL status can then follow this modeled connection, with documented
   lab timing. An unattached expansion port remains link-down.
2. Route indexed downstream configuration at +0x9000 / +0x8000 to the actual
   PCI hierarchy. The pinned driver's `brcm_pcie_map_bus()` uses root config
   directly for bus0/devfn0 and refuses downstream accesses unless both link
   bits at +0x4068 are set. Missing functions return absent-device data;
   bridge bus numbers and byte/word/dword semantics must work through PCI core.
   Test reset, invalid BDFs and closed bridge windows, not only vendor IDs.
3. Turn CPU-to-PCI descriptor latches into bounded outbound translations, with
   memory decode and bridge-window gating. The physical RP1 non-prefetchable
   bus range starts at zero and maps into CPU 0x1f00000000. BAR0/1/2 must be
   sized/assigned by Linux and accessed through these windows, never fixed to
   physical captured addresses internally.
4. Implement the separate inbound/DMA address space, including physical DT's
   bus 0x1000000000 -> CPU RAM0 window and external MIP bus alias
   0xfffffff000 -> CPU 0x1000130000 (4096 bytes) on the RP1 controller.
   Keep controller-specific DMA isolation/bounds. CPU outbound translation
   alone does not establish endpoint DMA/MSI support.
5. Preserve external MIP ownership: physical `msi-parent` points outside the
   host. Pinned `brcm_pcie_probe()` enables its internal MSI block only when
   `msi-parent` points back to that host. Route endpoint MSI writes through
   the translated host DMA space into the proper MIP and GIC; test mask,
   pending, vector decoding and reset. Do not substitute GPEX delivery and
   claim it is native Broadcom behavior.
6. Require actual captured-kernel RP1 enumeration, Linux-assigned BAR sizes,
   mapped accesses and interrupts, then RP1 MFD/clock/SPI diagnostics alongside
   another verified original-kernel boot before claiming operational readiness.

This coupled link/config/window/DMA work is deliberately deferred rather than
changing the successful recovery platform during the expensive fault matrix.
The existing source still returns link-down and absent downstream configuration;
no native RP1 endpoint or BAR access is inferred from root-port enumeration.
