# Laboratory migration checklist

No private V8 artifact or physical CM5 has been tested by this public surrogate.
Keep the public baseline and all laboratory golden inputs immutable. Work from
exported files and disposable overlays; never point preparation tools at eMMC,
Windows partitions or other physical block devices.

| Public surrogate component | Laboratory replacement and evidence needed |
| --- | --- |
| Pi-source Linux 6.18.62, 16 KiB virt configuration | Exact experimental `6.18.50+rpt-rpi-2712` source/config/patches, uncompressed Image or documented format, matching modules/initramfs. Verify 16 KiB at runtime and add required virt drivers without assuming CM5 DTB compatibility. |
| Public Ubuntu 10 GiB raw ext4 OS | Complete exported V8 OS data, exact protected byte/block count, filesystem/partition layout, clean-state information, original boot arguments, fstab/crypttab and service dependencies. |
| Synthetic 512 MiB FSW | Actual binaries, libraries, configuration, permissions, service definitions, supported ABI/ELF alignment, required Linux interfaces and real functional acceptance endpoints. |
| Synthetic 1 GiB LOGS | Production ownership, permissions, writable-state paths, retention and crash/power-loss requirements. Keep it outside verity. |
| Synthetic RECOVERY regions | Authoritative data/hash block sizes, roots, salts, tree offsets, FEC offsets, protected-block counts and parity. Validate actual geometry; the public 1/128/256/272 MiB offsets are not production defaults. |
| Experimental initramfs-pinned roots | Trusted laboratory roots and production trust/verification procedure. A root read beside potentially altered data is not a trusted boot chain. Preserve laboratory root values rather than resealing modified data to bypass verification. |
| Synthetic ext4 BOOT and host direct boot | Actual boot components and filesystem layout for reference. QEMU virt still needs a compatible kernel and generated DTB; physical Pi firmware/DTB does not transfer unchanged. |
| Prototype service | Real FSW health checks, expected results, watchdog/heartbeat semantics, startup ordering and approved writable paths. Passing the prototype does not establish FSW correctness. |

Before importing:

- Prefer reproducing fixtures from scripts on the laboratory host. When moving
  existing sparse assets, rebase only host-side manifest `path` entries and the
  kernel workspace location, then verify all recorded hashes. Guest dm table
  device names and immutable data/tree/parity bytes must remain unchanged.
- Record hashes of every exported artifact and the known-good laboratory launch
  command, logs, kernel release, page size and dm tables/status.
- Inspect whether the 10 GiB object is a bare filesystem or a partitioned disk.
  Select the whole VirtIO device or the correct partition deliberately.
- Confirm virt/GIC/PSCI/architected timer/PL011/VirtIO PCI or MMIO, ext4,
  OverlayFS, Device Mapper, verity/FEC, SHA-256 and Reed–Solomon support in the
  actual kernel. Match all pre-root modules and archive compression support.
- Establish the verified mapper before mounting ext4, prevent journal replay on
  sealed data, and put writable OverlayFS upper/work storage on the same RAM
  filesystem with correct switch-root lifetime.
- Review `/usr`, BOOT, RECOVERY and device-specific mount requirements. Remove
  absent hardware dependencies only in an explicit simulator profile; retain
  their unsupported status instead of hiding failed production services.
- Validate 16 KiB executable segment alignment and any hardcoded mmap/page-size
  assumptions in real FSW and its dependencies.

Then validate incrementally:

1. Re-run the unchanged public Ubuntu baseline.
2. Boot the laboratory kernel with the public userspace and strict systemd
   acceptance. Confirm actual 16384-byte pages.
3. Substitute laboratory OS and its authoritative verity/FEC metadata; obtain a
   clean full userspace boot before enabling hardware-dependent FSW services.
4. Substitute FSW and validate actual essential functions and sustained service
   behavior. Keep SPI/mission-UART adapters explicitly unsupported until real
   interfaces are implemented and compared with the physical CM5.
5. Repeat bounded disposable corruption pilots with recorded offsets, proven
   XOR changes, kernel correction logs, known-clean targeted bytes and complete
   logical digests where feasible. Separate boot from recovery outcomes.

Unresolved physical differences include BCM2712/RP1 devices, firmware and boot
chain, eMMC controller/partition topology and endurance, sensors/buses, mission
UART/SPI, hardware watchdog, interrupts and real-time latency, thermal/power
behavior and full-memory stress. The current 8 GiB guest allocation is lazy
under x86-64 TCG and is not a physical CM5 performance model.
