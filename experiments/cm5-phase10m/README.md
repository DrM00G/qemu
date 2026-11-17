# Private Phase10M persistent verified FSW baseline

Local experiment only; never include these AI-assisted sources in upstream
contributions. No QEMU hardware model changes, physical storage, host block
device operations, work-PC changes or corruption injection.

`seal.py` prepares an intentionally requested generation once. It validates the
original full-eMMC/ELF identities and actual partition table against Phase10L,
checks capacity and offline clean/free filesystem prerequisites, then edits
exclusively owned regular-file copies. It installs the ELF in FSW, verifies its
readback/permissions, generates new verity/FEC metadata, and updates RECOVERY's
FSW hash, parity, root and SHA256SUMS. All OS verification files and every image
byte outside FSW/RECOVERY are compared with the original. Original captures and
accepted exports are never opened for write. Commands and failed stages remain.

The sealed raw image is a distinct lab artifact, NOT the original golden.
BOOT stays unchanged. The effective lab initramfs is a separate explicit
substitution: original byte prefix + Phase10L scan-policy override + the new
FSW root pin. OS pin, FEC, original kernel and late handoff assertions remain.
This artifact set must be launched together; the unchanged firmware-selected
BOOT initramfs alone still contains the old FSW root and is not the new seal's
effective initramfs. No physical EEPROM execution or secure-firmware claim.

`generation.json` v1 binds the image, installed ELF identity, FSW root/tree/FEC,
effective initramfs, original BOOT manifest/kernel, verification parameters,
partition geometry, preservation proofs, source provenance and clean-baseline
contract. Its canonical content generation ID and independently retained full
manifest SHA256 prevent silent mixing. Artifacts are sealed without write bits;
the harness additionally checks their content identities. This is trusted local
acceptance, not a signed deployment authority. Do not hash an arbitrary edited
manifest and use that new digest as acceptance.

Example generation preparation, with private prerequisite variables populated
from the accepted Phase10L inventory:

```bash
umask 077
python3 experiments/cm5-phase10m/seal.py --golden "$CM5_M_GOLDEN" --fsw "$CM5_M_APPROVED_ELF" --original-initramfs "$CM5_M_ORIGINAL_INITRAMFS" --boot-expected "$CM5_M_BOOT_MANIFEST" --inventory "$CM5_M_PHASE10L_INVENTORY" --output "$CM5_M_FRESH_GENERATION"
```

Retain the printed manifest SHA256 outside the generation's mutable working
context. New builds may differ because filesystem timestamps, metadata and
generation time are recorded; reuse the accepted generation instead of resealing
on every case. A new FSW version needs intentional staging/sealing authorization
and a versioned policy update; normal experiment mode never installs an ELF.

Each case creates a fresh QCOW2 child:

```bash
python3 experiments/cm5-phase10j/run.py --execution-mode verified-fsw-partition --sealed-generation "$CM5_M_MANIFEST" --generation-sha256 "$CM5_M_ACCEPTED_MANIFEST_SHA" --boot-profile operational --duration 30 --work "$CM5_M_FRESH_CASE"
python3 experiments/cm5-phase10m/assess.py --run "$CM5_M_FRESH_CASE" --generation "$CM5_M_MANIFEST" --generation-sha256 "$CM5_M_ACCEPTED_MANIFEST_SHA" --phase10l-reference "$CM5_M_PHASE10L_RUN" --output "$CM5_M_FRESH_ASSESSMENT"
```

The existing outer comparison intentionally returns PARTIAL/shell 1 for physical
equivalence; inspect the independent clean verified-FSW assessment. Original
strict and Phase10L RAM-staged operational commands remain supported. Direct
mode forbids `--fsw`; it accepts no ELF upload or RAM fallback. It sends only a
small checksum-verified control script and waits for the same readiness and
timeout contracts. Normal `/run` remains noexec; writable working data can live
there, while `/opt/fsw/RpiDeployment.elf` is executed directly as root.

The guest validates both mappings/root identities and verified read-only mounts,
checks path/inode metadata, and captures `/proc/child/exe`, argv and executable
mapping evidence. It does NOT read/hash the whole ELF before launch. Linux
exec/loader/demand paging therefore supplies the executable through real
dm-verity/FEC. Boot, mount, loader, launch, initialization and operation outcomes
remain separate; expected absent external fixtures are not synthetic successes.

The manifest's expected contract is immutable. A separate hashed baseline
acceptance receipt binds observed clean results to it without rewriting the
generation after a guest run. Private FINAL-SUMMARY.md records exact artifacts,
timings, commands, preserved failures and tests. Keep all raw evidence outside
the checkout. One full Linux guest at a time; no rebuild needed here, and use
`ninja -j2` for any later required build. See the batch and campaign documents
for explicitly unimplemented future work.
