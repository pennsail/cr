#!/bin/bash -ex

LOC=$(dirname $(realpath "$0"))

sudo apt-get update
sudo apt install -y make build-essential libssl-dev zlib1g-dev \
  libbz2-dev libreadline-dev libsqlite3-dev wget curl llvm \
  libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev

sudo apt install -y mosh htop redis-tools

# install the msr-tools package
sudo apt install -y msr-tools

sleep 2
sudo modprobe msr

# Disable Turbo Boost
if [[ -z $(which rdmsr) ]]; then
    echo "msr-tools is not installed. Run 'sudo apt-get install msr-tools' to install it." >&2
    exit 1
fi

if [[ ! -z $1 && $1 != "enable" && $1 != "disable" ]]; then
    echo "Invalid argument: $1" >&2
    echo ""
    echo "Usage: $(basename $0) [disable|enable]"
    exit 1
fi

cores=$(cat /proc/cpuinfo | grep processor | awk '{print $3}')
for core in $cores; do
    if [[ $1 == "disable" ]]; then
        sudo wrmsr -p${core} 0x1a0 0x4000850089
    fi
    if [[ $1 == "enable" ]]; then
        sudo wrmsr -p${core} 0x1a0 0x850089
    fi
    state=$(sudo rdmsr -p${core} 0x1a0 -f 38:38)
    if [[ $state -eq 1 ]]; then
        echo "core ${core}: disabled"
    else
        echo "core ${core}: enabled"
    fi
done

sleep 2
# Set CPU governor to performance

sudo apt-get install -y linux-tools-common linux-tools-$(uname -r)
# Permanently disable Swap
sudo sed -i '/ swap / s/^/#/' /etc/fstab
sudo swapoff -a


rm -rf /users/$USER/.pyenv
# python3, we need 3.7+
curl https://pyenv.run | bash
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
export PYENV_ROOT="$HOME/.pyenv"
command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
pyenv install 3.10.8 -f
pyenv global 3.10.8
pip3 install -r "$HOME"/cr/realtime/cloudlab/requirements.txt

# golang
sudo rm -rf /usr/local/go
curl -OL https://go.dev/dl/go1.20.linux-amd64.tar.gz
sudo tar -C /usr/local -xvf go1.20.linux-amd64.tar.gz
# rm go1.19.3.linux-amd64.tar.gz
rm go1.20.linux-amd64.tar.gz
echo "export PATH=$PATH:/usr/local/go/bin" >> "$HOME"/.bashrc

# k8s + containerd
sudo apt-get install -y apt-transport-https ca-certificates curl

# Ensure the keyring directory exists
sudo mkdir -p /etc/apt/keyrings

# Get the default user group
USER_GROUP=$(id -gn)

# Print the default user group to the console
echo "The default user group is: $USER_GROUP"

# Create .gnupg directory if it doesn't exist and set permissions
mkdir -p ~/.gnupg
sudo chown -R $USER:$USER_GROUP ~/.gnupg
chmod 700 ~/.gnupg
# Only chmod files if they exist
if [ -n "$(ls -A ~/.gnupg 2>/dev/null)" ]; then
    chmod 600 ~/.gnupg/*
fi

# Add Docker GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
# Add Docker repository for containerd.io
sudo add-apt-repository -y "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
# Add Kubernetes GPG key
# curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.28/deb/Release.key | sudo gpg --dearmor --yes -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
# Add Kubernetes repository
# echo "deb https://apt.kubernetes.io/ kubernetes-xenial main" | sudo tee /etc/apt/sources.list.d/kubernetes.list
echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.28/deb/ /' | sudo tee /etc/apt/sources.list.d/kubernetes.list
# Update package information again
sudo apt update
# Install Kubernetes components and containerd.io
sudo apt install -y kubelet kubeadm kubectl containerd.io

# disable swap
sudo swapoff -a

# enable cri for containerd
sudo sed -i '/disabled_plugins/s/^/#/' /etc/containerd/config.toml
sudo systemctl restart containerd

# enable br_netfilter
sudo modprobe br_netfilter

# node
sudo apt-get install -y ca-certificates curl gnupg
sudo mkdir -p /etc/apt/keyrings
chmod 700 -R ~/.gnupg
# sudo rm /etc/apt/keyrings/nodesource.gpg if exists
if [ -f /etc/apt/keyrings/nodesource.gpg ]; then
  sudo rm /etc/apt/keyrings/nodesource.gpg
fi

curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg

NODE_MAJOR=16  
echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | sudo tee /etc/apt/sources.list.d/nodesource.list
# curl -sL https://deb.nodesource.com/setup_16.x | sudo -E bash -
sudo apt-get update
sudo apt install -y nodejs

# memcached
# sudo apt install memcached

# use bash as default shell
sudo usermod -s /bin/bash "$USER"

echo "Remember to run" '`source ~/.bashrc`' "to reload the path!"