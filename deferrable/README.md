**Overview**

This folder builds on the GAIA simulator to generate data linking “power deviations” (the extra CPU allocation induced by a carbon‐aware policy) with the resulting impact on total waiting time. We then fit a Lasso regression model to predict waiting time from summary statistics of those power deviations. Below is a step‐by‐step description, without showing the detailed code.

---

### 1. Generating Paired Samples of (d_power, waiting\_time)

1. **Windowed Sampling**
   We simulate “2-day windows” over the carbon trace. For each sample, we randomly pick a start time (between 0 and 24 hours) and consider the next 48 hours of carbon data. We also select a random subset of the full job list and shift their arrival times to within that 48 hour window. 

2. **Two Simulations per Sample**
   For each randomly sampled job set, we run two back‐to‐back simulations:

   * **Baseline (“cost/oracle” or “no‐wait”)**: This is the no-wait policy that never suspends a job for carbon reasons. Every job is scheduled as soon as it arrives. We call out how much CPU it uses and record the sum of final waiting time.
   * **Policy of Interest (e.g. EDD, or “suspend-resume” or “carbon-waiting” etc.)**: We run the same job set under a given EDD or carbon‐aware policy. 
      * For EDD policy, we alter the power allocation to follow a random walk around the baseline allocation, simulating a scheduler that might delay jobs because of the power cap.
      * For other carbon-aware policies, we may suspend and resume jobs when carbon is high, or delay entire jobs until a lower‐carbon window, or follow other heuristics. Again, we record CPU usage and the total “waiting time” (including any time suspended mid-job).

3. **Computing d_power & Δwaiting**
   Once both simulations finish, we have two time series of CPU allocation (baseline vs. policy) in each window, as well as two total-waiting‐time scalars.

   * We compute **d_power\[t] = (baseline\_CPU\[t] - policy\_CPU\[t])** for each window, positive if the policy reduces CPU compared to baseline, negative if it uses more CPU.
   * We compute **Δwaiting = (total\_wait\_policy – total\_wait\_baseline)** and convert that difference into days. That is the *additional* waiting induced by this policy, beyond the baseline.

5. **Building a Dataset**
   Each sample yields:

   * A vector of d_power values,
   * A scalar Δwaiting (in hours),
   * A histogram of how many jobs arrived in each window (job\_counts),
   * Metadata (which scheduling+carbon policy, which random offset in the carbon trace, how many tasks, etc.).
     We repeat this procedure in parallel many times (e.g. 10 000 times) for each policy combination (edd, suspend-resume vs. carbon-waiting vs. carbon-lowest vs. carbon-average, etc.), producing one “pickle” file per (scheduling\_policy, carbon\_policy) pair.

---

### 2. Summarizing Each (d_power, job\_counts) Time Series into Features

Rather than fit a model directly on the d_power series, we compute a handful of summary statistics that capture two intuitive effects:

**Carbon‐Driven Curtailment**

   * Whenever d_power\[t] > 0, the policy is running *less* CPU than baseline (we’ve suspended or delayed some work to avoid high carbon).
   * Whenever d_power\[t] < 0, the policy is running *more* CPU than baseline (we might be rushing jobs before they get suspended, or using additional CPUs at low carbon).
   * We define:

     1. **cum\_wait\_penalty** = sum over time t of max{ ∑\_{τ≤t} \[ job\_counts\[τ] × d_power\[τ]/U\[τ] ], 0 }.  Intuitively, whenever there is a backlog of jobs multiplied by how much we cut CPU at each t, we accumulate a “delay penalty.”
     2. **cum\_delayed\_power** = sum over time t of max{ ∑\_{τ≤t} d_power\[τ], 0 }.  This tracks cumulative positive deviation in CPU usage (i.e. how much we rushed to make up for earlier curtailment).
     3. **convex\_wait\_penalty** = sum over time t of max{ ∑\_{τ≤t} \[ job\_counts\[τ] × (d_power\[τ])² / U\[τ] ], 0 }.  A convex variant that penalizes big deviations even more.
     4. **jobs\_affected** = ∑ over time t of job\_counts\[t] × max{ d_power\[t], 0 } / U\[t].  If at time t we cut CPU (d_power < 0), then no jobs are affected, but if d_power > 0, we count how many jobs we forced to run more intensively (or ahead of schedule).
     5. ~~**tardiness (beyond SLO)** = sum over all t of max{ ∑\_{τ≤t−SLO\_window} \[ job\_counts\[τ] × d_power\[τ]/U\[τ] ], 0 }.  Whenever we have a backlog older than a service-level window, we accumulate a penalty that mimics an overdue-delay measure.~~ This feature was removed in the regression experiments, as it the public job trace does not have a notion of SLOs or deadlines.

Putting these together, each sample gives us an 4-dimensional feature vector. We store these features in a tabular DataFrame, alongside the target Δwaiting.

---

### 3. Fitting a Sparse Linear Model (Lasso)

1. **Data Splitting & Standardization**
   We collect all samples (for a given policy) into a large $N×7$ feature matrix $X$ and a length-$N$ target vector $y=\{\Delta waiting\}$. We then standardize each column of $X$ to zero mean and unit variance.

2. **10-Fold Cross-Validated Lasso**
   We use scikit-learn’s `LassoCV` with 10 folds and `positive=True` (non‐negative coefficients). This means:

   * We fit a linear model $ŷ = β₀ + β₁·f₁ + β₂·f₂ + … + β₇·f₇$, where $f_i$ are the features.
   * We automatically choose α (the regularization strength) by 10-fold cross validation.
   * We force each $β_i ≥ 0$ since it is not physically meaningful to have a negative penalty on any of these features.

3. **Evaluating Fit**
   After LassoCV returns the best α and the fitted coefficients, we measure:

   * **R²**: fraction of variance in waiting-time explained.
   * **MSE**: mean squared error.
   * **MAE**: mean absolute error.

   We also produce a scatter plot of true vs. predicted waiting time to visualize how well the model fits at the tails.

---

### 4. Results & Insights

* **Earliest Due Date (EDD)** is a classic scheduling policy that minimizes the maximum lateness of jobs. In our experiments, we treat EDD as the default batch‐job scheduler in hyperscale datacenters because it preserves a clean workload abstraction: it always allocates each job its maximum entitled CPU and never delays tasks for the sake of carbon reduction. We believe that carbon‐saving measures should be applied at the cluster-management level rather than imposed on individual workload teams (which enforces all teams to modify their existing schedulers).

* **Carbon-aware Scheduling Policies** are proposed by GAIA paper, e.g., “carbon-waiting,” “carbon-lowest,” “carbon-cst\_average”. They typically have very smooth and continuous d_power patterns, because they delay jobs block-by-block instead of repeatedly suspending/resuming. As a result, even only the original 4 features proposed in CR paper explain most of the waiting time. R² often exceeds 0.8. See the scatter plots below.

* **Suspend-Resume Policies** (e.g. “suspend-resume\_oracle,” “suspend-resume\_threshold\_oracle”) exhibit highly oscillatory d_power as they can suspend jobs at any time and resume them later. Capturing this requires extra features and measures. The model fit R²≈0.8 for the suspend-resume policies. See the scatter plots above and below.
 
![Regression Results](./plots/lasso_scatter_baseline.png)

---

### 5. Practical Steps to Reproduce

1. **Prepare Your Environment**

   * Install Python 3.9+.
   * `pip install numpy pandas scikit-learn matplotlib pickle5`.
   * Ensure the GAIA codebase (cluster, scheduling, carbon, task.py, etc.) is in `src/`.

2. **Generate Datasets**

   ```
   cd deferrable
   python src/dgp.py --waiting-times 1x8 --num-samples 1000 --num-tasks 10000 --task-trace azure-100k -o azure100k-1x8-10000 -p baseline
   ```

   This will spawn multiple processes. Each process picks a random 48 h window, runs both baseline and policy, and saves one dict. At the end you get 1 000–10 000 dicts per policy pair, all pickled.

3. **Fit Lasso on Baselines**

   ```
   cd deferrable
   python src/lasso.py
   ```

   By default, `lasso.py` looks in the folder named `azure100k-1x8-1000-10000/` for files ending in “\_dataset.pkl” whose names start with any of the six baseline policy identifiers. It computes features, fits LassoCV (10 folds), prints chosen α, coefficients, R², and saves a 2×3 scatter plot of true vs. predicted waiting time.

4. **Fit Lasso on All Policies**
   Edit `lasso.py`’s `main()` so it calls `fit_lasso_for_all_datasets(...)` instead of the baseline variant. This will produce a 4×5 grid of scatter plots, one per scheduling+carbon combination (including all suspend‐resume variants).
