# Phase 10J: approved CM5 FSW, local experiment only

AI-assisted local experiment; not eligible for upstream submission under
`docs/devel/code-provenance.rst`. Never commit private images, payloads or logs.
No QEMU models changed. Phase10I defaults are preserved.

Use the approved AArch64 ELF only (SHA256
`b0b4dd5af15b4cbfd8005da10551cf4dc9f9ce45166299c4996d238a5362fbc3`).
There is no automatic retrieval. An explicit missing path produces BLOCKED;
the independently accepted golden and BOOT are still checked first.

From the checkout on BigDog, after the human arranges authorized placement:

```sh
python3 experiments/cm5-phase10j/run.py --fsw /home/aweso/cm5-v8-lab/phase10j/input/RpiDeployment.elf --duration 30 --work /home/aweso/cm5-v8-lab/phase10j/fsw30-$(date -u +%Y%m%dT%H%M%S)-$$
```

Only after reviewing successful startup and functional evidence, extend manually:

```sh
python3 experiments/cm5-phase10j/run.py --fsw /home/aweso/cm5-v8-lab/phase10j/input/RpiDeployment.elf --duration 300 --work /home/aweso/cm5-v8-lab/phase10j/fsw300-$(date -u +%Y%m%dT%H%M%S)-$$
```

`--golden`, `--boot-expected`, `--work` configure private inputs; see
[WORK-PC-SETUP.md](WORK-PC-SETUP.md). Binaries remain in `build-arm64-phase1`.
Default `--host-timeout 1800` bounds boot + serial transfer + application + shutdown
in host monotonic seconds. For a large ELF or slow TCG host, increase that bound
explicitly; do not reinterpret it as application time. No automatic 300s retry.

The harness validates regular files and the accepted full-image size/hash before
creating a fresh raw-backed QCOW2. It selects actual captured kernel/initramfs,
cmdline, physical-reference DT and config from that overlay's BOOT using the
existing headless selection policy. Selection is a lab firmware-behavior proxy;
the existing generated DT substitution remains in use. Original physical DT and
roots2 verity/FEC metadata are never edited. No host mounts or physical devices.
Preflight reads and identities remain private. Selected kernel/initramfs identities
are in `preflight-boot/selection.json`; actual exports/launch identities are in
`control/v8/boot-selection/selection.json`.

Two multi-user observations must pass the existing systemd, OS/FSW verity V,
roots2, verified mount and libc gates. Phase10J omits the legacy observer's LOGS
write and its fixed p6 check. It inventories live mounts/partition identities and
requires `/run` tmpfs and mounts a dedicated 64 MiB executable tmpfs below it
for staging. The parent `/run` retains V8's original `noexec` option. It makes no LOGS durability
claim. No FSW partition writes or verity resealing occur. Synthetic SPI/GPIO
stimuli are not enabled in this workload. Missing SatNOGS/serial fixtures remain
absent; nothing reports their communications successful.

The explicit ELF is hash/architecture checked on the host, transferred as a compressed launcher over base64 lines of at most 2048
characters, with only one line in flight until the guest acknowledges it. Both
compressed and expanded launcher digests are checked before execution; the ELF
is hash checked again in the guest. Console output is drained throughout. The dedicated executable tmpfs contains `RpiDeployment.elf`, with that directory as
cwd. Relative output files are disposable. No auxiliary application config/input
files are invented. If the ELF requires such files, record the failure and supply
an approved bundle in a later experiment. Absolute paths retain original V8
semantics. OS writable overlays and LOGS writes made by normal boot or the FSW
itself remain contained by the disposable eMMC overlay.

Guest root runs `timeout -s INT -k 10s 30s ./RpiDeployment.elf` (or 300s), with
stdin/stdout/stderr attached to a PTY. Output is streamed and also returned as
exact PTY bytes in the completion record. A guest watchdog kills a stuck process
group after duration+30 guest monotonic seconds. The host requests normal systemd
poweroff only after the complete newline-terminated completion record, including guest setup errors. A lost
completion record or boot hang reaches the host bound and requires forced cleanup;
it is INCONCLUSIVE, never normal shutdown. No timing fidelity follows from TCG.
Guest monotonic, host monotonic and QEMU virtual time are separate; virtual time
is unmeasured/null, not estimated. Output timestamps supplied by FSW retain their
own undocumented domain.

Private evidence under `--work`:

- `comparison.json`: Phase10I comparison envelope, physical observations as
  user-reported baseline, executable/tool/Git/image identities, event lines,
  status/reason, separate clocks. Exact physical component/task names are not
  available from the supplied narrative.
- `preflight-boot/selection.json`, `emmc.qcow2`: accepted BOOT identity and fresh
  overlay. `launch.json`, `runner.log`, `git-status.txt`: host launch evidence.
- `v8/serial.log`, `debug-serial.log`, `hardware.log`, `observations.jsonl`,
  `userspace.json`, `result.json`, `fsw-result.json`: full kernel/application/QEMU,
  verified mounts/tables and shutdown evidence. QMP records are not virtual time.
- `fsw-output.log`: complete application PTY bytes; includes warnings/errors.
  `guest-workload.py` contains the ELF payload and MUST remain private.
- `control/v8/command.json` and `boot-selection/`: actual selected exports and
  launch binding, also private.

BLOCKED means a missing/invalid prerequisite, FAIL an observed application crash,
forced kill or unexpected exit against the timeout contract; INCONCLUSIVE means
incomplete workload/boot/shutdown evidence. PARTIAL means a completed timeout run
still needing functional comparison. Automated keyword matches are candidate
event lines only. A human-reviewed PASS requires matching version, topology,
component/task identities, repeated housekeeping and packet generation/routing,
expected timeout (124), no observed crash, intact verified mounts and normal
shutdown. Missing fixtures alone are not emulator failures. Do not edit raw logs;
retain any reviewed classification in a separate review record with justification.
Compare the physical 300s narrative cautiously against a 30s first run; the native
Linux executable is a different build, never a replacement for this ELF.

Checks (no flight software executed on the host):

```sh
python3 -m unittest discover -s experiments/cm5-phase10j -p 'test_*.py' -v
python3 -m unittest discover -s experiments/cm5-phase10i -p test_transport.py -v
```

Phase10J uses a per-user lock and rejects running QEMU system processes. Operators
must also avoid starting older launchers/recovery workloads concurrently; those
older runners do not participate in this lock.
