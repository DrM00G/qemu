#!/bin/sh
# Continue after the retained launcher-only error; do not repeat passed guests.
set -eu
out=experiments/cm5-phase9/artifacts
for case_name in os1 no-fec fsw0; do
 sh experiments/cm5-phase9/run.sh "$case_name" "matrix-$case_name" > "$out/matrix-$case_name.log" 2>&1
done
