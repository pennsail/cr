#!/bin/bash
# power_management.sh - Script for power management operations
# This script can initialize RAPL, set/unset power caps, and measure power usage

set -e  # Exit on error

# Default values
POWER_CAP=""
DURATION=60  # Default measurement duration in seconds
OUTPUT_DIR="./power_measurements"
ACTION=""

# Function to display usage information
usage() {
    echo "Usage: $0 [OPTIONS] ACTION"
    echo
    echo "Actions:"
    echo "  init      Initialize power management tools (RAPL, PCM)"
    echo "  cap       Set a power cap for the current node"
    echo "  uncap     Remove power cap for the current node"
    echo "  status    Show current power cap and available range"
    echo "  measure   Measure power usage for the current node"
    echo
    echo "Options:"
    echo "  -c, --cap VALUE    Power cap in watts (required for 'cap' action)"
    echo "  -d, --duration SEC Duration for measurement in seconds (default: 60)"
    echo "  -o, --output DIR   Output directory for measurements (default: ./power_measurements)"
    echo "  -h, --help         Display this help message"
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        init|cap|uncap|status|measure)
            ACTION="$1"
            shift
            ;;
        -c|--cap)
            POWER_CAP="$2"
            shift 2
            ;;
        -d|--duration)
            DURATION="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Check if action is specified
if [ -z "$ACTION" ]; then
    echo "Error: No action specified"
    usage
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to initialize power management tools
init_power_management() {
    echo "Initializing power management tools..."
    
    # Install necessary packages
    sudo apt-get update
    sudo apt-get install -y linux-tools-common linux-tools-generic linux-tools-$(uname -r) \
        build-essential git cmake libboost-all-dev

    # Check if RAPL is available
    if [ -d "/sys/class/powercap/intel-rapl" ]; then
        echo "RAPL is available on this system."
    else
        echo "Warning: RAPL is not available on this system. Power capping may not work."
        exit 1
    fi

    # Install PCM - assume you installed pcm with install_pcm_legacy from dvfs py
    echo 'passive' | sudo tee /sys/devices/cpu/intel_pstate/status

    # Enable MSR module if not loaded
    if ! lsmod | grep -q msr; then
        echo "Loading MSR module..."
        sudo modprobe msr
    fi

    echo "Power management tools initialized successfully."
}

# Function to set power cap
set_power_cap() {
    if [ -z "$POWER_CAP" ]; then
        echo "Error: Power cap value not specified. Use -c or --cap option."
        exit 1
    fi

    echo "Setting power cap to $POWER_CAP watts..."
    
    # Check if RAPL is available
    if [ ! -d "/sys/class/powercap/intel-rapl" ]; then
        echo "Error: RAPL is not available on this system."
        exit 1
    fi

    # Find all RAPL domains for package (socket)
    for pkg_dir in /sys/class/powercap/intel-rapl:*; do
        if [[ "$pkg_dir" == *":*"* ]]; then
            echo "No RAPL domains found."
            exit 1
        fi
        
        # Get the max power constraint
        max_power_uw=$(cat "$pkg_dir/constraint_0_max_power_uw")
        
        # Convert watts to microwatts
        power_cap_uw=$(echo "$POWER_CAP * 1000000" | bc)
        
        # Check if requested cap is within limits
        if (( power_cap_uw > max_power_uw )); then
            echo "Warning: Requested power cap ($POWER_CAP W) exceeds maximum ($((max_power_uw/1000000)) W). Setting to maximum."
            power_cap_uw=$max_power_uw
        fi
        
        # Set the power cap
        echo "$power_cap_uw" | sudo tee "$pkg_dir/constraint_0_power_limit_uw" > /dev/null
        
        # Enable the constraint
        echo 1 | sudo tee "$pkg_dir/enabled" > /dev/null
        
        echo "Power cap set for $(basename "$pkg_dir"): $POWER_CAP watts"
    done
}

# Function to remove power cap
remove_power_cap() {
    echo "Removing power cap..."
    
    # Check if RAPL is available
    if [ ! -d "/sys/class/powercap/intel-rapl" ]; then
        echo "Error: RAPL is not available on this system."
        exit 1
    fi

    # Find all RAPL domains for package (socket)
    for pkg_dir in /sys/class/powercap/intel-rapl:*; do
        if [[ "$pkg_dir" == *":*"* ]]; then
            echo "No RAPL domains found."
            exit 1
        fi
        
        # Get the max power constraint
        max_power_uw=$(cat "$pkg_dir/constraint_0_max_power_uw")
        
        # Set the power cap to maximum (effectively removing the cap)
        echo "$max_power_uw" | sudo tee "$pkg_dir/constraint_0_power_limit_uw" > /dev/null
        
        echo "Power cap removed for $(basename "$pkg_dir")"
    done
}

# Function to show power cap status
show_power_status() {
    echo "Power cap status:"
    
    # Check if RAPL is available
    if [ ! -d "/sys/class/powercap/intel-rapl" ]; then
        echo "Error: RAPL is not available on this system."
        exit 1
    fi

    # Find all RAPL domains for package (socket)
    for pkg_dir in /sys/class/powercap/intel-rapl:*; do
        if [[ "$pkg_dir" == *":*"* ]]; then
            echo "No RAPL domains found."
            exit 1
        fi
        
        pkg_name=$(basename "$pkg_dir")
        
        # Read current power limit
        current_limit_uw=$(cat "$pkg_dir/constraint_0_power_limit_uw")
        current_limit_w=$((current_limit_uw / 1000000))
        
        # Read max power limit
        max_limit_uw=$(cat "$pkg_dir/constraint_0_max_power_uw")
        max_limit_w=$((max_limit_uw / 1000000))
        
        # Check if enabled
        enabled=$(cat "$pkg_dir/enabled")
        
        echo "  $pkg_name:"
        echo "    Current limit: $current_limit_w W"
        echo "    Maximum limit: $max_limit_w W"
        echo "    Enabled: $enabled"
    done
}

# Function to measure power usage
measure_power() {
    echo "Measuring power usage for $DURATION seconds..."
    
    # Create output directory if it doesn't exist
    mkdir -p "$OUTPUT_DIR"
    
    # Get hostname for the output file
    HOSTNAME=$(hostname)
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    OUTPUT_FILE="$OUTPUT_DIR/${HOSTNAME}_power_${TIMESTAMP}.csv"
    
    # Check if PCM is installed
    if ! command_exists pcm-power; then
        echo "Error: PCM is not installed. Run with 'init' action first."
        exit 1
    fi
    
    # Run PCM power measurement
    echo "Starting power measurement, saving to $OUTPUT_FILE"
    # Calculate iterations: duration * 10 (since we sample every 0.1 seconds)
    ITERATIONS=$((DURATION * 10))
    sudo pcm-power 0.1 -i=$ITERATIONS -csv="$OUTPUT_FILE"
    
    echo "Power measurement completed. Results saved to $OUTPUT_FILE"
    
    # Display a summary of the results
    echo "Summary of power measurements:"
    tail -n 1 "$OUTPUT_FILE" | tr ',' ' ' | awk '{print "Socket 0 power:", $3, "W, Socket 1 power:", $4, "W, Total CPU power:", $3+$4, "W"}'
}

# Execute the requested action
case "$ACTION" in
    init)
        init_power_management
        ;;
    cap)
        set_power_cap
        ;;
    uncap)
        remove_power_cap
        ;;
    status)
        show_power_status
        ;;
    measure)
        measure_power
        ;;
    *)
        echo "Error: Invalid action '$ACTION'"
        usage
        ;;
esac

exit 0