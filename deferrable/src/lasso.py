#!/usr/bin/env python3
import os
import pickle
import pandas as pd
import numpy as np
from analysis_utils import inspect_row, plot_waiting_hist, plot_sample_d_powers, summarize_dataset, plot_sample_d_powers_colormap, load_dataset
from dgp import SCHED_POLICIES, CARBON_POLICIES, BASELINE_POLICIES

import matplotlib.pyplot as plt
from multiprocessing import Pool
from sklearn.linear_model import LassoCV
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.model_selection import train_test_split

# from data import MW_PER_CORE    
MW_PER_CORE = 0.000015
from task import TIME_FACTOR

RAW_FEATURES = False
DOWN_SAMPLE = True
if RAW_FEATURES:
    DOWN_SAMPLE = True

EXTRA_FEATURES = False
POLY = False
SLO = 8  # SLO in hours

orig_cols = [
    'cum_wait_penalty',
    'cum_delayed_power',
    'convex_wait_penalty',
    'jobs_affected',
    'tardiness_penalty',
    'suspension_impact_s',
    'avg_run_length_after_suspension',
    'degree_of_resumption',
    'suspension_impact_e',
]

def summary():
    dataset_dir = 'datasets'
    files = sorted(f for f in os.listdir(dataset_dir) if f.endswith('_dataset.pkl'))
    summaries = [summarize_dataset(os.path.join(dataset_dir, f)) for f in files]
    df = pd.DataFrame(summaries)
    cols = [
        'dataset', 'samples',
        'waiting_mean', 'waiting_median', 'waiting_min', 'waiting_max',
        'd_power_avg_mean', 'd_power_avg_median', 'd_power_avg_min', 'd_power_avg_max',
        'd_power_max_mean', 'd_power_max_median', 'd_power_max_min', 'd_power_max_max',
        'd_power_min_mean', 'd_power_min_median', 'd_power_min_min', 'd_power_min_max'
    ]
    df = df[cols]
    print(df.to_markdown(index=False))

def plot_all(dataset_dir='datasets', output_dir='plots'):
    for policy in BASELINE_POLICIES:
        plot_waiting_hist(policy=policy, bins=30, output_dir=f"{output_dir}/waiting_hist", dataset_dir=dataset_dir)
        plot_sample_d_powers_colormap(policy, 
                                      num_samples=5, 
                                      seed=123, 
                                      output_dir=f"{output_dir}/d_power_colormap", 
                                      dataset_dir=dataset_dir, 
                                      delta=False)

def weighted_integral(J: np.ndarray, start: int, end: int) -> float:
    """
    Calculate weighted integral of J[start:end] with linearly decreasing weights.
    Weight w[k] = (end - k + 1) for k from start to end.
    """
    idx = np.arange(start, end + 1)
    weights = (end - idx + 1).astype(float)
    return np.dot(J[idx], weights)

def compute_features(
    data: list[dict],
    raw_features: bool = False,
    downsample: bool = True,
    downsample_factor: int = 12
) -> tuple[pd.DataFrame, np.ndarray]:
    """
    data: list of dicts each containing
      - 'd_power': list[float]
      - 'base_usage': list[float]
      - 'job_counts': list[int]
      - 'waiting_time': float

    raw_features: if True, returns element-wise d rather than engineered
    downsample: if True, first down-samples all three time series by 'downsample_factor'
    """
    N = len(data)
    T = len(data[0]['d_power'])
    y = np.zeros(N, dtype=float)

    if raw_features:
        H = T // downsample_factor if downsample else T
        X = np.zeros((N, H), dtype=float)
    else:
        X = np.zeros((N, len(orig_cols)), dtype=float)

    input_is_cpu = True

    for i, sample in enumerate(data):
        d = -np.array(sample['d_power'], dtype=float)
        U = np.array(sample['base_usage'], dtype=float)
        J = np.array(sample['job_counts'], dtype=float)
        y[i] = sample['waiting_time']

        if input_is_cpu:
            U *= MW_PER_CORE
            d *= MW_PER_CORE

        if downsample:
            new_len = T // downsample_factor
            d = d[: new_len*downsample_factor].reshape(new_len, downsample_factor).mean(axis=1)
            U = U[: new_len*downsample_factor].reshape(new_len, downsample_factor).mean(axis=1)
            J = J[: new_len*downsample_factor].reshape(new_len, downsample_factor).sum(axis=1)

        valid = (U > 0)
        d, U, J = d[valid], U[valid], J[valid]
        Tprime = len(d)

        if raw_features:
            row = np.zeros(X.shape[1], dtype=float)
            row[:Tprime] = d
            X[i, :] = row
        else:
            # 1) cum_wait_penalty
            cum1 = np.cumsum(J * d / U)
            X[i, 0] = np.sum(np.maximum(cum1, 0.0))

            # 2) cum_delayed_power
            cum2 = np.cumsum(d)
            X[i, 1] = np.sum(np.maximum(cum2, 0.0))

            # 3) convex_wait_penalty
            cum3 = np.cumsum(J * (d**2) / U)
            X[i, 2] = np.sum(np.maximum(cum3, 0.0))

            # 4) jobs_affected
            X[i, 3] = np.sum(J * np.maximum(d, 0.0) / U)

            # 5) tardiness penalty for jobs waiting longer than SLO
            t = np.arange(len(d))
            tardiness = np.maximum(t - SLO, 0)
            cum5 = np.cumsum(tardiness * J * d / U)
            X[i, 4] = np.sum(np.maximum(cum5, 0.0))

            # 6-8) suspension impact features
            suspension_impact_e = 0.0
            suspension_impact_s = 0.0
            t = 0
            while t < Tprime:
                if d[t] > 0 and (t == 0 or d[t - 1] < 0):
                    start = t
                    while t < Tprime and d[t] > 0:
                        t += 1
                    end = t - 1
                    duration = end - start + 1
                    
                    jobs_affected_end = J[end-1] if end > 0 else J[0]
                    jobs_affected_start = J[start]
                    
                    suspension_impact_e += duration * jobs_affected_end
                    suspension_impact_s += duration * jobs_affected_start
                else:
                    t += 1
            
            X[i, 8] = suspension_impact_e
            X[i, 5] = suspension_impact_s
            X[i, 6] = 0

            # 7) degree_of_resumption
            drops = [d[t] - d[t - 1] for t in range(1, Tprime) if d[t] < 0 and d[t - 1] >= 0]
            X[i, 7] = np.mean(drops) if drops else 0.0
            
    if raw_features:
        cols = [f"raw_d_{t}" for t in range(X.shape[1])]
    else:
        cols = orig_cols

    if not EXTRA_FEATURES and not RAW_FEATURES:
        df = pd.DataFrame(X, columns=cols)
        df = df.drop(columns=['suspension_impact_e', 'suspension_impact_s', 
                             'avg_run_length_after_suspension', 'degree_of_resumption'])
        return df, y

    df = pd.DataFrame(X, columns=cols)
    return df, y

def fit_and_predict(file_path) -> dict:
    """
    Load dataset, compute features, fit Lasso, and return predictions.
    """
    key = os.path.basename(file_path).replace('_dataset.pkl', '')
    with open(file_path, 'rb') as f:
        data = pickle.load(f)
    X, y = compute_features(data, raw_features=RAW_FEATURES, downsample=DOWN_SAMPLE)

    if POLY:
        pipeline = make_pipeline(
            PolynomialFeatures(degree=2, interaction_only=False, include_bias=False),
            StandardScaler(),
            LassoCV(cv=10, positive=True, max_iter=90000, random_state=0)
        )
    else:
        pipeline = make_pipeline(
            StandardScaler(),
            LassoCV(cv=10, positive=True, max_iter=90000, random_state=0)
        )
    pipeline.fit(X.values, y)

    lasso_cv = pipeline.named_steps['lassocv']
    best_alpha = lasso_cv.alpha_
    y_pred = pipeline.predict(X.values)

    mse = mean_squared_error(y, y_pred)
    mae = np.mean(np.abs(y - y_pred))
    
    threshold = 1e-3
    non_zero_mask = np.abs(y) > threshold
    if np.any(non_zero_mask):
        mape = np.mean(np.abs((y[non_zero_mask] - y_pred[non_zero_mask]) / y[non_zero_mask])) * 100
    else:
        mape = 0.0
    
    r2 = r2_score(y, y_pred)

    if POLY:
        poly = pipeline.named_steps['polynomialfeatures']
        lasso = pipeline.named_steps['lassocv']
        feature_names = poly.get_feature_names_out(orig_cols)
    else:
        feature_names = orig_cols
        lasso = lasso_cv

    if True:
        print("---"*10)
        print(f"Dataset: {key}")
        print(f"Chosen alpha: {best_alpha:.5f}")
        print(f"Intercept: {lasso_cv.intercept_:.4f}")
        print(f"MAPE: {mape:.4f}, R2: {r2:.4f}, MAE: {mae:.4f}")
        print("Coefficients:")

        for name, coef in zip(feature_names, lasso.coef_):
            print(f"{name:30s}  {coef:.6f}")

        print("---"*10)

    results = {
        'key': key,
        'y_true': y,
        'y_pred': y_pred,
        'best_alpha': best_alpha,
        'mae': mae,
        'mape': mape,
        'r2': r2,
        'mse': mse
    }
    return results

def fit_lasso_for_all_datasets(
    dataset_dir: str = 'datasets',
    SLO_windows: int = 8,
    processes: int = None
):
    """
    Fit Lasso for each dataset in parallel, then plot y_pred vs y_true.
    """
    files = sorted(
        os.path.join(dataset_dir, f)
        for f in os.listdir(dataset_dir)
        if any(f.startswith(f"{sched}_{cpol}") for sched in SCHED_POLICIES for cpol in CARBON_POLICIES)
    )
    
    args = [(fp, SLO_windows) for fp in files]
    with Pool(processes=processes) as pool:
        results = pool.starmap(fit_and_predict, args)

    with open('plots/lasso_results.pkl', 'wb') as f:
        pickle.dump(results, f)

    n = len(results)
    rows, cols = 4, 5
    fig, axes = plt.subplots(rows, cols, figsize=(7, 4), sharey='row')
    axes = axes.flatten()

    for ax, (key, y, yhat, alpha) in zip(axes, results):
        ax.scatter(y, yhat, s=5, alpha=0.5)
        vmin = min(y.min(), yhat.min())
        vmax = max(y.max(), yhat.max())
        ax.plot([vmin, vmax], [vmin, vmax], 'r--', linewidth=1)
        ax.set_title(f"{key}", fontsize=10)
        ax.legend([f'alpha={alpha:.4f}\nMAPE={mean_absolute_percentage_error(y, yhat):.4f}\nR2={r2_score(y, yhat):.4f}'])
        ax.set_xlim(vmin, vmax)
        ax.set_ylim(vmin, vmax)
        ax.set_xlabel('True waiting (hours)')
        ax.set_ylabel('Predicted waiting (hours)')

    for ax in axes[n:]:
        ax.axis('off')

    fig.suptitle(f'Lasso Predictions vs True (alpha={alpha})', fontsize=16)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])

    downsample_str = ''
    raw_str = ''
    if DOWN_SAMPLE:
        downsample_str = 'downsample_hourly'
    if RAW_FEATURES:
        raw_str = 'raw_features_d_power'
    file_name = f'plots/lasso_scatter_{downsample_str}_{raw_str}.pdf'
    plt.savefig(file_name)
    print(f'Saved scatter plot to {file_name}') 

def fit_and_evaluate_lasso_for_baseline(
    dataset_dir: str = 'datasets',
    waiting_time: str = '8x24',
    processes: int = None
):
    """
    Fit Lasso for BASELINE datasets in parallel, then plot y_pred vs y_true.
    """
    files = sorted(
        os.path.join(dataset_dir, f)
        for f in os.listdir(dataset_dir)
        if f.endswith('_dataset.pkl')
        if any(f.startswith(f"{sched}") for sched in BASELINE_POLICIES)
    )
    print(f"Found {len(files)} BASELINE datasets")

    args = [(fp,) for fp in files]
    with Pool(processes=processes) as pool:
        results = pool.starmap(fit_and_predict, args)
    
    all_y = np.concatenate([r['y_true'] for r in results])
    all_yhat = np.concatenate([r['y_pred'] for r in results])
    vmin = min(all_y.min(), all_yhat.min())
    vmax = max(all_y.max(), all_yhat.max())
    
    n = len(results)
    rows, cols = 3, 2
    fig, axes = plt.subplots(rows, cols, figsize=(6, 9), sharey='row')
    axes = axes.flatten()
    
    for ax, r in zip(axes, results):
        key = r['key']
        y = r['y_true']
        yhat = r['y_pred']
        alpha = r['best_alpha']
        mae = r['mae']
        r2 = r['r2']
        mse = r['mse']
        mape = r['mape']
        ax.scatter(y, yhat, s=5, alpha=0.5)
        ax.plot([vmin, vmax], [vmin, vmax], 'r--', linewidth=1)
        ax.set_title(f"{key}", fontsize=10)
        ax.set_xlim(vmin, vmax)
        ax.set_ylim(vmin, vmax)
        ax.set_xlabel('True waiting (hours)')
        ax.set_ylabel('Predicted waiting (hours)')
        ax.legend([f'alpha={alpha:.4f}\nMAPE={mape:.4f}\nR2={r2:.4f}\nMAE={mae:.4f}'])
    
    fig.suptitle(f'Lasso Predictioned Y vs True Y')
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    
    with_extra_features = '_with_extra_features' if EXTRA_FEATURES else ''
    with_poly = '_with_poly' if POLY else ''
    with_raw = '_raw_features' if RAW_FEATURES else ''
    file_name = f'plots/lasso_scatter_baseline{with_extra_features}{with_poly}{with_raw}.pdf'
    plt.savefig(file_name)
    file_name_png = file_name.replace('.pdf', '.png')
    plt.savefig(file_name_png)
    print(f'Saved scatter plot to {file_name}')

    results_df = pd.DataFrame({
        'policy': [r['key'] for r in results],
        'mae': [r['mae'] for r in results],
        'mape': [r['mape'] for r in results],
        'r2': [r['r2'] for r in results],
        'mse': [r['mse'] for r in results],
        'best_alpha': [r['best_alpha'] for r in results]
    })
    results_df.to_csv(f'plots/lasso_results_baseline{with_extra_features}{with_poly}{with_raw}.csv', index=False)
    print(f'Saved results to plots/lasso_results_baseline{with_extra_features}{with_poly}{with_raw}.csv')

def main():
    dataset_dir = 'azure100k-1x8-1000-10000'
    plot_all(dataset_dir=dataset_dir)
    fit_and_evaluate_lasso_for_baseline(
        dataset_dir=dataset_dir,
        waiting_time=dataset_dir.split('-')[-1],
        processes=10
    )

if __name__ == "__main__":
    main()