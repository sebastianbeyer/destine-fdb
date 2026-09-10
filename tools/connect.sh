#!/usr/bin/env bash
# Connect this laptop to a JupyterLab job running on the HPC.
#
# Finds your running `jupyter` job, reads the node, port and token out of its
# log, opens the port forward and prints the URL to paste into a browser or
# into VSCode (Select Kernel -> Existing Jupyter Server).
#
#     ./tools/connect.sh                 # tunnel, print URL, stay in foreground
#     ./tools/connect.sh --open          # also open it in a browser
#     ./tools/connect.sh --local-port 8899   # if the remote port is taken here
#
# Ctrl-C closes the tunnel; the job keeps running (scancel it yourself).
#
# Environment: MN5_HOST (ssh alias, default "mn5"), REMOTE_DIR (repo on the
# HPC, default "destine-fdb"), JOB_NAME (default "jupyter").

set -euo pipefail

HOST="${MN5_HOST:-mn5}"
REMOTE_DIR="${REMOTE_DIR:-destine-fdb}"
JOB_NAME="${JOB_NAME:-jupyter}"
LOCAL_PORT=""
OPEN_BROWSER=0

while [ $# -gt 0 ]; do
    case "$1" in
        --open) OPEN_BROWSER=1; shift ;;
        --local-port) LOCAL_PORT="$2"; shift 2 ;;
        --host) HOST="$2"; shift 2 ;;
        --remote-dir) REMOTE_DIR="$2"; shift 2 ;;
        -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

# Newest running job of that name. %A is the job id, %N the node it landed on.
# shellcheck disable=SC2029  # JOB_NAME is meant to expand here, $USER remotely
read -r JOBID NODE <<<"$(ssh -o ClearAllForwardings=yes "$HOST" \
    "squeue -h -u \$USER -n '$JOB_NAME' -t RUNNING -S -V -o '%A %N'" | head -1)"

if [ -z "${JOBID:-}" ]; then
    echo "no running '$JOB_NAME' job on $HOST." >&2
    echo "start one with:" >&2
    echo "    ssh $HOST 'export FDB5_DIR=...; cd $REMOTE_DIR && sbatch tools/jupyter.slurm'" >&2
    exit 1
fi

# The token line appears a few seconds after the job starts, so give it a while.
echo "job $JOBID on $NODE -- waiting for the server to come up..." >&2
# shellcheck disable=SC2029  # REMOTE_DIR/JOBID expand here on purpose
URL="$(ssh -o ClearAllForwardings=yes "$HOST" "
    for _ in \$(seq 60); do
        url=\$(grep -o 'http://127.0.0.1:[0-9]*/lab?token=[0-9a-f]*' \
              '$REMOTE_DIR/jupyter-$JOBID.log' 2>/dev/null | tail -1)
        if [ -n \"\$url\" ]; then echo \"\$url\"; exit 0; fi
        sleep 2
    done
    exit 1
")" || { echo "no token URL in $REMOTE_DIR/jupyter-$JOBID.log after 2 minutes" >&2; exit 1; }

REMOTE_PORT="${URL#http://127.0.0.1:}"
REMOTE_PORT="${REMOTE_PORT%%/*}"
TOKEN="${URL#*token=}"
: "${LOCAL_PORT:=$REMOTE_PORT}"

if command -v nc >/dev/null 2>&1 && nc -z 127.0.0.1 "$LOCAL_PORT" 2>/dev/null; then
    echo "local port $LOCAL_PORT is already in use." >&2
    echo "another tunnel may already be up, or pick one: --local-port <n>" >&2
    exit 1
fi

LOCAL_URL="http://127.0.0.1:${LOCAL_PORT}/lab?token=${TOKEN}"

# Note: no ExitOnForwardFailure. It applies to *every* forward, including any
# RemoteForward your ssh config sets for this host -- one of those failing
# would take the tunnel down with it. Instead the forward runs in the
# background and we check the local port ourselves.
ssh -N -L "${LOCAL_PORT}:${NODE}:${REMOTE_PORT}" "$HOST" &
SSH_PID=$!
trap 'kill "$SSH_PID" 2>/dev/null || true' EXIT INT TERM

for _ in $(seq 30); do
    if ! kill -0 "$SSH_PID" 2>/dev/null; then
        echo "ssh exited before the forward came up" >&2
        exit 1
    fi
    if ! command -v nc >/dev/null 2>&1; then sleep 2; break; fi
    if nc -z 127.0.0.1 "$LOCAL_PORT" 2>/dev/null; then break; fi
    sleep 1
done

cat <<BANNER

  job ${JOBID} on ${NODE}, forwarding ${LOCAL_PORT} -> ${NODE}:${REMOTE_PORT}

  ${LOCAL_URL}

  Paste that into a browser, or into VSCode: Select Kernel -> Existing
  Jupyter Server. Ctrl-C here closes the tunnel; the job keeps running.

BANNER

if [ "$OPEN_BROWSER" = 1 ]; then
    if command -v open >/dev/null 2>&1; then open "$LOCAL_URL"
    elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$LOCAL_URL"
    fi
fi

wait "$SSH_PID"
