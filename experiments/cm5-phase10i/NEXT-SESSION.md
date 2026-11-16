# Phase 10J / approved FSW comparison handoff

Read STATUS.md, README.md, GPIO-SOURCE-CONTRACT.md, the capability manifest and
WORKDAY-READONLY-CAPTURE-PLAN.md first. Also retain H's actual 1MHz PARTIAL and
its timing/concurrency limitations. All work is local AI-assisted experimentation,
not upstream-eligible. No commit/push/reset/clean/stash/destructive checkout.

## Preserve and identify

Branch cm5-rp1-hardware, HEAD872181e1de29acb4c13ffdd8937ee6c9fa7d11bd.
The substantial F.2/G/H changes and new I changes remain uncommitted together.
The I private artifact root is /home/aweso/cm5-v8-lab/phase10i/i-20261116T190606Z.
Its initial source/ checkpoint and source-hashes.json predate substantial edits;
source-manifest.json in each guest run identifies execution sources. Final audit
and status/diff files preserve the full dirty tree. Keep all failed attempts.
Do not mistake pre-guest-source-manifest.json for a prelaunch snapshot: its
metadata explicitly says the first guest had already launched.

One full Linux guest at a time; builds normally-j2. Only fresh regular-file-backed
qcow2 media; protect golden, original kernel/initramfs, physical DTs and roots2
verification metadata. No physical devices/EEPROM/OTP/RPMB or Windows changes.
The requested Downloads assignment was absent; the exact Phase10I assignment was
found under /mnt/c/Users/aweso/projects and privately retained with its hash.

## First priority: requirements before more advertised hardware

Ask the supervisor which approved FSW/build/config/input workload, Linux APIs,
spacecraft simulators, tolerances and retention policy apply. Do not obtain or
explicitly launch proprietary FSW until authorized. In particular distinguish
GPIO cdev/libgpiod from legacy sysfs, gpiomem and direct MMIO. Do not fill UNKNOWN
manifest requirements by guessing. Use the read-only plan for an approved physical
baseline; no physical GPIO request, bus probing or fault/stress campaign belongs
in that baseline. No physical CM5 was accessed in I.

For each approved workload retain separate linux-only, physical and qemu records,
source/build/config hashes, matched input/output contract, fixture identity and
clock-domain semantics. comparison-record.schema.json supplies a small envelope.
Application results and supported device semantics precede timing comparisons.
Internal QEMU FIFO/shifter/scheduler state is not directly observable physically.

## Correctness and capability priorities

1. Audit existing provider outputs advertised by the real rp1-clk driver beyond
   the tested SYS/SLOW subset. Driver registration is not proof those paths work.
   Record unsupported accesses rather than adding fake success to broad stubs.
2. Confirm which GPIO API and pins are actually required. Current opt-in GPIO
   implements only20/21; gpio-reserved-ranges excludes52 of54 compiled descriptors.
   Full54-pin pinctrl/debug, alternate functions, filters and /dev/gpiomem are
   unsupported. Do not bulk-dump pinctrl debug files on this model. A later fuller
   pinctrl implementation needs per-function ownership/resource and IRQ evidence.
3. The loopback is a synthetic unidirectional zero-delay20->21 fixture. SPI0 remains
   independently logically wired, not pinmux-connected. Confirm any approved
   physical fixture before comparing data/waveforms. Source-backed pad/filter/
   synchronizer timing and reset/pull defaults remain unmeasured.
4. Only if needed, consider RP1 I2C1 (DesignWare I2C, clocks, pinmux and native IRQ)
   as the next vertical slice. Ethernet/USB have substantial DMA/PHY/reset/provider
   dependencies. Do not import their physical DT nodes ahead of real hardware.
5. Preserve H delayed-service and all19 I ordering sequences; compare normalized
   protocol/event hashes after any interrupt change. Future SMP IRQ affinity/reset
   interleavings and cdev concurrency require explicit tests. I did not repeat the
   H SMP worker workload; neither four CPUs nor icount proves deterministic MTTCG.

## Completed integration gates

Final i-native10k-03:host10k PASS90/90 strict CS,5 GPIO observations,20 GPIO IRQs.
Final i-fixed100k-01:fixed1ns100k PASS126/126 strict CS,7 GPIO observations,28
GPIO IRQs. Both pass original V8 provenance/verity/active-multi-user/shutdown/
host LOGS and all13 vertical checks. Seven observations versus H's six explain
126 versus108 control messages; no workload or SPI timing definition changed.
The earlier i-native10k-02 remains separate90/90 SPI-only/probe evidence.
I did not repeat1MHz or H SMP stress. Read integration-results.json for exact
source/executable/DT identities and per-vector event counts.

## Run and evaluation details

Use README commands with unique private run basenames; the C boot harness also
creates /home/aweso/cm5-v8-lab/phase10c/<basename>-v8. Keep basenames unique globally.
The I runner flag enables the bounded machine profile and public in-RAM observer.
Default generator remains fallback; arbitrary captured-dtb execution is rejected.
A stopped-machine DT snapshot precedes ARM boot fixups; runtime FDT identity must
be observed, not assumed equal. The contract validates every added GPIO property.

The first guest attempt hit canonical-tty line truncation before observer/SPI
execution. The fix splits embedded source into adjacent short literals; the PTY
regression checks exact bytes/syntax without running device operations on host.
The second attempt passed original V8/SPI but initially treated gpiochip0 and
its gpiochip4 alias as two chips. Discovery now records both and deduplicates by
st_rdev; the third run confirmed identical character-device identities. Do not
weaken line/event/IRQ assertions if future driver discovery fails.

Guest GPIO child ioctls are the original cdev-v1 ABI, exercised inside disposable
QEMU only. Reserved19/22/28/53/54 must reject, duplicate20 must EBUSY,20out and21in
must read1/0/1/0, edge IDs1/2/1/2, IRQ delta4 and no extra event. Parent records
Linux binding, live DT, QOM, SPI, verity, systemd, shutdown and host LOGS separately.
No universal delay knob, new SPI timing convention, record/replay support or
physical maximum-rate claim was introduced.
