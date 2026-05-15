#!/usr/bin/env bash
# Extract 500 hPa geopotential height from GFS pgb (GRIB1) files and convert
# to NetCDF4.  Each output file is written alongside its input as
# <input_file>.hgt500.nc (or in OUT_DIR if set).
#
# Usage:
#   extract_hgt500_gfs.sh [file1 file2 ...]
#
# If no files are given the script searches SRC_DIR (default: current directory)
# for files matching common GFS pgb naming patterns:
#   pgbf*.gfs.*  (forecast files)
#   pgbanl*.gfs.* or pgbanl*.gdas.* (analysis files)
#
# Environment variables:
#   SRC_DIR   – directory to scan when no arguments are given  (default: $PWD)
#   OUT_DIR   – directory for output files; defaults to the same directory as
#               each input file
#   KEEP_GRIB – set to "1" to keep the intermediate single-record GRIB file

set -euo pipefail

SRC_DIR="${SRC_DIR:-${PWD}}"
OUT_DIR="${OUT_DIR:-}"
KEEP_GRIB="${KEEP_GRIB:-0}"

if ! command -v wgrib >/dev/null 2>&1; then
  echo "ERROR: wgrib is required but not found in PATH." >&2
  exit 1
fi

if ! command -v cdo >/dev/null 2>&1; then
  echo "ERROR: cdo is required but not found in PATH." >&2
  exit 1
fi

# Collect input files from arguments or directory scan.
declare -a INPUT_FILES=()
if [[ $# -gt 0 ]]; then
  INPUT_FILES=("$@")
else
  while IFS= read -r -d '' f; do
    INPUT_FILES+=("$f")
  done < <(find "${SRC_DIR}" -maxdepth 1 \( -name 'pgbf*.gfs.*' -o -name 'pgbanl*.gfs.*' -o -name 'pgbanl*.gdas.*' \) \
             ! -name '*.nc' ! -name '*.grb' -print0 | sort -z)
  if [[ ${#INPUT_FILES[@]} -eq 0 ]]; then
    echo "ERROR: no matching pgbf*/pgbanl* files found in ${SRC_DIR}" >&2
    exit 1
  fi
fi

process_one() {
  local in_file="$1"

  if [[ ! -f "${in_file}" ]]; then
    echo "WARNING: ${in_file} not found; skipping." >&2
    return 0
  fi

  local base
  base="$(basename "${in_file}")"

  local dest_dir
  if [[ -n "${OUT_DIR}" ]]; then
    dest_dir="${OUT_DIR}"
  else
    dest_dir="$(dirname "$(realpath "${in_file}")")"
  fi
  mkdir -p "${dest_dir}"

  local out_grib="${dest_dir}/${base}.hgt500.grb"
  local out_nc="${dest_dir}/${base}.hgt500.nc"

  if [[ -f "${out_nc}" ]]; then
    echo "SKIP: ${out_nc} already exists."
    return 0
  fi

  # Validate the file is readable by wgrib.
  if ! wgrib "${in_file}" >/dev/null 2>&1; then
    echo "WARNING: ${in_file} is not readable by wgrib (expected GRIB1); skipping." >&2
    return 0
  fi

  echo "Processing ${in_file}"

  # Extract 500 hPa geopotential height (HGT, kpds5=7, isobaric=kpds6=100, 500 mb=kpds7=500).
  local n_matched
  n_matched=$(wgrib "${in_file}" 2>/dev/null \
    | grep -c ":kpds5=7:kpds6=100:kpds7=500:" || true)

  if [[ "${n_matched}" -eq 0 ]]; then
    echo "WARNING: no 500 hPa HGT record found in ${in_file}; skipping." >&2
    return 0
  fi

  if ! wgrib "${in_file}" \
    | grep ":kpds5=7:kpds6=100:kpds7=500:" \
    | wgrib -i "${in_file}" -grib -o "${out_grib}"; then
    echo "WARNING: extraction failed for ${in_file}; skipping." >&2
    rm -f "${out_grib}"
    return 0
  fi

  if ! cdo -f nc4 copy "${out_grib}" "${out_nc}"; then
    echo "WARNING: CDO conversion failed for ${out_grib}; skipping." >&2
    rm -f "${out_grib}" "${out_nc}"
    return 0
  fi

  if [[ "${KEEP_GRIB}" != "1" ]]; then
    rm -f "${out_grib}"
  fi

  echo "Wrote ${out_nc}"
}

if [[ -n "${OUT_DIR}" ]]; then
  mkdir -p "${OUT_DIR}"
fi

for f in "${INPUT_FILES[@]}"; do
  process_one "${f}"
done
