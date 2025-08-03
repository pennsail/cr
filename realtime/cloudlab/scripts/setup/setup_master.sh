#!/bin/bash -ex

# add hostname to bashrc
# node-0, node-1, node-2
HOSTNAME=$(hostname | cut -d. -f1)
echo "export HOSTNAME=$HOSTNAME" >>"$HOME"/.bashrc

# Install helmv3
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
chmod 700 get_helm.sh
./get_helm.sh

# Install Redis
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Reset existing cluster if it exists
sudo kubeadm reset -f || true
sudo rm -rf /etc/kubernetes/manifests
sudo rm -rf /var/lib/etcd
sudo rm -rf ~/.kube

# start k8s cluster
i=0
maximum_retries=10
while ! sudo kubeadm config images pull
do
    echo "Didn't succeed in pulling images, retrying in 5 seconds"
    sleep 5
    i=$((i+1))
    if [ $i -eq $maximum_retries ]; then
        echo "Error: Maximum retries: $maximum_retries exceeded when trying to pull images"
        echo "Exiting..."
        exit 1
    fi
done

sudo kubeadm init --pod-network-cidr=10.244.0.0/16 --node-name "$HOSTNAME"

# use kubectl as non-root user
sudo rm -rf "$HOME"/.kube
mkdir -p "$HOME"/.kube
sudo cp -i /etc/kubernetes/admin.conf "$HOME"/.kube/config
sudo chown $(id -u):$(id -g) "$HOME"/.kube/config

# add flannel network
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml

# install kubectl completion
echo "source <(kubectl completion bash)" >>~/.bashrc

echo "export PYTHONPATH=$HOME/cr/realtime/cloudlab/" >>"$HOME"/.bashrc

echo "alias k=kubectl" >>"$HOME"/.bashrc

# Install ghz
source ~/.bashrc;
# if ghz already exists, remove it
if [ -d ghz ]; then
  rm -rf ghz
fi
git clone https://github.com/bojand/ghz;
export PATH=$PATH:/usr/local/go/bin;
cd ghz/cmd/ghz; go build .; sudo mv ghz /usr/local/bin/ghz; cd -;