#!/usr/bin/env bash
set -e

# Ensure CMake ≥3.16 on Ubuntu 18.04
if [[ "$(cmake --version | head -n1 | cut -d' ' -f3)" < "3.16" ]]; then
  sudo apt-get update -qq
  sudo apt-get install -y software-properties-common wget gnupg lsb-release
  wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc \
    | sudo apt-key add -
  sudo apt-add-repository \
    "deb https://apt.kitware.com/ubuntu $(lsb_release -cs) main"
  sudo apt-get update -qq
  sudo apt-get install -y cmake
fi

git clone --recursive https://github.com/intel/pcm.git
sudo apt-get update
sudo apt install -y cmake
cd pcm
mkdir build
cd build
sudo cmake ..
sudo cmake --build .
sudo cmake --install .
sudo modprobe msr
