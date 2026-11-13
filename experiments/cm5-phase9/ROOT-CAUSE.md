# Phase 8 stall: reproduced erase-path starvation

## Finding

The native eMMC path exposed a pathological synchronous erase implementation in
QEMU's existing card model, `hw/sd/sd.c:sd_erase()`. It called `sd_blk_write()` /
`blk_pwrite()` separately for **every512-byte sector**. Linux's periodic fstrim
on disposable LOGS issued CMD35/CMD36/CMD38 over large free ranges. One128 MiB
CMD38 therefore performed262,144 backend calls before returning from the MMIO
instruction that issued the command.

This is an emulation latency/starvation defect, not evidence that FEC failed or
that the captured verification metadata mismatched. It is in the shared card
engine reached through BCM2712 SDHCI, rather than a new MIP or SDHCI interrupt
transition. No Linux driver check, RCU warning, systemd fstrim service or guest
timer was disabled to fix it.

## Evidence and causality limits

1. The preserved Phase 8 pilot's final controller trace is CMD35/36/38, during
   systemd fstrim. Its earlier FEC read had already returned the golden digest,
   verified ext4 mounted, the diagnostic passed and SPI completed.
2. `repro-before-2` uses the preserved Phase 8 binary, same kernel/machine,
   original observer, original OS0 fault and added passive diagnostics. It
   reproduces an RCU stall during that erase workload. The kernel explicitly
   reports **rcu_preempt kthread starved for8814 jiffies**, with all quiescent
   states seen. The configured HZ is250, so that is35.256 guest seconds.
   Timer/MMC interrupt counters advance between erase calls; the trace remains
   in large CMD38 operations during delayed progress.
3. Host samples show CPU pressure about1.29%, memory pressure0, IO pressure
   about0.15% over that reproduction. Each vCPU's accumulated run-queue wait is
   at most0.31 host seconds. The host has no cgroup CPU/memory quota or recorded
   throttling. Other vCPUs are repeatedly waiting on futexes while the issuing
   thread progresses. This argues against external CPU/memory exhaustion as
   the primary cause. Historical Phase 8 host pressure was not recorded and
   cannot be reconstructed.
4. An isolated synthetic128 MiB erase on the old binary takes19.650556 seconds.
   The final fixed test takes0.108358 seconds, about181 times faster. It checks
   the same erased contents and untouched adjacent sectors. This isolates the
   card operation from systemd, FEC, serial output and guest scheduling.
5. Linux `sdhci_request()` / `sdhci_request_atomic()` in the pinned source hold
   `host->lock` with `spin_lock_irqsave()` while issuing commands. QEMU completes
   the entire synchronous card erase inside the SDHCI command-register write.
   Long device callbacks consequently delay progress at an IRQ-disabled driver
   operation and interfere with other device/vCPU work. This mechanism is
   supported by source inspection and the latency probe; no host native stack
   backtrace was captured. Guest RCU stack-dump headings were emitted, but do
   not supply a complete symbolized call chain. Those missing frames are not
   invented.
6. The fixed original-observer reproduction reaches target and powers off in
   149.45 wall seconds without an RCU stall. The old diagnostic run eventually
   completes in288.75 wall seconds, with the stall. The older Phase 8 run remains
   a300-second timeout. Increasing the diagnostic limit allowed observation of
   eventual progress; it is **not** the fix. Natural fstrim timer scheduling
   varies: the fixed original-observer boot did not itself execute CMD38, so
   that boot comparison alone is not treated as an erase-path causal control.
7. `trim-validated` explicitly invokes real Linux fstrim on disposable LOGS
   with both original verity/FEC mappings active. It exercises eight CMD38
   ranges totaling985,661,440 bytes, with1.058663 seconds summed device time and
   0.352751 seconds maximum single-command time. Guest fstrim takes about2.29
   seconds, returns0, then target/diagnostic/SPI/twenty heartbeats/host LOGS
   persistence all pass without an RCU stall. This closes the natural-timer
   scheduling gap in the ordinary boot comparison.

`repro-before-2/result.json` retains the earlier runner's generic boot PASS and
`phase9.rcu_stall=true`. The final report classifies it as **REPRODUCED_RCU**,
not a healthy recovery. No original record is rewritten.

## Corrected source

High-capacity cards now write erased0xff data in bounded1 MiB batches. Contents,
inclusive sector endpoints and active hardware-area offset are preserved. The
code does not use QCOW2 discard, which could expose backing bytes instead of
the previous model's erased value. SDSC per-group write protection retains its
old sector path. Backend failure sets a card error. An independently discovered
exact-capacity bounds error is corrected: an address equal to capacity is invalid,
and must not grow the overlay by erasing one sector past its end.

`hw/sd/trace-events` adds erase batch lengths and elapsed time. The new qtest
covers128 MiB erase contents, adjacent boundaries, a partial batch, card state
and the exact-capacity error, alongside all previous SDHCI tests.

## Other hypotheses

| Hypothesis | Evidence / remaining scope |
| --- | --- |
| FEC decode or metadata failure | Original digests restored; distinct OS/FSW fault tests and no-FEC control establish actual verification behavior |
| MIP/GIC or timer malfunction | Models unchanged, hardware qtests and actual interrupt/SPI/heartbeat traffic pass; no physical timing equivalence claim |
| SDHCI Auto CMD12/23/reset/FIFO bug | Existing focused tests preserved; erase stalls occur in synchronous card/backend work; no bypass or forced completion |
| PIO IRQ storm / per-byte work | PIO still has substantial software overhead; measured command sequencing continues; no unmeasured optimization was applied |
| Console/tracing bottleneck | Same console and tracing remain; isolated command probe excludes them; trace output has overhead but does not explain262,144 backend calls |
| Userspace dependencies | Real V8 retains cloud-init, swap/unsupported-board service delays and ordinary failures; no masks were added to force target |
| External host starvation | Not supported by the controlled reproduction's pressure/run-queue data; arbitrary future host overload is not ruled out |

The fix is not a general asynchronous eMMC busy/timing model. Very large erases
still execute synchronously, and physical ECC, FTL, wear, power loss and radiation
remain outside this experiment. The targeted LOGS workload is measured and
validated; other extreme command sizes are not claimed.
