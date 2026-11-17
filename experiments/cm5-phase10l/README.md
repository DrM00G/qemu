# Private local Phase10L operational boot experiment

Not for upstream contribution under QEMU's code-provenance policy. No hardware
models change. All images, captured files, generated launchers, identities and
raw evidence stay outside the checkout. No physical storage is operated on.

The exact original scan is in `scripts/local-top/cm5-fsw-verity` inside captured
V8 initramfs `fcaade1e3aab0d79a51a170f556d25d0d1476bc17518099de54f5ebe16feab5b`.
Its FSW mapper uses the pinned FSW root file plus read-only RECOVERY hash/FEC
loops. Its OS mapper uses the pinned OS root file and two more read-only loops.
Both veritysetup opens retain `--fec-roots=2`. The OS table's size and two-root
FEC assertion precede the scan. Forty `dd` calls each read 256 MiB through the
verified OS mapper; read failure calls os_fail/panic. A valid OS mapper status
is required after the scan before verified-root handoff. There is no existing
scan-control option. The unchanged init-bottom hook validates verified mounts,
read-only ext4 lower and RAM OverlayFS before handoff.

Strict is still the default and uses the original accepted BOOT artifact with
the entire scan. Operational is an explicit lab profile: construct a derivative
which appends one uncompressed newc script override to the intact original
initramfs prefix. That script defaults to strict, accepts a single explicit
`cm5_lab_os_scan=operational` parameter, rejects duplicate/invalid settings, and
gates only the scan. Operational logs expressly say the scan was not performed;
the OS status check remains outside the conditional. Neither root, salt, tree,
FEC file nor mount policy changes. No ignore-corruption or unverified fallback.

The independent original BOOT manifest is validated normally and never edited.
Then a separate lab launch policy reconstructs the only allowed derivative
from the hash-pinned original and compares every byte. It also pins the original
kernel. A distinct effective initramfs identity and policy are recorded in
`operational-policy.json`, the BOOT launch record and the result. Passing a
different sidecar manifest cannot accept arbitrary initramfs changes. Strict
rejects derivative arguments. This is a lab substitution after original BOOT
acceptance, not EEPROM firmware execution or acceptance as original V8 BOOT.

Example local commands (each output directory must be fresh):

```bash
umask 077
python3 experiments/cm5-phase10l/lab_profile.py --original "$CM5_L_ORIGINAL" --output "$CM5_L_PRIVATE/operational-artifact"
CM5_PHASE10L_ORIGINAL="$CM5_L_ORIGINAL" python3 -m unittest discover -s experiments/cm5-phase10l -p 'test_*.py' -v
python3 experiments/cm5-phase10j/run.py --fsw "$CM5_L_APPROVED_ELF" --boot-profile operational --operational-initramfs "$CM5_L_PRIVATE/operational-artifact/initramfs-operational" --duration 30 --work "$CM5_L_PRIVATE/operational30"
python3 experiments/cm5-phase10l/assess.py --run "$CM5_L_PRIVATE/operational30" --strict-reference "$CM5_L_STRICT_REFERENCE" --output "$CM5_L_PRIVATE/assessment"
```

Use the existing Phase10J golden/BOOT-manifest options when paths differ.
Without the new profile arguments Phase10J remains strict. Preserve separate
original and derived artifacts. One full Linux guest at a time; no rebuild is
needed for these Python changes. Use `ninja -j2` if a later change needs a build.

The debug channel now participates in selector wakeups while the main console
continues to determine process lifetime. ACK parsing retains frame order,
complete-record framing, one-frame-at-a-time sends and both digest checks.
Temporary selector registration prevents locally open FIFO ends from extending
guest lifetime after QEMU exits. Overall timeout remains unchanged. Host upload
speed improvement is a harness scheduling result, not UART hardware calibration.

`assess.py` preserves separate checks for boot, readiness, verified mounts,
application initialization, housekeeping, internal packets, library probe and
shutdown. Clean RAM-staged execution is explicitly not protected-FSW corruption
survival. See the two design documents for future work. Per-run private
FINAL-SUMMARY.md records exact measured timings, files and validation limits.
