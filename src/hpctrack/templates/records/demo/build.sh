#!/bin/bash
set -eu
mkdir -p "$PREFIX/bin"
cp "$SRC_DIR/calculate.py" "$PREFIX/bin/calculate.py"
