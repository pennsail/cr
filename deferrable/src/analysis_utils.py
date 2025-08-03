import os
import pickle
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm

def load_dataset(policy, dataset_dir="datasets"):
    """
    Load the dataset pickle for a given policy.
    Returns None if file doesn't exist.
    """
    path = os.path.join(dataset_dir, f"{policy}_dataset.pkl")
    if not os.path.exists(path):
        print(f"Warning: Dataset file not found: {path}")
        return None
    with open(path, "rb") as f:
        data = pickle.load(f)
    return data

def inspect_row(policy, row_index, dataset_dir="datasets", output_dir="plots"):
    """
    Dive deep into a single row, save d_power time series as PDF:
      - Prints waiting time
      - Saves a PDF plot of d_power
    """
    data = load_dataset(policy, dataset_dir)
    entry = data[row_index]
    d_power = entry["d_power"]
    waiting = entry["waiting_time"]
    print(f"Policy: {policy}, Row: {row_index}, Waiting time: {waiting}")

    os.makedirs(output_dir, exist_ok=True)
    fig, ax = plt.subplots()
    ax.plot(d_power)
    ax.set_xlabel("Window index")
    ax.set_ylabel("d_power")
    ax.set_title(f"{policy} — Row {row_index} d_power")
    pdf_path = os.path.join(output_dir, f"{policy}_row{row_index}_d_power.pdf")
    fig.savefig(pdf_path)
    plt.close(fig)
    print(f"Saved d_power plot to {pdf_path}")

def plot_waiting_hist(policy, dataset_dir="datasets", output_dir="plots", bins=50):
    """
    Show and save a histogram of waiting times across all rows for a given policy.
    """
    data = load_dataset(policy, dataset_dir)
    if data is None:
        return
    waiting_times = [entry["waiting_time"] for entry in data]

    os.makedirs(output_dir, exist_ok=True)
    fig, ax = plt.subplots()
    ax.hist(waiting_times, bins=bins)
    ax.set_xlabel("Waiting time (simulation ticks)")
    ax.set_ylabel("Frequency")
    ax.set_title(f"{policy} Waiting Time Distribution")
    pdf_path = os.path.join(output_dir, f"{policy}_waiting_hist.pdf")
    fig.savefig(pdf_path)
    fig.savefig(pdf_path.replace('.pdf', '.png'), dpi=300)
    plt.close(fig)
    print(f"Saved waiting time histogram to {pdf_path}")

def plot_sample_d_powers(policy, dataset_dir="datasets", output_dir="plots", num_samples=10, seed=None):
    """
    Plot and save time series of d_power for a random subset of rows.
    """
    data = load_dataset(policy, dataset_dir)
    if data is None:
        return
    n = len(data)
    if seed is not None:
        np.random.seed(seed)
    indices = np.random.choice(n, size=min(num_samples, n), replace=False)

    os.makedirs(output_dir, exist_ok=True)
    fig, ax = plt.subplots()
    for idx in indices:
        dp = data[idx]["d_power"]
        ax.plot(dp, alpha=0.7)
    ax.set_xlabel("Window index")
    ax.set_ylabel("d_power")
    ax.set_title(f"{policy} — Sample {len(indices)} d_power Time Series")
    pdf_path = os.path.join(output_dir, f"{policy}_sample_d_powers.pdf")
    fig.savefig(pdf_path)
    plt.close(fig)
    print(f"Saved sample d_power time series to {pdf_path}")

def plot_sample_d_powers_colormap(
    policy,
    dataset_dir="datasets",
    output_dir="plots",
    num_samples=10,
    seed=None,
    delta=True,
):
    """
    Plot and save time series of d_power for a random subset of rows,
    using color intensity to represent each row's waiting time.
    """
    data = load_dataset(policy, dataset_dir)
    if data is None:
        return
    n = len(data)
    if seed is not None:
        np.random.seed(seed)
    indices = np.random.choice(n, size=min(num_samples, n), replace=False)

    waits = np.array([data[idx]["waiting_time"]/24 for idx in indices])
    norm = plt.Normalize(vmin=waits.min(), vmax=waits.max())
    cmap = cm.get_cmap('viridis')

    os.makedirs(output_dir, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4))
    for idx in indices:
        if delta:
            dp = -np.array(data[idx]["d_power"])
        else:
            dp = data[idx]["pol_usage"]
        w = data[idx]["waiting_time"] / 24
        color = cmap(norm(w))
        ax.plot(dp, color=color, alpha=0.9)
    ax.set_xlabel("Window index")
    if delta:
        ax.set_ylabel("d_power (# of cores)")
    else:
        ax.set_ylabel("Power Usage (# of cores)")
    ax.set_title(f"{policy} — Sample {len(indices)} Scheduling Results")
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax)
    cbar.set_label('Waiting time (days)')
    
    pdf_path = os.path.join(output_dir, f"{policy}_sample_d_powers_colormap.pdf")
    fig.savefig(pdf_path)
    fig.savefig(pdf_path.replace('.pdf', '.png'), dpi=300)
    plt.close(fig)
    print(f"Saved colored sample d_power time series to {pdf_path}")

def summarize_dataset(path):
    with open(path, 'rb') as f:
        data = pickle.load(f)
    waiting_times = np.array([item['waiting_time'] for item in data])
    d_means = np.array([np.mean(item['d_power']) for item in data])
    d_maxs = np.array([np.max(item['d_power']) for item in data])
    d_mins = np.array([np.min(item['d_power']) for item in data])
    return {
        'dataset': os.path.basename(path).replace('_dataset.pkl', ''),
        'samples': len(data),
        'waiting_mean': waiting_times.mean(),
        'waiting_median': np.median(waiting_times),
        'waiting_min': waiting_times.min(),
        'waiting_max': waiting_times.max(),
        'd_power_avg_mean': d_means.mean(),
        'd_power_avg_median': np.median(d_means),
        'd_power_avg_min': d_means.min(),
        'd_power_avg_max': d_means.max(),
        'd_power_max_mean': d_maxs.mean(),
        'd_power_max_median': np.median(d_maxs),
        'd_power_max_min': d_maxs.min(),
        'd_power_max_max': d_maxs.max(),
        'd_power_min_mean': d_mins.mean(),
        'd_power_min_median': np.median(d_mins),
        'd_power_min_min': d_mins.min(),
        'd_power_min_max': d_mins.max(),
    }

def main():
    policy = "suspend-resume_oracle"
    row_index = 0
    dataset_dir = "datasets"
    output_dir = "plots"

    inspect_row(policy, row_index, dataset_dir, output_dir)
    plot_waiting_hist(policy, dataset_dir, output_dir)
    plot_sample_d_powers(policy, dataset_dir, output_dir)
    plot_sample_d_powers_colormap(policy, dataset_dir, output_dir)

if __name__ == "__main__":
    main()