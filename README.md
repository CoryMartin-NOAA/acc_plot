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

Note: the extractor uses `wgrib` KPDS matching and expects GRIB1-style
`mean_MMDD` input files.

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

For GRIB2 forecast inputs, use `./plot_acc_500hpa_grib2.py`.  Climatology can be
either GRIB2 (`hgt500_climo_MMDD*.grib2`) or NetCDF
(`hgt500_climo_MMDD.grb.nc`/`hgt500_climo_MMDD.nc`).  If only GRIB1 climo files
are present (e.g. `mean_MMDD`), generate NetCDF climo first with
`./build_hgt500_climo.sh`.

### 3) Convert experiment GRIB2 files to NetCDF

`./convert_grib2_to_netcdf.sh`

Converts one or more GRIB2 files using:

`wgrib2 input_file.grib2 -netcdf output_file.nc`

You can also point it at a root directory; it will recursively find all
`*.grib2` files and write all outputs into one flat directory (`OUT_DIR`).

For paths shaped like:

`.../aigfs.YYYYMMDD/HH/aigfs.tHHz.pres.fFFF.grib2`

the output filename is rewritten as:

`pgbfFF.aigfs.YYYYMMDDHH.grib2.nc`

Example:

```bash
OUT_DIR=/lfs/h2/emc/ptmp/${USER} bash ./convert_grib2_to_netcdf.sh /path/to/experiment/*.grib2

# Recursive mode from a product root:
OUT_DIR=/lfs/h2/emc/ptmp/${USER} \
  bash ./convert_grib2_to_netcdf.sh /lfs/h2/emc/da/noscrub/cory.r.martin/aigfs/com/prod_ic
```
