#!/bin/bash

# Step 1: Source envs.sh
source ./envs.sh

# Step 2: Upload SSH key
scp -P 22 -i "${private_key}" "${GIT_KEY_PATH}" "${node_username}@${node_address}:~/.ssh/cloudlab"

# Step 3: Write SSH config
ssh -p 22 -i "${private_key}" "${node_username}@${node_address}" 'cat << EOF > ~/.ssh/config
Host github.com
    IdentityFile ~/.ssh/cloudlab
    IdentitiesOnly yes
    Hostname ssh.github.com
    Port 443
EOF'

# Step 4: Clone repository
# ssh -p 22 -i "${private_key}" "${node_username}@${node_address}" 'cd ~ && git clone https://github.com/USER/protobuf.git && cd protobuf'

# run setup-cloudlab.sh to setup the hotel app
bash ./setup-cloudlab.sh

# Step 6: Configure Git using the environment variables
ssh -p 22 -i "${private_key}" "${node_username}@${node_address}" << EOF
  git config --global url."git@github.com:".insteadOf "https://github.com/"
  git config --global user.name "${GIT_USERNAME}"
  git config --global user.email "${GIT_USEREMAIL}"
EOF

scp_file_transfer() {
    local src=$1
    local dest=$2

    if [[ "$src" == *"${node_username}@${node_address}"* ]]; then
        local dest_dir=$(dirname "$dest")
        mkdir -p "$dest_dir"
        scp -P 22 -i "${private_key}" "$src" "$dest"
    else
        local remote_dest="${node_username}@${node_address}:$dest"
        scp -P 22 -i "${private_key}" "$src" "$remote_dest"
    fi
    
    if [ $? -ne 0 ]; then
        echo "SCP command failed. Exiting."
        exit 1
    fi
}

PROTO_DIR="./hotelApp"

scp_file_transfer "$PROTO_DIR/ghz-client/run_client_cloudlab.sh" "~/protobuf/ghz-client/run_client_cloudlab.sh"
scp_file_transfer "$PROTO_DIR/ghz-client/clientcall" "~/protobuf/ghz-client/clientcall"
# copy all proto files to the ghz-client directory
for proto_file in $(find "$PROTO_DIR" -name "*.proto"); do
    scp_file_transfer "$proto_file" "~/protobuf/"
done

  