#!/usr/bin/env python3

import os
import subprocess
import xml.etree.ElementTree as ET


def project_path():
    return os.popen("git rev-parse --show-toplevel --show-superproject-working-tree").read().strip()


def run_collect_output(cmd):
    res = subprocess.run(cmd, stdout=subprocess.PIPE)
    return res.stdout.decode('utf-8').strip()


def run_in_bg(cmd: str, wd: str):
    return subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=os.path.join(project_path(), wd))


def run_shell(cmd):
    res = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
    return res.stdout.decode('utf-8').strip()


def update_manifest(manifest_file: str = "manifest.xml"):
    node_username = os.environ.get('node_username')
    node_address = os.environ.get('node_address')
    private_key = os.environ.get('private_key', '~/.ssh/id_cl')  # Default to KEYFILE if not set

    # SSH command to run geni-get manifest
    ssh_cmd = f"ssh -i {private_key} -o StrictHostKeyChecking=no {node_username}@{node_address} 'geni-get manifest > {manifest_file}'"
    run_shell(ssh_cmd)
    print("Manifest file updated")

    # Copying the manifest file from the remote server
    scp_cmd = f"scp -i {private_key} -o StrictHostKeyChecking=no {node_username}@{node_address}:manifest.xml {manifest_file}"
    run_shell(scp_cmd)


def addresses_from_manifest(manifest_file: str) -> "list[str]":
    update_manifest()
    tree = ET.parse(manifest_file)
    root = tree.getroot()
    addresses = []
    for child in root:
        # print(child.tag)
        if child.tag.endswith("node"):
            component_id = child.attrib["component_id"]
            # print(component_id)
            node_name = component_id.split("+")[-1]
            location = component_id.split("+")[1]
            address = f'{node_name}.{location}'
            # print(address)
            addresses.append(address)
    return addresses

PROJECT_PATH = project_path()

SERVERS = addresses_from_manifest(f'{PROJECT_PATH}/manifest.xml')
