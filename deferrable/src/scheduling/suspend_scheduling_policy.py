from typing import Callable
from carbon import CarbonModel
from task import TIME_FACTOR, Task
from queue import PriorityQueue
from cluster.base_cluster import BaseCluster
import pandas as pd
import numpy as np

class QueueObject:
    def __init__(self, task: Task, max_start_time: int, priority: float) -> None:
        self.task = task
        self.max_start_time = max_start_time
        self.priority = priority

    def __lt__(self, other):
        return self.priority < other.priority

    def __str__(self):
        return f"QueueObject(task={self.task.ID}, max_start={self.max_start_time}, pri={self.priority})"

class SuspendSchedulingPolicy:
    """A Scheduling Policy that simulates suspend/resume:
    - WaitAwhile (optimal=True): select J slots of lowest carbon within J+W window.
    - Ecovisor (optimal=False): greedy by threshold then enforce deadline.
    """

    def __init__(self, cluster: BaseCluster, carbon_model: CarbonModel, optimal: bool) -> None:
        self.cluster = cluster
        self.carbon_model = carbon_model
        self.queue: PriorityQueue = PriorityQueue()
        self.optimal = optimal

    def compute_schedule_optimal(self, df: pd.DataFrame, task: Task) -> list:
        """
        WaitAwhile: within the first (J + W) slots of df['carbon_intensity_avg'],
        pick the J lowest-carbon slots and schedule them in time order.
        """
        J = task.task_length
        W = task.waiting_time
        window_len = J + W
        arr = df['carbon_intensity_avg'].iloc[:window_len].to_numpy()
        if arr.shape[0] < window_len:
            raise RuntimeError(f"Insufficient carbon data: need {window_len}, got {arr.shape[0]}")
        idxs = np.argsort(arr, kind='stable')[:J]
        slots = sorted(int(i) for i in idxs)
        schedule = [0] * window_len
        for t in slots:
            schedule[t] = 1
        return schedule

    def compute_schedule_threshold(self, df: pd.DataFrame, task: Task, threshold: float) -> list:
        """
        Ecovisor: run when carbon < threshold; else wait until threshold or W expires,
        then run continuously to finish J units.
        """
        J = task.task_length
        W = task.waiting_time
        window_len = J + W
        arr = df['carbon_intensity_avg'].iloc[:window_len].to_numpy()
        if arr.shape[0] < window_len:
            raise RuntimeError(f"Insufficient carbon data: need {window_len}, got {arr.shape[0]}")
        schedule = [0] * window_len
        rem_wait = W
        rem_job = J
        for t, ci in enumerate(arr):
            if rem_job <= 0:
                break
            if ci < threshold or rem_wait <= 0:
                schedule[t] = 1
                rem_job -= 1
            else:
                rem_wait -= 1
        if rem_job > 0:
            raise RuntimeError(f"Cannot fit job (length {J}) within deadline W={W}")
        return schedule

    def submit(self, current_time: int, task: Task):
        """Split Task into sub-tasks according to computed schedule and enqueue."""
        try:
            horizon = task.task_length + task.waiting_time
            trace_df = self.carbon_model.subtrace(
                current_time, current_time + horizon
            ).df
            if self.optimal:
                schedule = self.compute_schedule_optimal(trace_df, task)
            else:
                lookahead = int(3600 / TIME_FACTOR * 24)
                threshold = self.carbon_model.df[
                    current_time : current_time + lookahead
                ]['carbon_intensity_avg'].quantile(0.3)
                schedule = self.compute_schedule_threshold(trace_df, task, threshold)

            sub_tasks = []
            start_times = []
            prev_end = 0
            i = 0
            while i < len(schedule):
                if schedule[i] == 0:
                    i += 1
                    continue
                start = i
                while i < len(schedule) and schedule[i] == 1:
                    i += 1
                length = i - start

                scheduled_wait = start - prev_end
                
                sub = Task(task.ID, current_time + start, length, task.CPUs)
                sub.scheduled_wait = scheduled_wait
                prev_end = i

                if not self.optimal:
                    sub.task_length_class = task.task_length_class
                sub_tasks.append(sub)
                start_times.append(start)

            for sub, offset in zip(sub_tasks, start_times):
                self.queue.put(QueueObject(sub, current_time + offset, sub.arrival_time))
        except Exception as e:
            print(f"SuspendSchedulingPolicy error: {e}")
            raise

    def execute(self, current_time: int):
        """Submit ready sub-tasks whose start time has arrived."""
        next_queue = PriorityQueue()
        while not self.queue.empty():
            obj = self.queue.get()
            if current_time >= obj.max_start_time:
                self.cluster.submit(current_time, obj.task)
            else:
                next_queue.put(obj)
        self.queue = next_queue
        self.cluster.refresh_data(current_time)