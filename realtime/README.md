# Real-time Workload Power-Capping Experiments

## Setup

1. **Setup K8s on CloudLab (7 nodes)**
   ```bash
   vim cloudlab/scripts/envs.sh
   source cloudlab/scripts/envs.sh && python3 cloudlab/scripts/host/upload.py && python3 cloudlab/scripts/host/setup.py && cd cloudlab/scripts && bash cloudlab_setup.sh
   ```

2. **Run microservices application**
   ```bash
   export METHOD=search-hotel
   export WARMUP_LOAD=4000
   bash ./cloudlab/scripts/overload-experiments.sh -c 8000
   ```

3. **Apply DVFS on all nodes**
   ```bash
   python3 cloudlab/scripts/host/power_management.py status                 
   python3 cloudlab/scripts/host/power_management.py cap -c 40
   ```

4. **Run the experiments**
   ```bash
   for i in {1..50}; do bash cloudlab/scripts/power-exp.sh search-hotel --low --no-control; bash cloudlab/scripts/power-exp.sh compose --low --no-control; done
   ```