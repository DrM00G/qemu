# Executed Phase 1 validation

Executed on 2026-11-12 (host Hawaii time), on x86-64 Ubuntu under WSL2.
This is a local research experiment, not an upstream QEMU contribution.

Built `qemu-system-aarch64` and `qemu-img`, version 11.1.90, from checkout
`9d7d057a558b9a1c232cea390b4481dd20d9c9ce` using `./build.sh`.
The build completed; an immediate repeat returned `ninja: no work to do`.
No QEMU machine/device source files were changed.

Executed `./accept.sh --timeout 900` from this directory for both corrected runs:

| Artifact directory | Result | Wall time |
| --- | --- | --- |
| `artifacts/20261112-141559-c6448da0` | PASS, exit 0 | 299.94 s |
| `artifacts/20261112-141729-461a1e91` | PASS, exit 0 | 288.10 s |

Both used independent QCOW2 overlays and AAVMF variable stores, `virt`,
`cortex-a76`, multithreaded TCG, two vCPUs, 2048 MiB RAM, and VirtIO devices.
Both guest reports demonstrate:

* Ubuntu 24.04.5 LTS ARM64, kernel `6.8.0-147-generic`, 4096-byte pages.
* PID 1 named `systemd`, executable `/usr/lib/systemd/systemd`.
* `multi-user.target` active, no failed units.
* `phase1-test.service`: `Result=success`, `ExecMainStatus=0`.
* All filesystem, shared-library, CPU, memory and networking checks passed.
* Cloud-init user-data and network-config schemas valid; status `done`, no
  errors or recoverable errors.
* Normal systemd shutdown and Linux `reboot: Power down`, then QEMU exit 0.

The last run's host result also explicitly records `guest_poweroff_seen: true`.
See its [acceptance result](artifacts/20261112-141729-461a1e91/acceptance.json),
[guest result](artifacts/20261112-141729-461a1e91/guest-result.json), and
[serial log](artifacts/20261112-141729-461a1e91/serial.log). Generated evidence is
intentionally ignored by Git and remains on this host.

The original input disk SHA-256 was identical before and after every attempt:

```text
50e24e1fb79e89116e939d90aa7738f7af48c442fa1bc2510131e0b39c50348e
```

Failure-path checks also ran:

* Missing build executable: `FAIL_INFRASTRUCTURE`, exit 2; base unchanged
  (`artifacts/20261112-140647-39c9143c`).
* Sandbox denial of the HTTP listener: `FAIL_INFRASTRUCTURE`, exit 2; reran
  outside the network sandbox with authorization
  (`artifacts/20261112-141212-67abb269`).
* `./accept.sh --timeout 1`: intentional `FAIL_BOOT`, exit 1, preserved serial
  log and unchanged base (`artifacts/20261112-141347-7194d523`).

An earlier exploratory full boot (`artifacts/20261112-141241-51d8ba51`) passed
functional checks but exposed a cloud-init schema warning from an empty
`ssh_genkeytypes` list. That seed was corrected to generate an ephemeral
Ed25519 host identity, and acceptance was strengthened to validate cloud-init.
Use the two corrected runs above as the milestone evidence. Historical logs
and results were retained unchanged.

Python compilation, shell syntax checks, `git diff --check`, and ignore checks
for build products, overlays, firmware variables and logs all passed. Production
CM5 OS compatibility, FSW dependencies and physical hardware behavior remain
unvalidated; see the laboratory handoff in [README.md](README.md).
