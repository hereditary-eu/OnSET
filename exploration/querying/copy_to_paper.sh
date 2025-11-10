#!/bin/sh
target_dir="$HOME/tugraz/cgv/papers/2025/ickg-onset/generated"
target_dir_figures="$target_dir/figures"
target_dir_tables="$target_dir/tables"
mkdir -p $target_dir
mkdir -p $target_dir_figures
mkdir -p $target_dir_tables
cp -r figures/ $target_dir_figures
cp -r tables/ $target_dir_tables