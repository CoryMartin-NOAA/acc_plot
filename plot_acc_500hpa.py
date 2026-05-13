#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import re

nc = None
np = None
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
    if "HGT_500mb" in ds.variables:
        return "HGT_500mb"
    for name in ds.variables:
        if re.search(r"^HGT.*(?:_500mb|_500MB|500hPa)", name):
            return name
    raise KeyError("Could not find a 500 hPa geopotential height variable.")


def _open_nc_file(path: Path) -> dict:
    _ensure_dependencies()
    with nc.Dataset(path) as ds:
        lat_name = "latitude" if "latitude" in ds.variables else "lat"
        lon_name = "longitude" if "longitude" in ds.variables else "lon"
        time_var = ds.variables["time"]
        hgt_name = _find_hgt_name(ds)

        valid_num = float(time_var[0])
        valid_dt_raw = nc.num2date(valid_num, units=time_var.units)
        valid_dt = datetime(
            valid_dt_raw.year,
            valid_dt_raw.month,
            valid_dt_raw.day,
            valid_dt_raw.hour,
            valid_dt_raw.minute,
            int(valid_dt_raw.second),
            tzinfo=timezone.utc,
        )

        # WGRIB2 NetCDF output commonly includes this custom epoch-seconds attribute.
        ref_epoch = getattr(time_var, "reference_time", None)
        ref_dt = None
        if ref_epoch is not None:
            ref_dt = datetime.fromtimestamp(float(ref_epoch), tz=timezone.utc)

        hgt = np.array(ds.variables[hgt_name][0, :, :], dtype=np.float64)
        fill_value = getattr(ds.variables[hgt_name], "_FillValue", None)
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


def _load_climo(climo_dir: Path, mmdd: str) -> dict:
    candidates = [
        climo_dir / f"hgt500_climo_{mmdd}.grb.nc",
        climo_dir / f"mean_{mmdd}.nc",
    ]
    for candidate in candidates:
        if candidate.exists():
            return _open_nc_file(candidate)
    raise FileNotFoundError(f"Climatology file not found for MMDD={mmdd} in {climo_dir}")


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
        if mmdd not in cached_climo:
            cached_climo[mmdd] = _load_climo(args.climo_dir, mmdd)
        climo = cached_climo[mmdd]
        grids_match_climo = _same_grid(fcst, climo)
        if not grids_match_climo:
            raise ValueError(f"Grid mismatch between forecast and climatology for {path}")

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
