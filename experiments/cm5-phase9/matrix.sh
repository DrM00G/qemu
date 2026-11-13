#!/bin/sh
# Serial workload schedule: avoid reproducing host contention accidentally.
set -eu
out=experiments/cm5-phase9/artifacts
while [ ! -f "$out/repro-before-2/result.json" ]; do sleep 2; done
sh experiments/cm5-phase9/run.sh reproduce repro-after > "$out/repro-after.log" 2>&1
for case_name in clean os0 os1 no-fec fsw0; do
 sh experiments/cm5-phase9/run.sh "$case_name" "matrix-$case_name" > "$out/matrix-$case_name.log" 2>&1
done
