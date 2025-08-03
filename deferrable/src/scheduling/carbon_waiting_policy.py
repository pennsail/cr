from task import Task, TIME_FACTOR
from carbon import CarbonModel

class Schedule:
    def __init__(self, start_time, finish_time, carbon_cost) -> None:
        assert type(start_time) == int
        assert type(finish_time) == int

        self.start_time = start_time
        self.finish_time = finish_time
        self.carbon_cost = carbon_cost

    def actual_start_time(self, current_time):
        return current_time + self.start_time

    def actual_finish_time(self, current_time):
        return current_time + self.finish_time

def compute_carbon_consumption(task: Task, start_time: int, carbon_trace: CarbonModel) -> Schedule:
    """Compute Carbon Consumption with cyclical carbon data"""
    trace_length = len(carbon_trace.df)
    carbon_values = carbon_trace.df["carbon_intensity_avg"].values
    
    execution_carbon = []
    for i in range(task.task_length):
        idx = (start_time + i) % trace_length
        execution_carbon.append(carbon_values[idx])
    
    carbon = sum(execution_carbon) * task.CPUs
    return Schedule(start_time, start_time + task.task_length, carbon)

def lowest_carbon_slot(task: Task, carbon_trace: CarbonModel) -> Schedule:
    """Lowest Carbon Slot Policy that picks the carbon slot with the lowest carbon intensity"""
    if task.waiting_time != 0:
        start_time = carbon_trace.df[:task.waiting_time + 1]["carbon_intensity_avg"].idxmin()
    else:
        start_time = 0
    return compute_carbon_consumption(task, start_time, carbon_trace)

def oracle_carbon_slot(task: Task, carbon_trace: CarbonModel) -> Schedule:
    """Oracle Best Execution slot that uses the actual job length"""
    schedules = []
    for i in range(0, task.waiting_time + 1, 3600//TIME_FACTOR):
        try:
            s = compute_carbon_consumption(task, i, carbon_trace)
            schedules.append(s)
        except:
            pass
    schedule = min(schedules, key=lambda x: x.carbon_cost)
    return schedule

def oracle_carbon_slot_waiting(task: Task, carbon_trace: CarbonModel) -> Schedule:
    """Oracle Carbon Saving per waiting time policy that uses the actual job length"""
    schedules = []
    CA = None
    for i in range(0, task.waiting_time + 1, 3600//TIME_FACTOR):
        try:
            s = compute_carbon_consumption(task, i, carbon_trace)
            schedules.append(s)            
            if i == 0:
                CA = s.carbon_cost
        except:
            pass
    schedule = max(schedules, key=lambda x: (CA - x.carbon_cost)/(x.start_time+ task.task_length))
    return schedule

def average_carbon_slot_waiting(task: Task, carbon_trace: CarbonModel) -> Schedule:
    """Carbon Saving per waiting time policy that uses the average job length"""
    common_task = Task(task.ID, task.arrival_time, task.expected_time, task.CPUs)
    common_schedule = oracle_carbon_slot_waiting(common_task, carbon_trace)
    schedule = compute_carbon_consumption(task, common_schedule.start_time, carbon_trace)
    return schedule

def best_waiting_time(task: Task, carbon_trace) -> Schedule:
    """Oracle Best Execution slot that uses the average job length"""
    common_task = Task(task.ID, task.arrival_time, task.expected_time, task.CPUs)
    common_schedule = oracle_carbon_slot(common_task, carbon_trace)
    schedule = compute_carbon_consumption(task, common_schedule.start_time, carbon_trace)
    return schedule