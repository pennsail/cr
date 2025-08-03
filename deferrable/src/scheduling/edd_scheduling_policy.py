from typing import List
from task import Task, TwoQueues
from queue import PriorityQueue
from cluster.base_cluster import BaseCluster

class EDDQueueObject:
    def __init__(self, task: Task, due_time: int) -> None:
        self.task = task
        self.due_time = due_time
        
    def __lt__(self, other):
        return self.due_time < other.due_time

class EDDSchedulingPolicy:
    def __init__(self, cluster: BaseCluster, cpu_limits: List[int]) -> None:
        """
        EDD scheduler with hourly CPU limits.
        """
        self.cluster = cluster
        self.cpu_limits = cpu_limits
        self.queue: PriorityQueue = PriorityQueue()
        
    def submit(self, current_time: int, task: Task):
        """Submit task to EDD queue, sorted by due time (arrival + waiting_time)"""
        due_time = task.arrival_time + task.waiting_time
        self.queue.put(EDDQueueObject(task, due_time))
        
    def execute(self, current_time: int):
        """Execute tasks in EDD order, respecting CPU limits"""
        if self.queue.empty():
            return
            
        current_hour = current_time // 720
        
        if current_hour >= len(self.cpu_limits):
            temp_queue = PriorityQueue()
            while not self.queue.empty():
                queue_obj = self.queue.get()
                self.cluster.submit(current_time, queue_obj.task)
            return
            
        cpu_limit = self.cpu_limits[current_hour]
        current_cpu_usage = self.cluster.runtime_allocation[current_time] if current_time < len(self.cluster.runtime_allocation) else 0
        
        temp_queue = PriorityQueue()
        scheduled_any = False
        
        while not self.queue.empty():
            queue_obj = self.queue.get()
            task = queue_obj.task
            
            if current_cpu_usage + task.CPUs <= cpu_limit:
                self.cluster.submit(current_time, task)
                current_cpu_usage += task.CPUs
                scheduled_any = True
            else:
                temp_queue.put(queue_obj)
                
        self.queue = temp_queue
        self.cluster.refresh_data(current_time)