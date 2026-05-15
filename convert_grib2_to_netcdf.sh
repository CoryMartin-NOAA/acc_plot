#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${OUT_DIR:-.}"

usage() {
  cat <<'EOF'
Usage:
  bash ./convert_grib2_to_netcdf.sh INPUT1.grib2 [INPUT2.grib2 ...]

Environment:
  OUT_DIR   Output directory for NetCDF files (default: current directory)

Example:
  OUT_DIR=/lfs/h2/emc/ptmp/${USER} bash ./convert_grib2_to_netcdf.sh /path/to/exp/*.grib2
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

if ! command -v wgrib2 >/dev/null 2>&1; then
  echo "ERROR: wgrib2 is required but not found in PATH." >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

for in_file in "$@"; do
  if [[ ! -f "${in_file}" ]]; then
    echo "WARNING: missing input file ${in_file}; skipping." >&2
    continue
  fi

  base_name="$(basename "${in_file}")"
  stem="${base_name%.*}"
  out_file="${OUT_DIR}/${stem}.nc"

  if [[ -s "${out_file}" ]]; then
    echo "SKIP: ${out_file} already exists; ${in_file} already processed."
    continue
  fi

  echo "Converting ${in_file} -> ${out_file}"
  wgrib2 "${in_file}" -netcdf "${out_file}"
done
