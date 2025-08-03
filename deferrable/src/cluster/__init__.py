from carbon import CarbonModel
from .simulation_cluster import SimulationCluster
from .base_cluster import BaseCluster
from .base_cluster import ON_DEMAND_COST_HOUR


def create_cluster(cluster_type: str, scheduling_policy: str, carbon_model: CarbonModel, reserved_instances: int, experiment_name: str, cluster_partition: str):
    """Create Cluster Instance (Simulation and Real)

    Args:
        cluster_type (str): Cluster Type ("simulation")
        scheduling_policy (str): scheduling algorithm
        carbon_model (CarbonModel): Carbon Intensity Model
        reserved_instances (int): number of reserved instances
        waiting_times_str (str): waiting times per queue
        cluster_partition (str): used cluster partition (queue)

    Raises:
        Exception: Wrong Configuration

    Returns:
        _type_: Cluster
    """
    if cluster_type == "simulation":
        return SimulationCluster(reserved_instances, carbon_model, experiment_name, "spot" in scheduling_policy)
    else:
        raise Exception("Not Implemented")
