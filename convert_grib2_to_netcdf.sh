#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${OUT_DIR:-.}"

usage() {
  cat <<'EOF'
Usage:
  bash ./convert_grib2_to_netcdf.sh INPUT1.grib2 [INPUT2.grib2 ...]
  bash ./convert_grib2_to_netcdf.sh /path/to/root_dir

Environment:
  OUT_DIR   Output directory for NetCDF files (default: current directory)
  SRC_ROOT  Root directory to recursively scan for *.grib2 files when no
            positional args are provided

Example:
  OUT_DIR=/lfs/h2/emc/ptmp/${USER} bash ./convert_grib2_to_netcdf.sh /path/to/exp/*.grib2
  OUT_DIR=/lfs/h2/emc/ptmp/${USER} bash ./convert_grib2_to_netcdf.sh /lfs/h2/emc/da/noscrub/cory.r.martin/aigfs/com/prod_ic
EOF
}

SRC_ROOT="${SRC_ROOT:-}"

if ! command -v wgrib2 >/dev/null 2>&1; then
  echo "ERROR: wgrib2 is required but not found in PATH." >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

declare -a INPUT_FILES=()

if [[ $# -gt 0 ]]; then
  if [[ $# -eq 1 && -d "$1" ]]; then
    SRC_ROOT="$1"
  else
    INPUT_FILES=("$@")
  fi
fi

if [[ ${#INPUT_FILES[@]} -eq 0 ]]; then
  if [[ -z "${SRC_ROOT}" ]]; then
    usage
    exit 1
  fi

  while IFS= read -r -d '' f; do
    INPUT_FILES+=("$f")
  done < <(find "${SRC_ROOT}" -type f -name '*.grib2' -print0 | sort -z)

  if [[ ${#INPUT_FILES[@]} -eq 0 ]]; then
    echo "ERROR: no *.grib2 files found under ${SRC_ROOT}" >&2
    exit 1
  fi
fi

build_output_name() {
  local in_file="$1"
  local base_name stem

  base_name="$(basename "${in_file}")"
  stem="${base_name%.*}"

  # Pattern-based rename for paths like:
  # .../aigfs.20250301/00/aigfs.t00z.pres.f000.grib2
  # -> pgbf00.aigfs.2025030100.grib2.nc
  if [[ "${in_file}" =~ /([^/]+)\.([0-9]{8})/([0-9]{2})/[^/]+\.grib2$ ]]; then
    local model ymd cyc fh_raw fh_num fh_label
    model="${BASH_REMATCH[1]}"
    ymd="${BASH_REMATCH[2]}"
    cyc="${BASH_REMATCH[3]}"

    if [[ "${base_name}" =~ \.f([0-9]{3})\.grib2$ ]]; then
      fh_raw="${BASH_REMATCH[1]}"
      fh_num=$((10#${fh_raw}))
      if [[ ${fh_num} -lt 100 ]]; then
        fh_label="$(printf '%02d' "${fh_num}")"
      else
        fh_label="${fh_num}"
      fi
    else
      fh_label="00"
    fi

    printf 'pgbf%s.%s.%s%s.grib2.nc' "${fh_label}" "${model}" "${ymd}" "${cyc}"
    return
  fi

  printf '%s.nc' "${stem}"
}

for in_file in "${INPUT_FILES[@]}"; do
  if [[ ! -f "${in_file}" ]]; then
    echo "WARNING: missing input file ${in_file}; skipping." >&2
    continue
  fi

  out_name="$(build_output_name "${in_file}")"
  out_file="${OUT_DIR}/${out_name}"

  if [[ -s "${out_file}" ]]; then
    echo "SKIP: ${out_file} already exists; ${in_file} already processed."
    continue
  fi

  echo "Converting ${in_file} -> ${out_file}"
  wgrib2 "${in_file}" -netcdf "${out_file}"
done
