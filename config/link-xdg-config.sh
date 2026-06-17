#!/usr/bin/env sh
set -eu

APP_NAME="kimp3"
PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
XDG_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}"
TARGET_DIR="$XDG_ROOT/$APP_NAME"

mkdir -p "$TARGET_DIR"
ln -sfn "$PROJECT_DIR/config/config.example.yaml" "$TARGET_DIR/config.yaml"
ln -sfn "$PROJECT_DIR/config/logging.example.yaml" "$TARGET_DIR/logging.yaml"

printf 'Linked %s/config.yaml -> %s/config/config.example.yaml\n' "$TARGET_DIR" "$PROJECT_DIR"
printf 'Linked %s/logging.yaml -> %s/config/logging.example.yaml\n' "$TARGET_DIR" "$PROJECT_DIR"
