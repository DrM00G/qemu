# Current limits after real V8 integration

* Actual Debian 13 V8 userspace, systemd and mock diagnostic are exercised;
  proprietary flight software is absent and neither searched for nor emulated.
* Simulator kernel is Phase 3 `6.18.62-cm5-surrogate-16k`, not production
  `6.18.50+rpt-rpi-2712` or the imported experimental unified 6.18.50 Image.
  The latter's matching module archive is available but untested here.
* Real BOOT/OS/FSW/LOGS/RECOVERY layout is retained. Physical firmware boot,
  EEPROM, eMMC boot hardware areas, RP1, DMA, GPU and PCIe behavior are not modeled.
  BOOT corruption cannot predict physical Pi firmware boot survival.
* Original OS metadata matches all captured OS blocks in a host check. Runtime
  root is readonly ext4 under RAM OverlayFS, **not** a dm-verity root. Original
  FSW metadata is used for real guest dm-verity/FEC. Captured roots are not
  independently authenticated; no secure-boot claim is made.
* UART passes with V8 libraries before systemd starts. UART RX under production
  console activity timed out in earlier runs; no in-service UART robustness claim.
  PL011 differs from CM5 mission UART hardware and timing.
* SPI ioctl adapter compiles, but no guest SPI controller/driver/slave path has
  been integrated. SPI, I2C and GPIO remain UNSUPPORTED. Existing PL022 or BCM2835
  QEMU controllers are candidates; neither is DesignWare/RP1 compatibility.
* Network tests cover successful TCP/UDP echo only. Refusal, corrupted response,
  and timeout profiles, physical Ethernet characteristics and sustained mission
  duration remain unimplemented. Heartbeat test lasts ten seconds.
* JSON config is an initial path/device/duration frontend; the injected service
  uses an explicit simulator profile. The replacement executable must implement the diagnostic positional CLI;
  full unified experiment schema and statistical corruption sweeps remain work.
* One bounded FSW corruption case is the implemented real-image pilot. It is a
  4096-byte block XOR, not random independent bit flips. OS corruption and a new
  real-V8 no-FEC guest control are not claimed. Phase 3 controls remain separate.
* Corrected logical reads do not repair golden/parity bytes or the fault overlay.
  Kernel correction events are not counts of distinct damaged blocks.
* Production failures are preserved separately. The EEPROM updater fails under
  virt; earlier cloud-init and swap-resize failures are retained. A profile PASS
  does not establish a healthy physical hardware configuration or all-unit PASS.
* Tests ran under TCG with bounded RAM; no flight timing, full RAM endurance,
  thermal, electrical or power-loss fidelity. Phase 1–3 source is unchanged;
  their full multi-case regressions were not repeated in this continuation.
