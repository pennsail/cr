import argparse
import concurrent.futures

from common import *
from envs import *


def rsync(src, dst, excludes=[]):
    to_exclude = ['*.pyc', '*.pyo', '*.pyd', '__pycache__', '.idea']
    to_exclude = to_exclude + excludes
    to_exclude = ' '.join([f'--exclude {e}' for e in to_exclude])
    shell_cmd = f'rsync -e "ssh -o StrictHostKeyChecking=no -i {KEYFILE}" -avz {to_exclude} {src} {dst}'
    run_shell(shell_cmd)


def main():
    args = parse_arguments()
    import concurrent.futures
    import threading
    
    def upload_to_server(s):
        print(f"copying files to {s}")
        path = f'{CLOUDLAB_USER}@{s}:~/'
        excludes = ['*.log', '*.pdf', '*.err', "*.png", "*.csv", "*.out*", "*.json", ".git", "logs/", "pcm_results/", "visual/", "sampled_services/", "nohup.out"]
        
        if SERVERS.index(s) == 0:
            rsync(PROJECT_PATH, path, excludes=excludes + ['proxy/target'])
        else:
            rsync(PROJECT_PATH, path, excludes=excludes + ['protobuf','proxy/target'])
    
    # Upload to first server only if host_only is specified
    if args.host_only:
        upload_to_server(SERVERS[0])
        return
    
    # Parallel upload to all servers
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(SERVERS), 2)) as executor:
        executor.map(upload_to_server, SERVERS)

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host_only",
                        help="determines whether to only upload to the host",
                        action="store_true")
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    main()
