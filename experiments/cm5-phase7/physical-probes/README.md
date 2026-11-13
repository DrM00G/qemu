# Read-only physical CM5 collection

These tools are prepared for the official CM5 I/O Board. **They have not been
run on the physical CM5.** Test fixtures and emulator data are not measurements.
Python 3 and its standard library are sufficient; Raspberry Pi, PCI, GPIO,
I2C, device-mapper and systemd utilities are optional.

On the board, choose a fresh approved evidence directory:

```sh
python3 collect.py --output /approved/private-evidence/cm5-friday
```

Run as the ordinary operator first if appropriate. Root may be necessary to
read dmesg, firmware or pinmux views; the script does not invoke sudo or install
anything. Permission failures, absent utilities and unsupported options are
recorded as `UNAVAILABLE` in manifest.json. A partial DT copy is not treated as
a complete hardware description. No active probe stimulus is performed.

The only writes are new output files. The output directory/raw directory are
mode 0700 and files use umask 077. Use restricted local storage, not an automatic
public upload or shared directory. Raw data can contain serials, MAC/IP addresses,
UUIDs, kernel command-line secrets, mount credentials, paths or application/unit
names. **Keep raw/ private until manually reviewed.** Do not paste raw logs into
an analysis report. The scripts do not read proprietary FSW source, binaries or
arbitrary filesystem contents.

Collected observations:

* Kernel release/page size, CPU/memory metadata and complete readable live DT.
* PCI topology, standard configuration/resource descriptions and driver links.
* Two interrupt-counter snapshots, one second apart, without generating traffic.
* SPI/UART/I2C/GPIO exposure; read-only pinmux views when tools are installed.
* MMC host driver links, block/partition geometry/labels, mounts and dm status.
* Phase 8: translated SDHCI host/cfg ranges and declared DT capabilities;
  logical sector sizes; passive MMC host topology, exposed clock/capability
  descriptors, and `/sys/kernel/debug/mmc*/ios` **only if already readable**.
  The latter can show negotiated timing, clock and width. Missing fields remain
  `UNAVAILABLE`; do not mount debugfs or load a module to obtain them. No card
  CID/EXT_CSD/RPMB command or raw filesystem sector read is added.
* Kernel boot log, systemd timing, critical chain and failed units.
* Read-only firmware and bootloader version/configuration via vcgencmd.

Important exclusions: no devmem, PCI resource mmap, setpci, unknown MMIO reads,
SPI transfers, I2C address scans, gpioget line requests, GPIO outputs/configuration,
clock changes, EEPROM apply/update/reflash, service changes, remount, reboot,
filesystem repair, verity/corruption sweeps, raw disk writes or package installation.
`i2cdetect -l` lists existing adapters only; `-y` scans are not used.
`pinctrl get`, `raspi-gpio get` and `gpioinfo` query existing state only.
No debugfs/tracefs is mounted or enabled. Physical register snapshots with unknown
read side effects are deferred to the reviewed Friday procedure.

`facts.json` contains allowlisted descriptor values only. It omits DT serial,
MAC, bootargs, raw log text, private labels, UUIDs, arbitrary driver strings and
network addresses. Full kernel suffix stays raw; only numeric kernel version is
included. A device-node count is explicitly exposure, not proof of transfer.
Live DT descriptions and actual driver bindings are separate evidence types.
MMC geometry is grouped by recognized BOOT/OS/FSW/LOGS/RECOVERY roles; filenames
and UUIDs do not enter the report. Unknown roles remain unavailable.

After reviewing facts, compare it to the emulator description using
`../compare-hardware.py`. That tool reads facts only, never raw/. It additionally
rejects non-allowlisted values. Its structured output includes physical/QEMU
values, status, evidence pointer/kind, QEMU implementation path, impact and next
action. A `MATCH` is descriptor equality, not electrical or recovery validation.
GIC compatible aliases and RP1 driver naming aliases are normalized.

Live DT cannot determine MIP reset/clear/level/VPU behavior or physical FIFO
reset/synthesis details. Missing such evidence stays UNAVAILABLE. See
[Friday questions](../FRIDAY-HARDWARE-QUESTIONS.md) for conditional methods and
safety/equipment requirements.
