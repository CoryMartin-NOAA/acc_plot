# acc_plot
quick computation and plot of 500 hPa GPH ACC scores

## Scripts

### 1) Build daily 500 hPa climatology files on WCOSS2

`./build_hgt500_climo.sh`

This script reads ERA5 climatology GRIB files named `mean_MMDD` from:

`/lfs/h2/emc/vpppg/noscrub/emc.vpppg/verification/EVS_fix/climos/atmos/era5`

For each date, it extracts `kpds5=7, kpds6=100, kpds7=500` (500 hPa geopotential
height), writes GRIB output `hgt500_climo_MMDD.grb`, then converts to NetCDF
`hgt500_climo_MMDD.grb.nc`.

Example:

```bash
bash ./build_hgt500_climo.sh 0101 0102
```

### 2) Compute and plot 500 hPa ACC (analysis vs control/experiment)

`./plot_acc_500hpa.py`

Inputs are directories containing single-valid-time NetCDF files (analysis,
control, experiment) with `HGT_500mb(time, latitude, longitude)`.

Example:

```bash
python ./plot_acc_500hpa.py \
  --analysis-dir /path/to/analysis_nc \
  --control-dir /path/to/control_nc \
  --experiment-dir /path/to/experiment_nc \
  --climo-dir /lfs/h2/emc/ptmp/${USER} \
  --output-plot /path/to/acc_500hpa.png
```
