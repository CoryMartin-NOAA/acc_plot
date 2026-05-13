import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
import os

def calculate_acc(forecast, analysis, climatology):
    """
    Computes the Anomaly Correlation Coefficient.
    ACC = <(F-C)(A-C)> / sqrt(<(F-C)^2><(A-C)^2>)
    where F=Forecast, A=Analysis, C=Climatology.
    """
    f_prime = forecast - climatology
    a_prime = analysis - climatology
    
    # Weights for latitude (cosine of latitude)
    weights = np.cos(np.deg2rad(analysis.latitude))
    
    # Numerator: Covariance of anomalies
    numerator = (f_prime * a_prime).weighted(weights).mean(dim=['latitude', 'longitude'])
    
    # Denominator: Product of standard deviations
    f_var = (f_prime**2).weighted(weights).mean(dim=['latitude', 'longitude'])
    a_var = (a_prime**2).weighted(weights).mean(dim=['latitude', 'longitude'])
    denominator = np.sqrt(f_var * a_var)
    
    return numerator / denominator

def main():
    # --- Configuration ---
    # Update these paths to where your files are stored
    data_dir = "./data"
    lead_times = np.arange(0, 126, 24)  # 0, 24, 48, 72, 96, 120 hours
    var_name = "HGT_500mb"
    
    # For a real ACC, you need a climatology file. 
    # If you don't have one, you'd typically use a long-term average.
    # Here we assume a file exists or we use the analysis mean as a dummy placeholder.
    clim_path = os.path.join(data_dir, "climatology_500hPa.nc")

    acc_control = []
    acc_experiment = []

    for fhr in lead_times:
        # Example filename pattern based on your snippet: pgbf{fhr}.gfs.{valid_time}
        # Adjust logic if valid_time changes per file
        valid_time_str = "2025020900" 
        
        ana_file = f"{data_dir}/analysis.{valid_time_str}.nc"
        cntl_file = f"{data_dir}/cntl.f{fhr:02d}.{valid_time_str}.nc"
        expt_file = f"{data_dir}/expt.f{fhr:02d}.{valid_time_str}.nc"

        try:
            # Load datasets
            ds_ana = xr.open_dataset(ana_file)[var_name].squeeze()
            ds_cntl = xr.open_dataset(cntl_file)[var_name].squeeze()
            ds_expt = xr.open_dataset(expt_file)[var_name].squeeze()
            
            # Use analysis mean as climatology if file doesn't exist
            if os.path.exists(clim_path):
                ds_clim = xr.open_dataset(clim_path)[var_name].squeeze()
            else:
                ds_clim = ds_ana.mean() # Simple spatial mean if no clim file

            # Calculate ACC
            acc_control.append(calculate_acc(ds_cntl, ds_ana, ds_clim).values)
            acc_experiment.append(calculate_acc(ds_expt, ds_ana, ds_clim).values)
            
            print(f"Lead {fhr}h: CNTL={acc_control[-1]:.4f}, EXPT={acc_experiment[-1]:.4f}")

        except FileNotFoundError as e:
            print(f"Skipping hour {fhr}: {e}")

    # --- Plotting ---
    plt.figure(figsize=(10, 6))
    plt.plot(lead_times, acc_control, 'o-', label='Control Run', color='black', linewidth=2)
    plt.plot(lead_times, acc_experiment, 's--', label='Experiment', color='red', linewidth=2)
    
    # 0.6 is the standard threshold for "useful" skill
    plt.axhline(0.6, color='gray', linestyle=':', label='Skill Threshold (0.6)')
    
    plt.title(f"Anomaly Correlation Coefficient (ACC) at 500 hPa\nValid Time: {valid_time_str}", fontsize=14)
    plt.xlabel("Lead Time (hours)", fontsize=12)
    plt.ylabel("ACC", fontsize=12)
    plt.ylim(0, 1.05)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.savefig("acc_plot_500hPa.png", dpi=300)
    plt.show()

if __name__ == "__main__":
    main()