#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin="$HOME/.venvs/s6-training/bin/python"
results_dir="$project_root/results/fruitfly_poisoning/multiseed_v1"
mkdir -p "$results_dir"
cd "$project_root"

for seed in 2027 2028; do
  for job in \
    label_flip_10__untreated \
    label_flip_10__semantic \
    label_flip_10__weighted_50 \
    targeted_0_to_1__untreated \
    targeted_0_to_1__semantic \
    targeted_0_to_1__weighted_25; do
    printf 'START %s seed=%s\n' "$job" "$seed" >> "$results_dir/batch.log"
    "$python_bin" -u s6/data_poisoning/train_fruitfly_repeat_v1.py \
      --job "$job" --seed "$seed" >> "$results_dir/batch.log" 2>&1
    printf 'FINISHED %s seed=%s\n' "$job" "$seed" >> "$results_dir/batch.log"
  done
done
printf 'BATCH COMPLETE\n' >> "$results_dir/batch.log"
