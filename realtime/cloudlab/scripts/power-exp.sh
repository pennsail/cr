#!/usr/bin/env bash
set -euo pipefail

# Parse command line arguments
METHOD=""
LOW_ONLY=false
NO_CONTROL_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --low)
            LOW_ONLY=true
            shift
            ;;
        --no-control)
            NO_CONTROL_ONLY=true
            shift
            ;;
        compose|search-hotel)
            METHOD=$1
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 <METHOD> [--low] [--no-control]"
            echo "METHOD: compose or search-hotel"
            echo "--low: only run lowest load for each method"
            echo "--no-control: only run no-control scenarios"
            exit 1
            ;;
    esac
done

if [ -z "$METHOD" ]; then
    echo "Usage: $0 <METHOD> [--low] [--no-control]"
    echo "METHOD: compose or search-hotel"
    echo "--low: only run lowest load for each method"
    echo "--no-control: only run no-control scenarios"
    exit 1
fi

export METHOD
OVERLOAD_SCRIPT=./cloudlab/scripts/overload-experiments.sh

# 0) Unset any existing power cap
echo "🔌 Unsetting any existing power cap…"
python3 cloudlab/scripts/host/power_management.py uncap

# prepare logs
LOGDIR=logs
mkdir -p "$LOGDIR"

# Set warmup load based on method
if [ "$METHOD" = "search-hotel" ]; then
    export WARMUP_LOAD=4000
    CONTROL_LOADS=(7000 8000 9000)
    NO_CONTROL_LOADS=(6000 7000 8000)
else  # compose
    export WARMUP_LOAD=1000
    CONTROL_LOADS=(5000 6000 7000)
    NO_CONTROL_LOADS=(3000 4000)
fi

# Apply --low flag: only use lowest load for each scenario
if [ "$LOW_ONLY" = true ]; then
    if [ "$METHOD" = "search-hotel" ]; then
        CONTROL_LOADS=(7000)
        NO_CONTROL_LOADS=(6000)
    else  # compose
        CONTROL_LOADS=(5000)
        NO_CONTROL_LOADS=(3000)
    fi
    echo "🔽 LOW mode: Using lowest loads only"
fi

# Apply --no-control flag: clear control loads
if [ "$NO_CONTROL_ONLY" = true ]; then
    CONTROL_LOADS=()
    echo "🚫 NO-CONTROL mode: Skipping all control scenarios"
fi

# Combine all unique loads for the outer loop
ALL_LOADS=($(printf "%s\n" "${CONTROL_LOADS[@]}" "${NO_CONTROL_LOADS[@]}" | sort -nu))

echo "📊 Experiment configuration:"
echo "   Method: $METHOD"
echo "   Control loads: ${CONTROL_LOADS[*]:-none}"
echo "   No-control loads: ${NO_CONTROL_LOADS[*]:-none}"
echo "   All loads to test: ${ALL_LOADS[*]}"

# K8s initialization
echo "🚀 Initializing k8s for method: $METHOD"
# REMOTE_NODE=$(head -n1 ~/cloudlab_nodes.txt)
if [ "$METHOD" = "search-hotel" ]; then
    ssh -p 22 -i "${private_key}" "${node_username}@${node_address}" "cd hotelApp && ./setup-k8s-initial.sh hotel"
else  # compose
    ssh -p 22 -i "${private_key}" "${node_username}@${node_address}" "cd hotelApp && ./setup-k8s-initial.sh"
fi

# Loop over all test loads
for TEST_LOAD in "${ALL_LOADS[@]}"; do
  echo
  echo "===== TEST_LOAD=${TEST_LOAD} ====="

  # Loop over power caps: 10,20,…,100,105
  # for POWER_CAP in {20..100..5} 105; do
  # actually, let's make denser on small caps and looser on large caps. for example:
  # below 60W, use 3W increments; above 60W, use 20W increments
  for POWER_CAP in {15..25..2} 105; do
  # for POWER_CAP in {15..60..5} {70..100..15} 105; do
    # strip any decimal part
    CAP_INT=${POWER_CAP%.*}

    echo
    echo "⚡ Applying power cap = ${CAP_INT}W"
    python3 cloudlab/scripts/host/power_management.py cap -c ${CAP_INT}

    export TEST_LOAD
    export POWER_CAP
    export LOAD_INCREASE=true

    # Check if this load should run no-control
    if [[ " ${NO_CONTROL_LOADS[@]} " =~ " ${TEST_LOAD} " ]]; then
      # 1) No-control run
      NO_CONTROL_OPT="-c ${TEST_LOAD}"
      LOG_NOCTRL="${LOGDIR}/noctrl-load${TEST_LOAD}-cap${CAP_INT}.log"
      echo "▶ No-control: load=${TEST_LOAD}, cap=${CAP_INT} → $LOG_NOCTRL"
      export OVERLOAD_CONTROL=none
      if bash "$OVERLOAD_SCRIPT" $NO_CONTROL_OPT >"$LOG_NOCTRL" 2>&1; then
        echo "✔ No-control succeeded"
      else
        echo "✖ No-control FAILED (see $LOG_NOCTRL)"
      fi
    fi

    # Check if this load should run control
    if [[ " ${CONTROL_LOADS[@]} " =~ " ${TEST_LOAD} " ]]; then
      # 2) Control run
      if [ "$METHOD" = "search-hotel" ]; then
        CONTROL_OPT="-c ${TEST_LOAD} --control --param control_search-hotel_params.json"
      else  # compose
        CONTROL_OPT="-c ${TEST_LOAD} --control --param control_compose_params.json"
      fi
      LOG_CTRL="${LOGDIR}/ctrl-load${TEST_LOAD}-cap${CAP_INT}.log"
      echo "▶   Control: load=${TEST_LOAD}, cap=${CAP_INT} → $LOG_CTRL"
      export OVERLOAD_CONTROL=control 
      if bash "$OVERLOAD_SCRIPT" $CONTROL_OPT >"$LOG_CTRL" 2>&1; then
        echo "✔ Control succeeded"
      else
        echo "✖ Control FAILED (see $LOG_CTRL)"
      fi
    fi

  done
done

echo
echo "✅ All tests complete. Logs under $LOGDIR/"
