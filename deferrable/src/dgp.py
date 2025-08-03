#!/usr/bin/env python3
"""
Generate profiling datasets by reusing GAIA's run_experiment logic.
For each (scheduling_policy, carbon_policy) combination, sample random start indices
and task subsets, simulate 48h runs, and extract d_power & waiting_time.
"""
import os, copy
import random
import pickle
from typing import List, Tuple
import multiprocessing as mp
from tqdm import tqdm

import numpy as np

from carbon import get_carbon_model
from task import Task, set_waiting_times, load_tasks, TIME_FACTOR
from scheduling import create_scheduler
from cluster import create_cluster

DURATION_HOURS = 48
DURATION_TICKS = int(DURATION_HOURS * 3600 // TIME_FACTOR)
WINDOW_TICKS = int((5*60) // TIME_FACTOR)
NUM_WINDOWS = DURATION_TICKS // WINDOW_TICKS
UNLIMITED_CPUS = 10**9

SCHED_POLICIES = ["carbon", "carbon-cost", "suspend-resume", "suspend-resume-threshold", "edd"]
CARBON_POLICIES = ["waiting", "lowest", "oracle", "cst_oracle", "cst_average"]

BASELINE_POLICIES = [
    "suspend-resume-threshold_oracle",
    "suspend-resume_oracle",
    "carbon_lowest", 
    "carbon_waiting", 
    "carbon_cst_average",
    "edd_fixed",
]

ALL_TASKS: List[Task] = []
END_OF_DAY = 24 * 3600 // TIME_FACTOR
WAITING_STR: str = "0x0"
CARBON_TRACE: str = "AU-SA"

def init_worker(tasks: List[Task], carbon_trace: str, waiting_str: str):
    """
    Setup global task list and compute valid start index range for 2-day windows.
    """
    global ALL_TASKS, MAX_START, WAITING_STR, CARBON_TRACE
    ALL_TASKS = tasks
    WAITING_STR = waiting_str
    CARBON_TRACE = carbon_trace

def simulate_sample(
    sched_policy: str,
    carbon_policy: str,
    carbon_start_idx: int,
    tasks: List[Task],
    waiting_str: str,
    reserve_instances: int,
    cpu_limits: List[int] = None,
) -> dict:
    """
    Run a simulation for tasks whose arrival_time has been rebased to [0..DURATION_TICKS).
    Returns per-window mean usage and total waiting ticks.
    """
    cm = get_carbon_model(CARBON_TRACE, carbon_start_index=carbon_start_idx)
    cm = cm.extend(3600 / TIME_FACTOR)
    set_waiting_times(waiting_str)

    exp_name = f"{sched_policy}-{carbon_policy}-{carbon_start_idx}-{random.getrandbits(32)}"
    cluster = create_cluster(
        "simulation",
        sched_policy,
        cm,
        reserve_instances,
        exp_name,
        ""
    )
    
    if sched_policy == "edd":
        scheduler = create_scheduler(cluster, sched_policy, carbon_policy, cm, cpu_limits)
    else:
        scheduler = create_scheduler(cluster, sched_policy, carbon_policy, cm)

    current_time = 0
    while True:
        while len(tasks) > 0:
            if tasks[0].arrival_time <= current_time:
                if tasks[0].task_length > 0:
                    scheduler.submit(current_time, tasks[0])
                del tasks[0]
            else:
                break
        with cluster.lock:
            scheduler.execute(current_time)
        cluster.sleep()
        current_time += 1
        if len(tasks) == 0 and scheduler.queue.empty():
            break
 
    J_tick = [0] * DURATION_TICKS
    for rec in cluster.details:
        start = rec[8]
        end = rec[10]
        for t in range(start, min(end, DURATION_TICKS)):
            J_tick[t] += 1

    job_counts = [
        sum(J_tick[w*WINDOW_TICKS : (w+1)*WINDOW_TICKS])
        for w in range(NUM_WINDOWS)
    ]

    raw = cluster.runtime_allocation[:DURATION_TICKS]
    cpu_windows = [
        float(np.mean(raw[i*WINDOW_TICKS:(i+1)*WINDOW_TICKS]))
        for i in range(NUM_WINDOWS)
    ]
    
    total_wait = sum(r[9] for r in cluster.details)
    scheduled_jobs = len(cluster.details)
    total_wait = total_wait * TIME_FACTOR / 3600
    
    result = {
        "windows": cpu_windows,
        "total_wait": total_wait,
        "job_counts": job_counts,
        "scheduled_jobs": scheduled_jobs
    }
    return result

def worker_task(args) -> dict:
    sched, cpol = args

    csi = random.randint(0, 8500)

    window_tasks = ALL_TASKS
    if not window_tasks:
        raise ValueError("No tasks in window")
    if len(window_tasks) < 10000:
        raise ValueError("Too few tasks in window, need at least 10000")

    subset = random.sample(window_tasks, k)

    for t in subset:
        t.arrival_time = (t.arrival_time) % DURATION_TICKS

    subset.sort(key=lambda x: x.arrival_time)

    tasks_for_base = copy.deepcopy(subset)
    tasks_for_policy = copy.deepcopy(subset)

    nowait_result = simulate_sample(
        "carbon", "waiting", csi, tasks_for_base, '0x0', UNLIMITED_CPUS
    )
    base_usage, base_wait, J_window_b = nowait_result["windows"], nowait_result["total_wait"], nowait_result["job_counts"]
    scheduled_jobs = nowait_result["scheduled_jobs"]

    if sched == "edd":
        base_cpu_hourly = [np.mean(base_usage[h*12:(h+1)*12]) for h in range(DURATION_HOURS)]
        base_mean = np.mean(base_cpu_hourly)
        base_std = np.std(base_cpu_hourly)
        
        start_cpu = int(base_mean * random.uniform(0.9, 1.1))
        step_size = max(5, int(base_std * 0.2))
        cpu_limits = [start_cpu]
        
        for _ in range(DURATION_HOURS - 1):
            step = random.choice([-step_size//2, -step_size//4, 0, step_size//4, step_size//2])
            next_cpu = max(int(base_mean * 0.7), cpu_limits[-1] + step)
            cpu_limits.append(next_cpu)
            
        policy_result = simulate_sample(
            sched, cpol, csi, tasks_for_policy, WAITING_STR, RESERVED_INSTANCES, cpu_limits
        )
    else:
        policy_result = simulate_sample(
            sched, cpol, csi, tasks_for_policy, WAITING_STR, RESERVED_INSTANCES
        )
    pol_usage, pol_wait, J_window = policy_result["windows"], policy_result["total_wait"], policy_result["job_counts"]
    pol_scheduled_jobs = policy_result["scheduled_jobs"]

    d_power = [p - b for p,b in zip(pol_usage, base_usage)]
    result = {
        "d_power": d_power, 
        "waiting_time": pol_wait - base_wait,
        "sched_policy": sched,
        "carbon_policy": cpol,
        "carbon_start_index": csi,
        "num_tasks": len(subset),
        "base_wait": base_wait,
        "base_usage": base_usage,
        "pol_usage": pol_usage,
        "pol_wait": pol_wait,
        "base_job_counts": J_window_b,
        "job_counts": J_window,
        "scheduled_jobs": scheduled_jobs,
        "pol_scheduled_jobs": pol_scheduled_jobs
    }
    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser("Generate GAIA datasets via wrapper")
    parser.add_argument("-n", "--num-samples", type=int, default=10)
    parser.add_argument("-k", "--num-tasks", type=int, default=10000,
                        help="Number of tasks in each sample (default: 10000)")
    parser.add_argument("-t", "--task-trace", default="pai_1k")
    parser.add_argument("-w", "--waiting-times", default=WAITING_STR)
    parser.add_argument("-c", "--carbon-trace", default="AU-SA")
    parser.add_argument("--ca", action="store_true", help="Use custom carbon intensity data")
    parser.add_argument("-o", "--output-dir", default="datasets")
    parser.add_argument("-p", "--policies", default="all",
                        help="Which policies to generate datasets for")
    parser.add_argument("-r", "--reserve-instances", type=int, default=UNLIMITED_CPUS,
                        help="Number of reserved instances for the cluster")

    args = parser.parse_args()

    global RESERVED_INSTANCES
    RESERVED_INSTANCES = args.reserve_instances
    global k
    k = args.num_tasks
    
    if args.ca:
        args.carbon_trace = "custom"

    os.makedirs(args.output_dir, exist_ok=True)
    set_waiting_times(args.waiting_times)
    tasks = load_tasks(args.task_trace)

    print(f"Loaded {len(tasks)} tasks from {args.task_trace} trace")
    print(f"Using carbon trace {args.carbon_trace} with waiting times {args.waiting_times} and {RESERVED_INSTANCES} reserved instances")

    if args.policies == "all":
        for sched in SCHED_POLICIES:
            for cpol in CARBON_POLICIES:
                key = f"{sched}_{cpol}"
                print(f"Generating {key}: {args.num_samples} samples, each with {k} tasks")
                pool = mp.Pool(
                    processes=mp.cpu_count(),
                    initializer=init_worker,
                    initargs=(tasks, args.carbon_trace, args.waiting_times)
                )
                args_list = [(sched, cpol)] * args.num_samples
                results = pool.map(worker_task, args_list)
                pool.close(); pool.join()

                out_f = os.path.join(args.output_dir, f"{key}_dataset.pkl")
                with open(out_f, 'wb') as f:
                    pickle.dump(results, f)
                print(f"Saved {out_f}")
    elif args.policies == "baseline":
        for key in BASELINE_POLICIES:
            out_f = os.path.join(args.output_dir, f"{key}_dataset.pkl")
            if os.path.exists(out_f):
                print(f"Skipping {key}, already exists: {out_f}")
                continue
            print(f"Generating {key}: {args.num_samples} samples, each with {k} tasks")
            pool = mp.Pool(
                processes=mp.cpu_count(),
                initializer=init_worker,
                initargs=(tasks, args.carbon_trace, args.waiting_times)
            )
            sched, cpol = key.split("_", 1)
            args_list = [(sched, cpol)] * args.num_samples
            results = list(tqdm(pool.imap(worker_task, args_list), total=args.num_samples, desc=f"Processing {key}"))
            pool.close(); pool.join()

            out_f = os.path.join(args.output_dir, f"{key}_dataset.pkl")
            with open(out_f, 'wb') as f:
                pickle.dump(results, f)
            print(f"Saved {out_f}")
    else:
        policies = args.policies
        for key in policies.split(","):
            key = key.strip()
            if key not in BASELINE_POLICIES:
                raise ValueError(f"Unknown policy {key}, expected one of {BASELINE_POLICIES}")
            if "_" not in key:
                raise ValueError("Invalid policy format, expected 'sched_cpol' format")
            else:
                print(f"Generating {key}: {args.num_samples} samples")
                sched, cpol = key.split("_")

                pool = mp.Pool(
                    processes=mp.cpu_count(),
                    initializer=init_worker,
                    initargs=(tasks, args.carbon_trace, args.waiting_times)
                )
                args_list = [(sched, cpol)] * args.num_samples
                results = pool.map(worker_task, args_list)
                pool.close(); pool.join()
                out_f = os.path.join(args.output_dir, f"{key}_dataset.pkl")
                with open(out_f, 'wb') as f:
                    pickle.dump(results, f)
                print(f"Saved {out_f}")