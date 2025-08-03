#!/bin/bash
# this script is run on the cloudlab machine after the k8s cluster is set up
# it will set up the hotelApp and hotelproto repositories

GHZ_VERSION="v0.120.0"
GHZ_FILENAME="ghz-linux-x86_64.tar.gz"
GHZ_URL="https://github.com/bojand/ghz/releases/download/${GHZ_VERSION}/${GHZ_FILENAME}"

# Connect to the remote node
ssh -o StrictHostKeyChecking=no -p 22 -i ${private_key} ${node_username}@${node_address} << 'EOF'

# Clone the hotelApp repository

# Function to check if a directory exists
check_dir_exists() {
    if [ -d "$1" ]; then
        echo "$1 already exists, skipping clone."
        return 1
    else
        return 0
    fi
}

# Add GitHub to known hosts
ssh-keyscan -t rsa github.com >> ~/.ssh/known_hosts


# Navigate to the hotelApp directory
cd $HOME/cr/realtime/hotelApp || { echo "hotelApp directory not found"; exit 1; }

# Delete all Kubernetes services, deployments, and configmaps
kubectl delete svc --all --ignore-not-found
kubectl delete deployments --all --ignore-not-found
kubectl delete configmaps --all --ignore-not-found

# Run the setup-k8s.sh script
if [ -f "setup-k8s-initial.sh" ]; then
    ./setup-k8s-initial.sh hotel
else
    echo "setup-k8s-initial.sh not found."
fi

EOF
