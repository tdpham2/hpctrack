#!/bin/bash
set -eu
: "${SRC_URL:?}" "${SRC_REF:?}" "${PREFIX:?}"

# Needs only uv on PATH and network access from the build host. uv installs the
# pinned commit directly, so no clone or site modules are involved.
command -v uv >/dev/null || { echo "uv not found on PATH" >&2; exit 1; }
uv --version
uv venv --python 3.12 "$PREFIX/venv"
python="$PREFIX/venv/bin/python"
uv pip install --python "$python" \
    "mace-torch @ git+$SRC_URL@$SRC_REF" \
    "git+https://github.com/WillBaldwin0/graph_electrostatics.git@v0.4.4"
uv pip freeze --python "$python"

# Compute nodes may lack internet access; fetch the checkpoint into the prefix.
XDG_CACHE_HOME="$PREFIX/cache" "$python" -c \
    'from mace.calculators import mace_polar; mace_polar(model="polar-1-m", device="cpu")'
find "$PREFIX/cache" -type f -exec sha256sum {} +
