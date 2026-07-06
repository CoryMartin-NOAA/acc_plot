#!/usr/bin/env bash
# build_hgt500_climo_grib2.sh
#
# Extract 500 hPa geopotential height from GRIB2 climatology source files and
# write per-day GRIB2 output files that are directly readable by
# plot_acc_500hpa_grib2.py via grib2io.
#
# This is the GRIB2 counterpart of build_hgt500_climo.sh (which expects GRIB1
# source files and produces GRIB1 + NetCDF output).  Use this script when your
# source climatology files are already in GRIB2 format.
#
# Usage:
#   bash ./build_hgt500_climo_grib2.sh [MMDD ...]
#
# When no arguments are supplied every calendar day (0101–1231, plus 0229) is
# processed.  Supply one or more MMDD tokens to process specific days only.
#
# Environment variables:
#   CLIMO_SRC_DIR  Directory containing GRIB2 source files named mean_MMDD
#                  (default: /lfs/h2/emc/vpppg/noscrub/emc.vpppg/verification/EVS_fix/climos/atmos/era5)
#   OUT_DIR        Directory where per-day GRIB2 files are written
#                  (default: /lfs/h2/emc/ptmp/${USER}/climo)
#
# Output files are named:  hgt500_climo_MMDD.grb2
# These names are recognised by the _load_climo() function in
# plot_acc_500hpa_grib2.py without any further configuration.

set -euo pipefail

CLIMO_SRC_DIR="${CLIMO_SRC_DIR:-/lfs/h2/emc/vpppg/noscrub/emc.vpppg/verification/EVS_fix/climos/atmos/era5}"
OUT_DIR="${OUT_DIR:-/lfs/h2/emc/ptmp/${USER}/climo}"

if ! command -v wgrib2 >/dev/null 2>&1; then
  echo "ERROR: wgrib2 is required but not found in PATH." >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

build_one_day() {
  local mmdd="$1"
  local in_file="${CLIMO_SRC_DIR}/mean_${mmdd}"
  local out_grb2="${OUT_DIR}/hgt500_climo_${mmdd}.grb2"

  if [[ -s "${out_grb2}" ]]; then
    echo "SKIP: ${out_grb2} already exists."
    return 0
  fi

  if [[ ! -f "${in_file}" ]]; then
    echo "WARNING: missing input file ${in_file}; skipping." >&2
    return 0
  fi

  echo "Processing ${in_file}"

  # wgrib2 -match filters messages whose inventory line contains the pattern.
  # The standard wgrib2 inventory for 500 hPa geopotential height is:
  #   N:offset:d=YYYYMMDD:HGT:500 mb:...
  if ! wgrib2 "${in_file}" -match ":HGT:500 mb:" -grib2 "${out_grb2}" > /dev/null; then
    echo "WARNING: could not extract 500 hPa HGT from ${in_file}; skipping." >&2
    rm -f "${out_grb2}"
    return 0
  fi

  if [[ ! -s "${out_grb2}" ]]; then
    echo "WARNING: no 500 hPa HGT messages matched in ${in_file}; skipping." >&2
    rm -f "${out_grb2}"
    return 0
  fi

  echo "Wrote ${out_grb2}"
}

if [[ $# -gt 0 ]]; then
  for mmdd in "$@"; do
    build_one_day "${mmdd}"
  done
else
  for month in $(seq -w 1 12); do
    case "${month}" in
      01|03|05|07|08|10|12) max_day=31 ;;
      04|06|09|11) max_day=30 ;;
      # Include leap-day climatology (0229) when available.
      02) max_day=29 ;;
      *) continue ;;
    esac
    for day in $(seq -w 1 "${max_day}"); do
      build_one_day "${month}${day}"
    done
  done
fi
