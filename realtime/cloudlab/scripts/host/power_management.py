#!/usr/bin/env python3
import os
import sys
import argparse
from fabric import ThreadingGroup, Connection
from fabric import exceptions
from envs import *
from common import *

REMOTE_DIR = "~/cr/realtime"
SCRIPT_PATH = "cloudlab/scripts/power_management.sh"

def parse_args():
    parser = argparse.ArgumentParser(description='Power management operations across nodes')
    parser.add_argument('action', choices=['init', 'cap', 'uncap', 'status'],
                        help='Action to perform: init, cap, uncap, or status')
    parser.add_argument('-c', '--cap', type=int, default=None,
                        help='Power cap value in watts (required for cap action)')
    parser.add_argument('-d', '--duration', type=int, default=60,
                        help='Duration for measurement in seconds (default: 60)')
    parser.add_argument('-o', '--output', default='./power_measurements',
                        help='Output directory for measurements (default: ./power_measurements)')
    parser.add_argument('-n', '--nodes', default=None,
                        help='Comma-separated list of nodes to target (default: all nodes)')
    
    args = parser.parse_args()
    

    if args.action == 'cap' and args.cap is None:
        parser.error("The 'cap' action requires the --cap argument")
    
    return args

def main():
    args = parse_args()
    

    targets = HOST_SERVERS
    if args.nodes:
        requested = args.nodes.split(",")
        targets = [h for h in HOST_SERVERS if h in requested]
        if not targets:
            print("No matching hosts; exiting.")
            sys.exit(1)
    
    print(f"Targeting nodes: {', '.join(targets)}")
    
    group = ThreadingGroup(*targets, connect_kwargs={
        'key_filename': KEYFILE,
    })
    
    remote_script_path = os.path.join(REMOTE_DIR, SCRIPT_PATH)
    cmd_parts = [remote_script_path, args.action]


    cmd_parts.insert(0, "sudo")
    
    if args.cap is not None:
        cmd_parts.extend(["-c", str(args.cap)])
    
    if args.duration != 60:
        cmd_parts.extend(["-d", str(args.duration)])
    
    if args.output != './power_measurements':
        cmd_parts.extend(["-o", args.output])
    
    command = " ".join(cmd_parts)
    
    print(f"Executing on all nodes: {command}")
    try:
        results = group.run(command)
        
        for node, result in results.items():
            print(f"\n--- Results from {node} ---")
            print(result.stdout)
        
    except exceptions.GroupException as e:
        print("Errors occurred during execution:")
        for node, exception in e.result.items():
            print(f"  {node}: {exception}")
    
    print(f"\nPower management '{args.action}' operation completed on: {', '.join(targets)}")

if __name__ == "__main__":
    main()