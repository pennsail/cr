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
ssh -p 22 -i "${private_key}" "${node_username}@${node_address}" 'cd ~ && git clone https://github.com/USER/protobuf.git && cd protobuf'

# run setup-cloudlab.sh to setup the hotel app
bash ./setup-cloudlab.sh

# Step 6: Configure Git using the environment variables
ssh -p 22 -i "${private_key}" "${node_username}@${node_address}" << EOF
  git config --global url."git@github.com:".insteadOf "https://github.com/"
  git config --global user.name "${GIT_USERNAME}"
  git config --global user.email "${GIT_USEREMAIL}"
EOF

