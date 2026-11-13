# Phase 9 completion

Local research on `cm5-rp1-hardware`. No commit, push, stash, reset, clean or
branch change. Original evidence and golden image preserved. No physical
hardware measurements were fabricated or performed.

## Explicit answers

| Question | Actual result |
| --- | --- |
| RCU stall reproduced? | Yes: preserved pre-fix binary, same OS0 fault; RCU grace-period thread starvation during large CMD38 erase |
| Cause? | Synchronous512-byte-per-call card erase, exercised by fstrim on LOGS; see ROOT-CAUSE.md for measured causal evidence and its limits |
| Actual QEMU defect corrected? | Yes: shared card `hw/sd/sd.c` erase batching and exact-capacity bounds; no guest-driver workaround |
| Corrupted OS fully boots? | Yes: OS block0 and distinct OS block1 both reach multi-user.target and complete all ten function conditions |
| OS and FSW actively verified? | Yes: actual p2/p5 through independent dm-verity/FEC mappings, original metadata from captured RECOVERY p7 over native eMMC |
| Diagnostic/SPI after correction? | Yes: verified FSW read, filesystem/fsync, host LOGS persistence, live diagnostic process, real SPI and20 heartbeats pass |
| Tests inconclusive? | No comparison-matrix case is inconclusive. Physical/internal flash behavior, extreme erase sizes and long mission duration remain unvalidated; historical Phase 8 host state and complete native stack backtrace are unavailable |
| Source changes? | Hardware: `hw/sd/sd.c`, `hw/sd/trace-events`; qtest: `tests/qtest/bcm2712-sdhci-test.c`; diagnostic: `experiments/cm5-phase4/diagnostic.c`; runner hooks: `experiments/cm5-phase6/regress.py`; new Phase 9 sources/scripts listed in artifacts/validation.json |

## Measured matrix

| Run | Result | Wall seconds | Target guest seconds | Kernel FEC events logged |
| --- | --- | ---: | ---: | ---: |
| Clean full OS+FSW | PASS | 158.56 | 134.08 | 0 |
| OS block0, original fault | PASS | 161.94 | 140.03 | 3 |
| OS block1, different fault | PASS | 190.26 | 159.01 | 3 |
| OS block0 without FEC | EXPECTED_FAILURE | 5.16 | Root intentionally refused | 0 |
| FSW block0 | PASS | 163.95 | 140.90 | 2 |

The no-FEC case performs the corrupted read, returns EIO, reports verity C and
powers off before root switch. It is an expected negative control, not a recovered
boot. Successful cases restore the original block digests, finish with both
mappings V, have no RCU stall and pass every independently reported condition.
Logged events may include repeated correction of one injected block; they are
not independent faults or physical ECC/radiation statistics.

`RESULTS.md` and `artifacts/validation.json` contain the per-function comparison,
stage timestamps, source inventory and evidence paths. Individual `inputs.json`,
`command.json`, `serial.log`, `peripheral.log`, `host-samples.jsonl`,
`timeline.jsonl`, expected digests, metadata audit and protection records remain
with each run. Disk images, original sidecars and exports stay in the private lab.

## Reliability and regression evidence

* All14 hardware qtests pass: original5 RP1,2 CM5IO,3 MIP,3 SDHCI plus the new
  erase/bounds test. Checkpatch for the Phase 9 hardware delta has0 errors and0
  warnings; `git diff --check` is clean.
* Existing Phase 7 gate passes all three72-message /5,448-frame SPI matrices and
  three V8 diagnostic boots, including native MIP and both fallbacks.
* Preserved Phase 8 native eMMC SPI, plain V8 and OS-only verified V8 profiles
  pass. The8 GiB native eMMC/SPI smoke also passes:10 preservation guest runs.
* Same-profile pre/post diagnostic: old binary reproduces RCU starvation;
  fixed binary reaches target and powers off without it. The old diagnostic
  eventually completed, but that does not make its RCU behavior healthy.
* Explicit Linux fstrim after target with both mappings:985,661,440 bytes across
  eight CMD38 operations, about2.29 guest seconds total. Kernel/diagnostic/SPI,
  persistent LOGS and heartbeat still pass afterward, with no RCU stall.
* Original metadata audit verifies all2,621,440 OS and131,072 FSW data blocks and
  their complete Merkle trees against the exact capture. No parity was regenerated.
* Golden whole-file SHA-256 is checked against the preserved Phase 8 reference;
  actual read-only descriptor flags are recorded in every matrix run.

No SDHCI core, BCM2712 wrapper, MIP, GIC, timer, RP1 or SPI driver bypass was
introduced. `hw/sd/sdhci.c` and `hw/sd/bcm2712-sdhci.c` retain their pre-Phase 9
hashes. The new diagnostic environment option is inactive in old profiles.

## Retained integration failures and report corrections

* First preserved-binary launch could not locate its option ROM after the binary
  was copied. A restored repository ROM search path fixed this; failure retained.
* Editing the launcher's option list while its shell waited on OS0 caused a
  trailing argument to be read as a command after the guest passed. The schedule
  resumed without repeating passed guests; scripts were then left unchanged.
* OS1's first result parser expected `FEC 1`. The real Linux log reports the RS
  interleaver byte base, `FEC 4096`. The pinned kernel source confirms that unit.
  `recheck-os1.py` creates separate `result-rechecked.json` from the same logs;
  the original result remains. All other checks, including raw/verified digests,
  target, diagnostic and shutdown, already passed. No workload was rerun to hide
  a failure.

## Remaining limits

This is a bounded logical fault-recovery experiment, not a statistical reliability
claim. The local diagnostic is injected into the RAM view and reads verified FSW;
it is not a production FSW executable authenticated by the FSW mapping. Original
captured root hashes are not independently authenticated, so no secure-boot claim.

Legacy PIO, synthetic card identity/EXT_CSD, fixed clocks, GPEX hosts and the other
Phase 8 substitutes remain. No HS200/HS400, DMA/tuning accuracy, EEPROM/firmware
boot, flash ECC/FTL/wear/power-loss/radiation behavior is established. Erases are
batched but still synchronous; much larger/extreme workloads remain untested.

The verified-root loop/DM stack remains pinned during final shutdown and emits
the existing busy-detach warnings. QEMU exits normally, diagnostics are collected,
and the deterministic LOGS file is verified from a post-exit export. This proves
that artifact's persistence through normal emulator shutdown, not physical
power-loss safety or complete teardown of every root dependency.
