# Physical-versus-QEMU interpretation

| Aspect | Captured physical V8 | This campaign |
| --- | --- | --- |
| Kernel/module | 6.18.50, external FEC-capable dm-verity | Same captured kernel and original module |
| OS/FSW/metadata | Captured roots2 partitions and RECOVERY | Same unmodified golden backing; fault bytes exist only in disposable overlays |
| Boot path | Firmware selects BOOT inputs | Direct host `-kernel`/initramfs, generated compatible lab DT; no firmware execution |
| Storage | HS400, ADMA64, CQE16, real eMMC | Synthetic card identity/clocks, existing ADMA64 with bounded command batching; no CQE/HS400 fidelity claim |
| Fault origin | No physical faults introduced here | Exactly one logical 4096-byte constant replacement per injected case |
| Correction | Physical clean reference does not demonstrate correction | Actual captured kernel must report correction and return the original verified block while raw remains damaged |
| Negative control | Not run on physical CM5 | Separate diagnostic hook removes OS FEC, records EIO/corrupt status and refuses root |
| FSW execution | Captured p5 content | Empty lost+found only; verified reads, no captured application execution |
| Peripherals | Actual RP1 and native PCIe | Native root ports/MDIO subset; downstream RP1 and native MSI unavailable; second PL011 debug UART is a lab interface |
| Persistence | No physical power-loss experiment | Independent file recovery after normal guest/emulator shutdown, without journal replay |
| Time/error counts | Reference observations only | Guest/host clocks distinct; correction messages may repeat one damaged block; no rate/statistical extrapolation |

No flash ECC, FTL, endurance, wear, radiation response, secure boot, metadata
authenticity or physical timing equivalence is established. The physical
39.36-second early logging interval remains unattributed to FEC. The captured
full verified OS scan stays intact in all successful original profiles.

`O_DIRECT` avoids block-device page-cache hits for the target check. Injection
precedes QEMU startup, so the original scan cannot receive a pre-injection guest
cache entry. Kernel FEC messages must identify the target partition and byte
interleaver base (not the absolute target offset); merely loading the module or reaching userspace does not count. Internal
hash/FEC metadata caching is normal verification behavior and is not claimed
to be eliminated. No `check_at_most_once` or ignore-corruption option is added.

The schema can represent future roots/distributions. Acceptance by that schema
does not prove those configurations were created or tested. The actual runner
supports only the five named cases and original captured roots2 metadata.
