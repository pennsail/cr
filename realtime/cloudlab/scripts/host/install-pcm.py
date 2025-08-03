#!/usr/bin/env python3
import os
import sys
from fabric import ThreadingGroup, Connection
from fabric import exceptions
from envs import *
from upload import rsync
from common import *

LOCAL_CO2   = os.path.expanduser("~/microservice-carbon")

def main():

    targets = HOST_SERVERS
    if len(sys.argv) > 1:
        requested = sys.argv[1].split(",")
        targets = [h for h in HOST_SERVERS if h in requested]
        if not targets:
            print("No matching hosts; exiting.")
            sys.exit(1)

    group = ThreadingGroup(*HOST_SERVERS, connect_kwargs={
        'key_filename': KEYFILE,
    })

    print("1) Installing system packages…")
    group.run(
        "sudo apt-get update && sudo apt-get install -y "
        "libcurl4-openssl-dev build-essential git libmicrohttpd-dev", hide="stdout"
    )

    print("2) changing governor to schedutil…")
    group.run(
        "sudo cpupower frequency-set -g performance"
    )

    # remove any frequency capping

    print("2) Push local code to each node…")

    for s in SERVERS:
        print("copying files to", s)
        path = f'{CLOUDLAB_USER}@{s}:~/'
        rsync(LOCAL_CO2, path, excludes=['control'])
    
    print("1) Installing pcm dependencies…")
    group.run(
        "sudo rm -rf ~/pcm && "
        "source $HOME/cr/realtime/cloudlab/scripts/host/install_pcm_legacy.sh", hide="stdout"
    )    

    print("3) copy the built pcm to /usr/local/bin…")
    group.run(
        "sudo cp ~/pcm/build/bin/pcm* /usr/local/bin"
    )





if __name__ == "__main__":
    main()
