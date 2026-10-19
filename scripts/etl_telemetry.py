#!/usr/bin/env python3
"""
AI4I ETL for Nestle Packaging Copilot
=====================================

Extracts the public AI4I 2020 benchmark, validates its schema and quality,
engineers physics-based features, and exports CSV/Parquet.

Important provenance rules:
- AI4I is a synthetic benchmark dataset, not Nestle factory telemetry.
- AI4I has no real timestamps; generated timestamps are simulation timestamps.
- AI4I Type L/M/H does not establish a real mapping to Nestle production lines.
  The optional Nestle scenario mapping is illustrative only.
- If the source cannot be loaded, the pipeline fails rather than silently
  replacing the benchmark with synthetic data.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import urllib.request
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (AI4I-ETL) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("AI4I_ETL")

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = SCRIPT_DIR.parent / "data"
DEFAULT_RAW_PATH = DEFAULT_DATA_DIR / "ai4i2020.csv"
DEFAULT_OUTPUT_DIR = DEFAULT_DATA_DIR / "processed"

DATASET_URLS = [
    "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip",
    "https://raw.githubusercontent.com/mandyiv/Predictive_Machine_Maintenance/main/ai4i2020.csv",
]

REQUIRED_COLUMNS = [
    "UDI",
    "Product ID",
    "Type",
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
    "Machine failure",
    "TWF",
    "HDF",
    "PWF",
    "OSF",
    "RNF",
]
LABEL_COLUMNS = ["Machine failure", "TWF", "HDF", "PWF", "OSF", "RNF"]
NUMERIC_COLUMNS = [
    "UDI",
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
    *LABEL_COLUMNS,
]

# This mapping is an illustrative scenario, not verified factory master data.
ILLUSTRATIVE_NESTLE_MAP = {
    "L": ("LINE_01", "Tetra Pak A3/Speed 115ml", "MILO_115ML"),
    "M": ("LINE_02", "Tetra Pak TBA/19 180ml", "MILO_180ML"),
    "H": ("LINE_03", "SIG Combibloc CFA 312", "NESTLE_PURE_250ML"),
}


def ensure_directories(data_dir: Path, output_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)


def download_ai4i_dataset(raw_path: Path, allow_download: bool = True) -> pd.DataFrame:
    """Load a local official-format CSV, optionally downloading the benchmark."""
    if raw_path.exists():
        logger.info("Loading local source dataset: %s", raw_path)
        return pd.read_csv(raw_path)

    if not allow_download:
        raise FileNotFoundError(
            f"Dataset not found at {raw_path}. Place ai4i2020.csv there "
            "or rerun with downloading enabled."
        )

    headers = {"User-Agent": "Nestle-Packaging-Copilot-AI4I-ETL/1.0"}
    errors: list[str] = []

    for url in DATASET_URLS:
        try:
            logger.info("Trying dataset source: %s", url)
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = response.read()

            if url.lower().endswith(".zip") or payload[:2] == b"PK":
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    csv_names = [
                        name for name in archive.namelist()
                        if name.lower().endswith(".csv")
                    ]
                    if not csv_names:
                        raise ValueError("ZIP archive contains no CSV file")
                    # Prefer the canonical AI4I file name if available.
                    selected = next(
                        (n for n in csv_names if "ai4i2020" in n.lower()),
                        csv_names[0],
                    )
                    with archive.open(selected) as file_obj:
                        df = pd.read_csv(file_obj)
            else:
                df = pd.read_csv(io.BytesIO(payload))

            validate_source_schema(df)
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(raw_path, index=False)
            logger.info("Downloaded and cached source dataset: %s", raw_path)
            return df
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            logger.warning("Source failed: %s", errors[-1])

    raise RuntimeError(
        "Unable to retrieve the AI4I dataset. No synthetic replacement was "
        "generated, to avoid confusing simulated rows with benchmark data.\n"
        + "\n".join(errors)
    )


def validate_source_schema(df: pd.DataFrame) -> None:
    missing = sorted(set(REQUIRED_COLUMNS) - set(df.columns))
    if missing:
        raise ValueError(
            "Source schema does not match AI4I 2020. Missing columns: "
            + ", ".join(missing)
        )
    if df.empty:
        raise ValueError("Source dataset is empty.")


def map_shift(hour: int) -> str:
    """Illustrative shift calendar; not a verified factory roster."""
    if 6 <= hour < 14:
        return "Shift 1"
    if 14 <= hour < 22:
        return "Shift 2"
    return "Shift 3"


def map_error_code(row: pd.Series) -> str:
    """
    Illustrative mapping from AI4I failure labels to project error categories.
    These codes are not confirmed Nestle CMMS/SAP error codes.
    """
    if row.get("HDF", 0) == 1:
        return "E-401"
    if row.get("TWF", 0) == 1:
        return "E-105"
    if row.get("PWF", 0) == 1:
        return "E-204"
    if row.get("OSF", 0) == 1:
        return "E-302"
    if row.get("RNF", 0) == 1:
        return "E-999"
    if row.get("Machine failure", 0) == 1:
        return "E-999"
    return "NORMAL"


def validate_and_quarantine(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Validate source rows; quarantine invalid rows instead of imputing them."""
    validate_source_schema(df_raw)
    df = df_raw[REQUIRED_COLUMNS].copy()
    rows_input = len(df)

    # Convert expected numeric values. Invalid text becomes NaN and is quarantined.
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Product ID"] = df["Product ID"].astype("string").str.strip()
    df["Type"] = df["Type"].astype("string").str.strip()

    duplicate_exact = df.duplicated(keep="first")
    exact_duplicates_removed = int(duplicate_exact.sum())
    df = df.loc[~duplicate_exact].copy()

    reasons = pd.Series("", index=df.index, dtype="string")

    def flag(mask: pd.Series, reason: str) -> None:
        nonlocal reasons
        mask = mask.fillna(True)
        reasons.loc[mask] = reasons.loc[mask].apply(
            lambda old: f"{old}; {reason}" if old else reason
        )

    required_non_null = [
        "UDI", "Product ID", "Type", "Air temperature [K]",
        "Process temperature [K]", "Rotational speed [rpm]",
        "Torque [Nm]", "Tool wear [min]", *LABEL_COLUMNS,
    ]
    flag(df[required_non_null].isna().any(axis=1), "missing_or_non_numeric_required_value")
    flag(~df["Type"].isin(["L", "M", "H"]), "invalid_product_type")

    invalid_label = pd.Series(False, index=df.index)
    for col in LABEL_COLUMNS:
        invalid_label |= ~df[col].isin([0, 1])
    flag(invalid_label, "failure_label_not_binary")

    flag(
        (df["UDI"] <= 0)
        | (df["UDI"] % 1 != 0),
        "invalid_udi",
    )
    flag(
        (df["Air temperature [K]"] <= 0)
        | (df["Process temperature [K]"] <= 0)
        | (df["Rotational speed [rpm]"] <= 0)
        | (df["Torque [Nm]"] < 0)
        | (df["Tool wear [min]"] < 0),
        "sensor_value_out_of_basic_domain",
    )
    flag(
        df["UDI"].notna() & df["UDI"].duplicated(keep=False),
        "duplicate_udi",
    )

    # Avoid using hard-coded physical limits to delete unusual but potentially
    # valid benchmark values. Those should be examined as outliers separately.
    reject_mask = reasons.ne("")
    rejected = df.loc[reject_mask].copy()
    rejected["rejection_reason"] = reasons.loc[reject_mask]
    clean = df.loc[~reject_mask].copy()

    clean["UDI"] = clean["UDI"].astype("int64")
    for col in LABEL_COLUMNS:
        clean[col] = clean[col].astype("int8")

    reason_counts: dict[str, int] = {}
    if not rejected.empty:
        reason_counts = (
            rejected["rejection_reason"]
            .str.split("; ")
            .explode()
            .value_counts()
            .astype(int)
            .to_dict()
        )

    report = {
        "dataset": "AI4I 2020 Predictive Maintenance Dataset",
        "data_provenance": "public benchmark; not live Nestle factory telemetry",
        "rows_input": int(rows_input),
        "exact_duplicates_removed": exact_duplicates_removed,
        "rows_after_exact_deduplication": int(len(df)),
        "rows_accepted": int(len(clean)),
        "rows_quarantined": int(len(rejected)),
        "acceptance_rate": round(len(clean) / len(df), 6) if len(df) else 0.0,
        "quarantine_reason_counts": reason_counts,
        "null_counts_accepted_rows": {
            str(k): int(v) for k, v in clean.isna().sum().to_dict().items()
        },
        "machine_failure_count": int(clean["Machine failure"].sum()),
        "machine_failure_rate": (
            round(float(clean["Machine failure"].mean()), 6) if len(clean) else 0.0
        ),
        "failure_label_counts": {
            col: int(clean[col].sum()) for col in LABEL_COLUMNS
        },
    }
    return clean.reset_index(drop=True), rejected.reset_index(drop=True), report


def process_telemetry_features(
    df_raw: pd.DataFrame,
    start_time: datetime,
    sample_interval_minutes: int = 1,
    map_to_nestle_scenario: bool = False,
) -> pd.DataFrame:
    """
    Build analytical features.

    The generated timestamp is a synthetic ordering timeline because AI4I
    does not contain actual timestamps. The default type mapping remains
    benchmark-oriented unless the illustrative mapping flag is enabled.
    """
    if sample_interval_minutes <= 0:
        raise ValueError("sample_interval_minutes must be positive")

    df = df_raw.copy()
    df = df.sort_values("UDI").reset_index(drop=True)

    rename_map = {
        "UDI": "record_id",
        "Product ID": "product_code",
        "Type": "product_type",
        "Air temperature [K]": "raw_air_k",
        "Process temperature [K]": "raw_proc_k",
        "Rotational speed [rpm]": "speed_servo_rpm",
        "Torque [Nm]": "tension_torque_nm",
        "Tool wear [min]": "cutting_knife_wear_min",
    }
    df = df.rename(columns=rename_map)

    if map_to_nestle_scenario:
        line_map = ILLUSTRATIVE_NESTLE_MAP
        df["line_id"] = df["product_type"].map(lambda x: line_map[x][0])
        df["machine_name"] = df["product_type"].map(lambda x: line_map[x][1])
        df["sku_profile"] = df["product_type"].map(lambda x: line_map[x][2])
        mapping_mode = "illustrative_nestle_scenario_not_verified"
    else:
        df["line_id"] = df["product_type"].map(lambda x: f"AI4I_TYPE_{x}")
        df["machine_name"] = df["product_type"].map(lambda x: f"AI4I benchmark type {x}")
        df["sku_profile"] = df["product_type"].map(lambda x: f"AI4I_TYPE_{x}")
        mapping_mode = "benchmark_type_only"

    df["timestamp"] = [
        start_time + timedelta(minutes=i * sample_interval_minutes)
        for i in range(len(df))
    ]
    df["timestamp_str"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["timestamp_is_synthetic"] = True
    df["shift_id"] = df["timestamp"].dt.hour.map(map_shift)

    # Kelvin to Celsius. Delta between temperatures has the same numeric
    # magnitude in Kelvin and Celsius.
    df["temp_cleanroom_c"] = (df["raw_air_k"] - 273.15).round(2)
    df["temp_sonotrode_c"] = (df["raw_proc_k"] - 273.15).round(2)

    df["speed_servo_rpm"] = pd.to_numeric(df["speed_servo_rpm"], errors="raise").astype(float)
    df["tension_torque_nm"] = pd.to_numeric(df["tension_torque_nm"], errors="raise").astype(float)
    df["cutting_knife_wear_min"] = pd.to_numeric(
        df["cutting_knife_wear_min"], errors="raise"
    ).astype(int)

    df["delta_t"] = (df["temp_sonotrode_c"] - df["temp_cleanroom_c"]).round(2)

    # Difference is calculated within each benchmark type/illustrative line.
    df = df.sort_values(["line_id", "timestamp"]).reset_index(drop=True)
    df["dt_dt"] = (
        df.groupby("line_id")["temp_sonotrode_c"]
        .diff()
        .fillna(0.0)
        .round(3)
    )

    # P(kW) = Torque(Nm) * 2*pi*RPM / 60000.
    df["p_mech_kw"] = (
        df["tension_torque_nm"] * df["speed_servo_rpm"] * 2 * np.pi / 60000.0
    ).round(3)
    df["heat_strain_index"] = (
        (df["p_mech_kw"] * 100.0) / (df["delta_t"].abs() + 0.1)
    ).round(2)

    df["error_code"] = df.apply(map_error_code, axis=1)
    df["is_failure"] = df["Machine failure"].astype("int8")

    def evaluate_severity(row: pd.Series) -> str:
        if row["is_failure"] == 1:
            return "CRITICAL"
        if row["delta_t"] < 8.6 and row["speed_servo_rpm"] < 1380:
            return "WARNING"
        if row["cutting_knife_wear_min"] >= 200:
            return "WARNING"
        if row["p_mech_kw"] > 8.5:
            return "WARNING"
        return "NORMAL"

    df["alert_severity"] = df.apply(evaluate_severity, axis=1)
    df["mapping_mode"] = mapping_mode
    df["data_source"] = "AI4I_2020_benchmark"

    output_columns = [
        "record_id",
        "product_code",
        "product_type",
        "timestamp",
        "timestamp_str",
        "timestamp_is_synthetic",
        "shift_id",
        "line_id",
        "machine_name",
        "sku_profile",
        "temp_cleanroom_c",
        "temp_sonotrode_c",
        "speed_servo_rpm",
        "tension_torque_nm",
        "cutting_knife_wear_min",
        "delta_t",
        "dt_dt",
        "p_mech_kw",
        "heat_strain_index",
        "error_code",
        "is_failure",
        "TWF",
        "HDF",
        "PWF",
        "OSF",
        "RNF",
        "alert_severity",
        "mapping_mode",
        "data_source",
    ]
    return df.sort_values("timestamp").reset_index(drop=True)[output_columns]


def export_outputs(
    processed: pd.DataFrame,
    rejected: pd.DataFrame,
    report: dict[str, Any],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "cleaned_telemetry.csv"
    rejected_path = output_dir / "ai4i_rejected.csv"
    report_path = output_dir / "ai4i_quality_report.json"
    parquet_path = output_dir / "cleaned_telemetry.parquet"

    processed.to_csv(csv_path, index=False)
    rejected.to_csv(rejected_path, index=False)
    report["output_rows"] = int(len(processed))
    report["output_columns"] = list(processed.columns)
    report["output_timestamp_semantics"] = (
        "synthetic timeline; AI4I source has no timestamp field"
    )
    report["feature_mapping_semantics"] = (
        "illustrative mapping only; not verified against Nestle factory master data"
    )
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    logger.info("CSV exported: %s", csv_path)
    logger.info("Quarantine exported: %s", rejected_path)
    logger.info("Quality report exported: %s", report_path)

    try:
        processed.to_parquet(parquet_path, engine="pyarrow", index=False)
        logger.info("Parquet exported: %s", parquet_path)
    except (ImportError, ModuleNotFoundError):
        logger.warning("pyarrow is not installed; skipped Parquet output.")
    except Exception:
        logger.exception("Parquet export failed; CSV output is still available.")

    if not processed.empty:
        print("\n" + "=" * 76)
        print("AI4I ETL QUALITY SUMMARY")
        print("=" * 76)
        print(f"Accepted telemetry rows : {len(processed):,}")
        print(f"Quarantined rows        : {len(rejected):,}")
        print(f"Failure events          : {int(processed['is_failure'].sum()):,}")
        print(f"Failure rate            : {processed['is_failure'].mean() * 100:.2f}%")
        print(f"Timestamp semantics     : synthetic timeline")
        print(f"Mapping mode            : {processed['mapping_mode'].iloc[0]}")
        print("=" * 76 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL pipeline for AI4I 2020 dataset")
    parser.add_argument("--input", type=Path, default=DEFAULT_RAW_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--start-time",
        default="2026-03-01T06:00:00",
        help="Start of the synthetic timeline, ISO format; not source telemetry time",
    )
    parser.add_argument(
        "--sample-interval-minutes",
        type=int,
        default=1,
        help="Interval used for generated timestamps; not measured by AI4I",
    )
    parser.add_argument(
        "--map-to-nestle-scenario",
        action="store_true",
        help="Apply the illustrative L/M/H-to-Nestle mapping from the original script",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Do not download the dataset when the local CSV is missing",
    )
    args = parser.parse_args()

    data_dir = args.input.parent
    ensure_directories(data_dir, args.output_dir)
    start_time = datetime.fromisoformat(args.start_time)

    logger.info("=== START AI4I ETL ===")
    raw = download_ai4i_dataset(args.input, allow_download=not args.no_download)
    clean_source, rejected, report = validate_and_quarantine(raw)
    processed = process_telemetry_features(
        clean_source,
        start_time=start_time,
        sample_interval_minutes=args.sample_interval_minutes,
        map_to_nestle_scenario=args.map_to_nestle_scenario,
    )
    export_outputs(processed, rejected, report, args.output_dir)
    logger.info("=== AI4I ETL COMPLETE ===")


if __name__ == "__main__":
    main()
