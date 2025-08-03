import time
import sys
import argparse
from fabric import Connection, ThreadingGroup
from fabric import exceptions
from common import *
from envs import *

SETUP_PATH = "./cr/realtime/cloudlab/scripts/setup"

# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument('controlplane', nargs='?', type=int, default=0, help='Controlplane node index')
parser.add_argument('--os', action='store_true', help='Use setup3.sh for Ubuntu 22')
args = parser.parse_args()

controlplane = args.controlplane
use_ubuntu22 = args.os
print(f"Controlplane: {controlplane}")
if use_ubuntu22:
    print("Using setup3.sh for Ubuntu 22")

def master_conn():
    return Connection(HOST_SERVERS[controlplane], connect_kwargs={
        'key_filename': KEYFILE,
    })


def worker_conn(idx: int):
    return Connection(HOST_SERVERS[idx], connect_kwargs={
        'key_filename': KEYFILE,
    })


def setup1():
    group = ThreadingGroup(*HOST_SERVERS, connect_kwargs={
        'key_filename': KEYFILE,
    })

    try:
        res = group.run(os.path.join(SETUP_PATH, "setup1.sh"))
        print(res)
    except exceptions.GroupException as e:
        print("Servers are rebooting. Disconnection expected:", e)


def setup2():
    group = ThreadingGroup(*HOST_SERVERS, connect_kwargs={
        'key_filename': KEYFILE,
    })
    setup_script = "setup3.sh" if use_ubuntu22 else "setup2.sh"
    res = group.run(os.path.join(SETUP_PATH, setup_script))
    

    log_suffix = "3" if use_ubuntu22 else "2"
    log_file = os.path.expanduser(f'~/setup{log_suffix}.log')
    with open(log_file, 'w') as f:
        for host, result in res.items():
            f.write(f"Host: {host}\n")
            f.write(f"Exit Code: {result.exited}\n")
            f.write(f"Stdout:\n{result.stdout}\n")
            f.write(f"Stderr:\n{result.stderr}\n")
            f.write("-" * 50 + "\n")
    
    print(f"Log saved to {log_file}")



def setup_master():
    conn = master_conn()
    res = conn.run(os.path.join(SETUP_PATH, "setup_master.sh"))
    prev_line = ""
    join_cmd = ""
    for line in res.stdout.splitlines():
        print(line)
        if "--discovery-token-ca-cert-hash" in line:
            join_cmd = prev_line[:-2] + line
        prev_line = line
    return join_cmd


def setup_workers(join_cmd: str):
    for idx in list(range(0, controlplane)) + list(range(controlplane + 1, len(HOST_SERVERS))):
        worker = worker_conn(idx)
        worker.run("sudo kubeadm reset -f || true")
        worker.run("sudo rm -rf /etc/kubernetes/kubelet.conf /etc/kubernetes/pki/ca.crt || true")
        res = worker.run("sudo " + join_cmd + f"--node-name=node-{idx}")
        print(res)



# def start_k8s():
#     conn = master_conn()
#     res = conn.run("kubectl apply -f $HOME/cr/realtime/cloudlab/deploy/hardcode-hotel.yaml")

#     print(res)

def setup():
    print("Setup2")
    setup2()
    join_cmd = setup_master()
    print("Join command:")
    print("-" * 20)
    print(join_cmd)
    setup_workers(join_cmd)
    time.sleep(3)
    # start_k8s()
    


def main():
    setup()


if __name__ == '__main__':
    main()
