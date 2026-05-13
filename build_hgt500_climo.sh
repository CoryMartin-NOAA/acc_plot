#!/usr/bin/env bash
set -euo pipefail

CLIMO_SRC_DIR="${CLIMO_SRC_DIR:-/lfs/h2/emc/vpppg/noscrub/emc.vpppg/verification/EVS_fix/climos/atmos/era5}"
OUT_DIR="${OUT_DIR:-/lfs/h2/emc/ptmp/${USER}}"

if ! command -v wgrib >/dev/null 2>&1; then
  echo "ERROR: wgrib is required but not found in PATH." >&2
  exit 1
fi

if ! command -v cdo >/dev/null 2>&1; then
  echo "ERROR: cdo is required but not found in PATH." >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

build_one_day() {
  local mmdd="$1"
  local in_file="${CLIMO_SRC_DIR}/mean_${mmdd}"
  local out_grib="${OUT_DIR}/hgt500_climo_${mmdd}.grb"
  local out_nc="${out_grib}.nc"

  if [[ ! -f "${in_file}" ]]; then
    echo "WARNING: missing input file ${in_file}; skipping." >&2
    return 0
  fi

  echo "Processing ${in_file}"
  wgrib "${in_file}" \
    | grep ":kpds5=7:kpds6=100:kpds7=500:" \
    | wgrib -i "${in_file}" -grib -o "${out_grib}"

  cdo -f nc4 copy "${out_grib}" "${out_nc}"
  echo "Wrote ${out_grib} and ${out_nc}"
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
      02) max_day=29 ;;
      *) continue ;;
    esac
    for day in $(seq -w 1 "${max_day}"); do
      build_one_day "${month}${day}"
    done
  done
fi
