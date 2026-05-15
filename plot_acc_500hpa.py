#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

nc = None
np = None
# Standard meteorological convention for "useful" ACC forecast skill.
SKILL_THRESHOLD = 0.6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compute and plot 500 hPa geopotential height anomaly correlation "
            "coefficient (ACC) from NetCDF files."
        )
    )
    parser.add_argument("--analysis-dir", required=True, type=Path)
    parser.add_argument("--control-dir", required=True, type=Path)
    parser.add_argument("--experiment-dir", required=True, type=Path)
    parser.add_argument("--climo-dir", required=True, type=Path)
    parser.add_argument("--output-plot", required=True, type=Path)
    parser.add_argument("--max-lead", type=int, default=120)
    return parser.parse_args()


def _ensure_dependencies() -> None:
    global nc, np
    if nc is None:
        try:
            import netCDF4 as _nc
        except ImportError as exc:
            raise ImportError("netCDF4 is required to read NetCDF inputs.") from exc
        nc = _nc
    if np is None:
        try:
            import numpy as _np
        except ImportError as exc:
            raise ImportError("numpy is required for ACC calculations.") from exc
        np = _np


def _find_hgt_name(ds) -> str:
    if "var7" in ds.variables:
        return "var7"
    if "HGT_500mb" in ds.variables:
        return "HGT_500mb"
    for name in ds.variables:
        if re.search(r"^HGT.*(?:_500mb|_500MB|500hPa)", name):
            return name
    raise KeyError("Could not find a 500 hPa geopotential height variable.")


def _parse_valid_dt(time_var) -> datetime:
    valid_num = float(time_var[0])
    units = getattr(time_var, "units", "")
    units_norm = units.strip().lower()

    if re.match(r"seconds since 1970-01-01", units_norm):
        return datetime.fromtimestamp(valid_num, tz=timezone.utc)

    # CDO output for GRIB->NetCDF often uses numeric YYYYMMDD.fractional_day.
    if re.fullmatch(r"day as %y%m%d\.%f", units.strip(), flags=re.IGNORECASE):
        frac_day, ymd_int = np.modf(valid_num)
        ymd = int(ymd_int)
        ymd_str = f"{ymd:08d}"
        base = datetime.strptime(ymd_str, "%Y%m%d").replace(tzinfo=timezone.utc)
        return base + timedelta(days=float(frac_day))

    valid_dt_raw = nc.num2date(valid_num, units=units)
    return datetime(
        valid_dt_raw.year,
        valid_dt_raw.month,
        valid_dt_raw.day,
        valid_dt_raw.hour,
        valid_dt_raw.minute,
        int(valid_dt_raw.second),
        tzinfo=timezone.utc,
    )


def _infer_ref_dt_from_filename(path: Path, valid_dt: datetime) -> datetime | None:
    name = path.name

    init_dt = None
    init_match = re.search(r"(19|20)\d{8}", name)
    if init_match:
        init_dt = datetime.strptime(init_match.group(0), "%Y%m%d%H").replace(tzinfo=timezone.utc)

    lead_match = re.search(r"(?:pgbf|f)(\d{2,3})", name, re.IGNORECASE)
    if lead_match:
        lead_hours = int(lead_match.group(1))
        if init_dt is not None:
            return init_dt
        return valid_dt - timedelta(hours=lead_hours)

    return init_dt


def _open_nc_file(path: Path) -> dict:
    _ensure_dependencies()
    with nc.Dataset(path) as ds:
        lat_name = "latitude" if "latitude" in ds.variables else "lat"
        lon_name = "longitude" if "longitude" in ds.variables else "lon"
        time_var = ds.variables["time"]
        hgt_name = _find_hgt_name(ds)

        valid_dt = _parse_valid_dt(time_var)

        # WGRIB2 NetCDF output commonly includes this custom epoch-seconds attribute.
        ref_epoch = getattr(time_var, "reference_time", None)
        ref_dt = None
        if ref_epoch is not None:
            ref_dt = datetime.fromtimestamp(float(ref_epoch), tz=timezone.utc)
        else:
            # Fallback for CDO-style outputs that do not carry a reference_time attribute.
            ref_dt = _infer_ref_dt_from_filename(path, valid_dt)

        hgt_var = ds.variables[hgt_name]
        if hgt_var.ndim == 4:
            hgt = np.array(hgt_var[0, 0, :, :], dtype=np.float64)
        elif hgt_var.ndim == 3:
            hgt = np.array(hgt_var[0, :, :], dtype=np.float64)
        elif hgt_var.ndim == 2:
            hgt = np.array(hgt_var[:, :], dtype=np.float64)
        else:
            raise ValueError(f"Unexpected rank {hgt_var.ndim} for HGT variable in {path}")

        fill_value = getattr(hgt_var, "_FillValue", None)
        if fill_value is not None:
            hgt = np.where(np.isclose(hgt, float(fill_value)), np.nan, hgt)

        lat = np.array(ds.variables[lat_name][:], dtype=np.float64)
        lon = np.array(ds.variables[lon_name][:], dtype=np.float64)

    return {"valid_dt": valid_dt, "ref_dt": ref_dt, "hgt": hgt, "lat": lat, "lon": lon}


def _acc_weighted(forecast_anom: np.ndarray, analysis_anom: np.ndarray, lat: np.ndarray) -> float:
    _ensure_dependencies()
    if lat.ndim != 1:
        raise ValueError("Latitude coordinate must be 1D for cosine-latitude ACC weighting.")

    weights = np.cos(np.deg2rad(lat))[:, None]
    valid = np.isfinite(forecast_anom) & np.isfinite(analysis_anom)
    if not np.any(valid):
        return np.nan

    f = np.where(valid, forecast_anom, 0.0)
    a = np.where(valid, analysis_anom, 0.0)
    w = np.where(valid, weights, 0.0)

    numer = np.sum(w * f * a)
    denom = np.sqrt(np.sum(w * f * f) * np.sum(w * a * a))
    if np.isclose(denom, 0.0):
        return np.nan
    return float(numer / denom)


def _regrid(data: "np.ndarray", src_lat: "np.ndarray", src_lon: "np.ndarray",
            tgt_lat: "np.ndarray", tgt_lon: "np.ndarray") -> "np.ndarray":
    """Bilinear interpolation of a 2-D (lat x lon) field onto a target regular grid."""
    try:
        from scipy.interpolate import RegularGridInterpolator
    except ImportError as exc:
        raise ImportError(
            "scipy is required when the climatology grid differs from the forecast grid."
        ) from exc
    # RegularGridInterpolator requires strictly ascending coordinates.
    if src_lat[0] > src_lat[-1]:
        src_lat = src_lat[::-1]
        data = data[::-1, :]
    interp = RegularGridInterpolator(
        (src_lat, src_lon), data, method="linear", bounds_error=False, fill_value=None
    )
    tgt_lat_2d, tgt_lon_2d = np.meshgrid(tgt_lat, tgt_lon, indexing="ij")
    return interp((tgt_lat_2d, tgt_lon_2d))


def _load_climo(climo_dir: Path, mmdd: str, valid_hour: int,
               tgt_lat: "np.ndarray", tgt_lon: "np.ndarray") -> dict:
    _ensure_dependencies()
    candidates = [
        climo_dir / f"hgt500_climo_{mmdd}.grb.nc",
        climo_dir / f"mean_{mmdd}.nc",
    ]
    path = next((c for c in candidates if c.exists()), None)
    if path is None:
        raise FileNotFoundError(f"Climatology file not found for MMDD={mmdd} in {climo_dir}")

    with nc.Dataset(path) as ds:
        lat_name = "latitude" if "latitude" in ds.variables else "lat"
        lon_name = "longitude" if "longitude" in ds.variables else "lon"
        src_lat = np.array(ds.variables[lat_name][:], dtype=np.float64)
        src_lon = np.array(ds.variables[lon_name][:], dtype=np.float64)

        if "var7" in ds.variables:
            # CDO-converted ERAclim format: var7(time, plev, lat, lon)
            var = ds.variables["var7"]
            n_times = var.shape[0]
            time_idx = min(valid_hour // 6, n_times - 1)
            hgt = np.array(var[time_idx, 0, :, :], dtype=np.float64)
        else:
            hgt_name = _find_hgt_name(ds)
            var = ds.variables[hgt_name]
            n_times = var.shape[0]
            time_idx = min(valid_hour // 6, n_times - 1) if n_times > 1 else 0
            hgt = np.array(var[time_idx, :, :], dtype=np.float64)

        fill_value = getattr(var, "_FillValue", None)
        if fill_value is not None:
            hgt = np.where(np.isclose(hgt, float(fill_value)), np.nan, hgt)

    # Interpolate onto the forecast/analysis grid when resolutions differ.
    if src_lat.shape != tgt_lat.shape or src_lon.shape != tgt_lon.shape or not (
        np.allclose(src_lat, tgt_lat, atol=1e-6, rtol=1e-9)
        and np.allclose(src_lon, tgt_lon, atol=1e-6, rtol=1e-9)
    ):
        hgt = _regrid(hgt, src_lat, src_lon, tgt_lat, tgt_lon)

    return {"hgt": hgt, "lat": tgt_lat, "lon": tgt_lon}


def _list_nc_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".nc")


def _same_grid(a: dict, b: dict) -> bool:
    return np.allclose(a["lat"], b["lat"], atol=1e-6, rtol=1e-9) and np.allclose(
        a["lon"], b["lon"], atol=1e-6, rtol=1e-9
    )


def _mean_by_leads(acc_by_lead: dict, leads: list[int]) -> list[float]:
    return [float(np.nanmean(acc_by_lead[lead])) if lead in acc_by_lead else np.nan for lead in leads]


def main() -> None:
    args = parse_args()

    _ensure_dependencies()
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise ImportError("matplotlib is required to generate the ACC plot.") from exc

    analysis_files = _list_nc_files(args.analysis_dir)
    control_files = _list_nc_files(args.control_dir)
    experiment_files = _list_nc_files(args.experiment_dir)
    if not analysis_files or not control_files or not experiment_files:
        raise ValueError("Analysis, control, and experiment directories must each contain .nc files.")

    analysis_by_valid = {}
    for path in analysis_files:
        info = _open_nc_file(path)
        analysis_by_valid[info["valid_dt"]] = info

    cached_climo = {}
    control_acc_by_lead = defaultdict(list)
    experiment_acc_by_lead = defaultdict(list)

    def process_forecast(path: Path, target: defaultdict) -> None:
        fcst = _open_nc_file(path)
        if fcst["ref_dt"] is None:
            raise ValueError(f"No time:reference_time attribute in {path}")

        lead = int(round((fcst["valid_dt"] - fcst["ref_dt"]).total_seconds() / 3600.0))
        if lead < 0 or lead > args.max_lead:
            return

        if fcst["valid_dt"] not in analysis_by_valid:
            return

        analysis = analysis_by_valid[fcst["valid_dt"]]
        grids_match_analysis = _same_grid(fcst, analysis)
        if not grids_match_analysis:
            raise ValueError(f"Grid mismatch between forecast and analysis for {path}")

        mmdd = fcst["valid_dt"].strftime("%m%d")
        valid_hour = fcst["valid_dt"].hour
        climo_key = (mmdd, valid_hour)
        if climo_key not in cached_climo:
            cached_climo[climo_key] = _load_climo(
                args.climo_dir, mmdd, valid_hour, fcst["lat"], fcst["lon"]
            )
        climo = cached_climo[climo_key]

        fcst_anom = fcst["hgt"] - climo["hgt"]
        anly_anom = analysis["hgt"] - climo["hgt"]
        target[lead].append(_acc_weighted(fcst_anom, anly_anom, fcst["lat"]))

    for path in control_files:
        process_forecast(path, control_acc_by_lead)
    for path in experiment_files:
        process_forecast(path, experiment_acc_by_lead)

    leads = sorted(set(control_acc_by_lead.keys()) | set(experiment_acc_by_lead.keys()))
    if not leads:
        raise ValueError("No matched valid times were found to compute ACC.")

    control_acc = _mean_by_leads(control_acc_by_lead, leads)
    experiment_acc = _mean_by_leads(experiment_acc_by_lead, leads)

    plt.figure(figsize=(9, 5))
    plt.plot(leads, control_acc, marker="o", linestyle="-", label="Control Run")
    plt.plot(leads, experiment_acc, marker="s", linestyle="--", label="Experiment")
    plt.axhline(0.0, color="k", linewidth=0.8)
    plt.axhline(
        SKILL_THRESHOLD,
        color="gray",
        linestyle=":",
        linewidth=1.0,
        label=f"Skill Threshold ({SKILL_THRESHOLD:.1f})",
    )
    plt.ylim(-0.2, 1.0)
    plt.xlim(0, args.max_lead)
    plt.xlabel("Lead time (hours)")
    plt.ylabel("ACC")
    plt.title("500 hPa Geopotential Height ACC")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.legend()
    plt.tight_layout()

    args.output_plot.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(args.output_plot, dpi=150)
    print(f"Saved plot to {args.output_plot}")


if __name__ == "__main__":
    main()
