# Phase 9 actual matrix results

| Case | Outcome | Wall seconds | Target guest seconds | Logged FEC events |
| --- | --- | ---: | ---: | ---: |
| clean | PASS | 158.56 | 134.08 | 0 |
| os0 | PASS | 161.94 | 140.03 | 3 |
| os1 | PASS | 190.26 | 159.01 | 3 |
| no-fec | EXPECTED_FAILURE | 5.16 | not reached | 0 |
| fsw0 | PASS | 163.95 | 140.90 | 2 |

All four successful boot cases satisfy each condition below. The no-FEC control intentionally refuses root.

| Condition | clean | os0 | os1 | no-fec | fsw0 |
| --- | --- | --- | --- | --- | --- |
| kernel_boot | PASS | PASS | PASS | PASS | PASS |
| os_verification | PASS | PASS | PASS | DETECTED_EIO_ROOT_REFUSED | PASS |
| fsw_verification | PASS | PASS | PASS | NOT_REACHED_EXPECTED | PASS |
| systemd_target | PASS | PASS | PASS | NOT_REACHED_EXPECTED | PASS |
| diagnostic_process | PASS | PASS | PASS | NOT_REACHED_EXPECTED | PASS |
| filesystem_operations | PASS | PASS | PASS | NOT_REACHED_EXPECTED | PASS |
| persistent_logs | PASS | PASS | PASS | NOT_REACHED_EXPECTED | PASS |
| rp1_spi | PASS | PASS | PASS | NOT_REACHED_EXPECTED | PASS |
| sustained_heartbeat | PASS | PASS | PASS | NOT_REACHED_EXPECTED | PASS |
| result_collection | PASS | PASS | PASS | PASS_CONTROL | PASS |

FEC event labels are kernel RS-base byte offsets, not physical ECC counts. Full stages/digests, inputs, logs and failure records remain in the linked run directories.

Preservation: 14 hardware qtests and 10 guest regressions PASS (including the8 GiB smoke). Golden whole-file SHA-256 unchanged.
