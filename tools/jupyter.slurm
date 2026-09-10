#!/bin/bash
# Run JupyterLab in the `explore` environment on a compute node.
#
#     export FDB5_DIR=/path/to/climateDT/build_intel   # so the kernel finds libfdb5
#     sbatch tools/jupyter.slurm
#     tail -f jupyter-<jobid>.log                      # prints the ssh + URL to use
#
# Submit from the repository root: the job takes the manifest from
# $SLURM_SUBMIT_DIR (override with DESTINE_FDB_ROOT).
#
# Adjust the account and QOS for your project -- `sacctmgr show assoc user=$USER`
# lists what you may use. gp_debug is capped at 2 hours on MN5.
#
# MN5 gpp nodes are shared (OverSubscribe=OK), so you are billed for what you
# ask for, not for the 112-core node. Memory follows the CPU count at 2000 MB
# per allocated CPU -- cpus-per-task=16 lands at ~32 GB, which is the real
# reason to raise it (or to add --mem) before a big H512 read.
#
#SBATCH --job-name=jupyter
#SBATCH --account=ehpc01
#SBATCH --qos=gp_debug
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --time=02:00:00
#SBATCH --output=jupyter-%j.log

set -euo pipefail

REPO="${DESTINE_FDB_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}"
PIXI="${PIXI:-$(command -v pixi || echo "$HOME/.pixi/bin/pixi")}"
ENVIRONMENT="${PIXI_ENV:-explore}"
RUN=("$PIXI" run --manifest-path "$REPO/pixi.toml" -e "$ENVIRONMENT")

# Modules for libfdb5's dependencies, if your build needs them:
#   sbatch --export=ALL,JUPYTER_MODULES="intel impi" tools/jupyter.slurm
if [ -n "${JUPYTER_MODULES:-}" ]; then
    # shellcheck disable=SC2086  # word splitting is the point: "intel impi"
    module load ${JUPYTER_MODULES}
fi

# Slurm exports the submit environment by default, so FDB5_DIR comes along if
# you exported it. LD_LIBRARY_PATH is prepended, never replaced: libfdb5.so
# needs its eckit/metkit siblings next to it.
if [ -n "${FDB5_DIR:-}" ]; then
    export LD_LIBRARY_PATH="$FDB5_DIR/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
else
    echo "warning: FDB5_DIR is not set -- pyfdb will not find libfdb5.so." >&2
    echo "         export it before sbatch if you want to read an FDB." >&2
fi

# A free port on this node, so the instructions printed below are always right
# (hence --port-retries=0: better to fail than to drift to another port).
PORT="${JUPYTER_PORT:-$("${RUN[@]}" python -c \
    'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()')}"
NODE="$(hostname)"

cat <<BANNER

========================================================================
 JupyterLab on ${NODE}:${PORT}   (job ${SLURM_JOB_ID:-?}, ${SLURM_CPUS_PER_TASK:-?} cores)

 On your laptop, forward the port through the login node (same port on
 both ends, so the URL below works verbatim):

     ssh -N -L ${PORT}:${NODE}:${PORT} mn5

 Then open the http://127.0.0.1:${PORT}/lab?token=... URL printed below in
 a browser, or paste it into VSCode: Select Kernel -> Existing Jupyter
 Server (it wants the whole URL, token included).

 The environment is already activated, so no kernelspec is needed here --
 pick the default Python 3 kernel once connected.
========================================================================

BANNER

cd "$REPO"
exec "${RUN[@]}" jupyter lab \
    --no-browser \
    --ip=0.0.0.0 \
    --port="$PORT" \
    --port-retries=0 \
    --ServerApp.root_dir="$REPO"
