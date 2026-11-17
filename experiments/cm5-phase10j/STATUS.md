# Phase 10J resumed result — 2026-11-16

Local AI-assisted experiment only; not for upstream submission. No commit/push.

Approved ELF verified on host and guest. Completed a 30-second FSW workload in
QEMU with original V8 kernel/initramfs and a fresh disposable QCOW2 overlay:
`/home/aweso/cm5-v8-lab/phase10j/fsw30-20261116-approved-04`.

Execution/shutdown PASS; comparison PARTIAL pending the user's physical transcript
comparison. Guest duration 30.041941s, exit 124,
normal systemd poweroff and QEMU exit 0. Version 3.0.0-alpha, 13 components,
11 created tasks, 2 sampling messages, packet receipt/routing to VC0 and TX queue
activity observed. 16 KiB pages and 128 KiB stack clamps match the narrative.
SPI nodes absent; /dev/spidev0.0 open and SPI_IOC_MESSAGE fail; watchdog run says
not implemented. No crash observed. No physical parity or successful radio claim.

Golden unchanged. Post-shutdown allocation audit finds changes only in LOGS p6;
BOOT, OS, FSW and recovery/verification storage retain backing contents. No model,
protected partition or verification metadata edits. Exact PTY transcript,
readable transcript, reviewed comparison and checksummed source bundle are under
the evidence directory. Work-PC instructions are complete; no remote build/run.

Resolved three end-to-end harness issues using local-only changes: incomplete
UART upload (now per-line ACK and launcher digest checks), V8 noexec /run (now a
dedicated executable tmpfs submount), and premature parsing of fragmented JSON
(now require the final newline). Seven harness tests and existing transport test
pass. Earlier attempts 01/02/03 remain preserved and are described in REVIEW.md.
The optional 300s command is in README.md and evidence command-300.txt; not run.

The legacy serial-only full_scan_complete/multi_user booleans are false; direct
userspace observations establish the active target and verity gates. See REVIEW.md
for this limitation and the separation of host, guest and unmeasured virtual time.

## Historical preparation checkpoint

# Phase 10J status — 2026-11-16

Local AI-assisted experiment only; not for upstream submission.
HEAD remains `64b13da2b57c7ff0a5ff061d975d4363be478c6c` on `cm5-rp1-hardware`.

- Harness/host checks: PASS, five tests including a byte-exact 256 KiB canonical
  PTY upload and conservative classification cases. No test executes FSW on host.
- Existing Phase10I transport regression: PASS, one test.
- Python compilation, diff whitespace and Phase10I comparison schema: PASS.
- Existing QEMU binary/custom machine options: verified. Successful configure
  flags recovered from config.status. No QEMU build/model change was needed;
  no work-PC build or workload was attempted.
- Golden/full-eMMC and BOOT preflight: PASS. Size 15634268160, raw SHA256
  `e2fb1a85c2652838793e58f8b13ef908e2e4a4c4295e27297ce742287f69cb87`;
  matching captured kernel/initramfs/config/cmdline/DT selected using the existing
  acceptance manifest. Read-only selector proves overlay/backing chain unchanged.
- Actual 30s QEMU FSW experiment: BLOCKED. No approved executable found under
  `/home/aweso` or the private lab; explicit expected incoming path is absent.
  No full Linux guest launched and no FSW executed. Guest workload/shutdown hook
  remains unvalidated end to end pending that binary. No 300s run attempted.

Private first preflight evidence (preserved):
`/home/aweso/cm5-v8-lab/phase10j/j-20261116-prepare-01/`.
Final preflight with compact comparison metadata/source snapshot:
`/home/aweso/cm5-v8-lab/phase10j/j-20261116-prepare-02/`.
Each contains `comparison.json`, `preflight-boot/selection.json`, fresh
`emmc.qcow2`, and Git status; final includes `harness-sources/`.
No application output exists because launch was blocked before Linux startup.

Added run.py, guest.py, test_harness.py, README.md, WORK-PC-SETUP.md and this status
under experiments/cm5-phase10j. Only earlier tracked file changed is
experiments/cm5-phase10c/run.py: opt-in workload/shutdown gating plus configurable
private lab/golden paths. Existing Phase10I behavior defaults remain unchanged.
Previous untracked evidence was left in place. No commit/push/reset/clean/stash,
physical access, original capture write, FSW transfer, or peripheral implementation.

Next action: arrange authorized transfer of the matching ELF to the explicit
incoming path (or use another explicit local --fsw path), run README's 30s command,
and review component/task identity, housekeeping, packets, errors and shutdown
before considering the documented optional 300s command. Raw physical/native logs
would permit a stronger comparison than the current user-reported narrative.
