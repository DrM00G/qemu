# Hardware capability matrix

Static captured declarations, QOM realization, Linux binding and functional testing are separate evidence. No new physical measurements. FSW requirements remain UNKNOWN.

| Capability | Classification | QOM realized | Linux bound | Functional evidence |
| --- | --- | --- | --- | --- |
| rp1-gpio-cdev | compatible-lab-substitution | True | True | PASS |
| rp1-spi0 | compatible-lab-substitution | True | True | PASS |
| rp1-sys-clock | compatible-lab-substitution | True | True | PASS |
| rp1-other-clocks | guest-advertised-unvalidated | True | True | NOT_TESTED |
| rp1-pcie | physically-declared-modeled-exercised | True | True | PASS |
| rp1-mfd | physically-declared-modeled-exercised | True | True | PASS |
| mip-host-edge | physically-declared-modeled-exercised | True | True | PASS |
| native-emmc | compatible-lab-substitution | True | True | PASS |
| console-uart | compatible-lab-substitution | True | None | PASS |
| header-uart-debug | compatible-lab-substitution | True | None | PASS |
| rtc-substitute | compatible-lab-substitution | True | None | NOT_RUN |
| synthetic-spi-slave | synthetic-fixture | None | True | PASS |
| synthetic-gpio-loopback | synthetic-fixture | True | True | PASS |
| header-i2c-policy | intentionally-disabled | None | False | NOT_IMPLEMENTED |
| physical-rp1-i2c1 | physical-only-unsupported | None | False | NOT_IMPLEMENTED |
| physical-rp1-ethernet | physical-only-unsupported | None | False | NOT_IMPLEMENTED |
| physical-rp1-gpiomem | physical-only-unsupported | None | False | NOT_IMPLEMENTED |
| physical-rp1-mailbox | physical-only-unsupported | None | False | NOT_IMPLEMENTED |
| physical-usb2 | physical-only-unsupported | None | False | NOT_IMPLEMENTED |

The manifest contains per-node register/dependency declarations, source identities and ranked gaps. GPIO has54 compiled driver descriptors but52 lines are reserved; only20/21 are usable. Its complete pinctrl/filtered/raw-gpiomem ABI is not implemented. SPI remains logically wired independently of GPIO. Provider registration alone is not a functional test.

Raw captured/live DT and QOM/Linux logs remain private. The selected BOOT DT is not installed; the opt-in generator profile is an explicit bounded compatible substitution. Physical-only node counts are not an implementation target.
