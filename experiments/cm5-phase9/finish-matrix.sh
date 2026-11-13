#!/bin/sh
# OS1 guest succeeded; its retained result is rechecked for the RS-byte offset.
set -eu
out=experiments/cm5-phase9/artifacts
for case_name in no-fec fsw0; do
 sh experiments/cm5-phase9/run.sh "$case_name" "matrix-$case_name" > "$out/matrix-$case_name.log" 2>&1
done
