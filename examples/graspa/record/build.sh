#!/bin/bash
set -eu
: "${SRC_DIR:?}" "${PREFIX:?}"

# A login shell initializes the site's module command. The user's script runs
# unchanged in the writable build copy, separate from both source and snapshot.
bash -lc '
set -e
cd "$SRC_DIR"
module load PrgEnv-nvidia
command -v nvc++
nvc++ --version
LMOD_PAGER=cat module -t list
bash ./install.sh
test -s nvc_main.x
test -x nvc_main.x
mkdir -p "$PREFIX/bin"
install -m 755 nvc_main.x "$PREFIX/bin/nvc_main.x"
sha256sum "$PREFIX/bin/nvc_main.x"
'
