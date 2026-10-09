#!/usr/bin/env python3
"""
================================================================================
NESTLE DONG NAI FACTORY - INDUSTRIAL PACKAGING DIGITAL TWIN
Module: IoT Edge Gateway & Telemetry Stream Simulator (Phase 4.1)
Role: Simulates real-time PLC/SCADA sensor telemetry streaming into SQLite
Author: Nguyen Doan Hoang (Digital Technical Specialist Candidate)
Reviewed by: Lead Industrial Data & AI Engineer
================================================================================
"""

import os
import sys
import time
import sqlite3
import logging
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (IoT-Gateway) %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("TelemetryStreamer")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "packaging_factory.db"
DATA_DIR = BASE_DIR / "data"
PARQUET_PATH = DATA_DIR / "cleaned_telemetry.parquet"
CSV_PATH = DATA_DIR / "cleaned_telemetry.csv"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def ensure_edge_buffer_table(conn: sqlite3.Connection):
    """
    Tạo bảng đệm trạng thái thời gian thực (realtime_edge_buffer)
    Lưu giữ giá trị cảm biến mới nhất của từng dây chuyền (Digital Twin State).
    """
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS realtime_edge_buffer (
        line_id TEXT PRIMARY KEY,
        record_id INTEGER NOT NULL,
        last_updated TEXT NOT NULL,
        machine_name TEXT NOT NULL,
        temp_cleanroom_c REAL NOT NULL,
        temp_sonotrode_c REAL NOT NULL,
        speed_servo_rpm REAL NOT NULL,
        tension_torque_nm REAL NOT NULL,
        cutting_knife_wear_min INTEGER NOT NULL,
        delta_t REAL NOT NULL,
        dt_dt REAL NOT NULL,
        p_mech_kw REAL NOT NULL,
        heat_strain_index REAL NOT NULL,
        error_code TEXT NOT NULL,
        is_failure INTEGER NOT NULL,
        alert_severity TEXT NOT NULL
    );
    """)
    conn.commit()


def load_telemetry_source() -> pd.DataFrame:
    """Nạp nguồn dữ liệu 10.000 records đã xử lý từ Pha 1."""
    if PARQUET_PATH.exists():
        df = pd.read_parquet(PARQUET_PATH)
    elif CSV_PATH.exists():
        df = pd.read_csv(CSV_PATH)
    else:
        raise FileNotFoundError("Không tìm thấy file telemetry sạch! Hãy chạy scripts/etl_telemetry.py trước.")
    return df


def stream_telemetry(line_filter: str = "LINE_01", delay_seconds: float = 0.5, max_steps: int = 50):
    """
    Phát dòng dữ liệu cảm biến mô phỏng nhịp đập thực tế của máy đóng gói.
    """
    df = load_telemetry_source()

    if line_filter != "ALL":
        df = df[df["line_id"] == line_filter].copy()

    df = df.sort_values(by="timestamp").reset_index(drop=True)
    total_records = len(df)

    conn = get_db_connection()
    ensure_edge_buffer_table(conn)
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print(f"   KHỞI ĐỘNG IOT EDGE GATEWAY - STREAMING TELEMETRY CHO DÂY CHUYỀN {line_filter}")
    print(f"   Tổng số bản ghi sẵn sàng: {total_records:,} | Chu kỳ phát: {delay_seconds}s/frame")
    print("=" * 80)

    try:
        step = 0
        for idx, row in df.iterrows():
            step += 1
            if max_steps and step > max_steps:
                logger.info(f"Đã đạt giới hạn mô phỏng kiểm thử ({max_steps} frames). Dừng stream.")
                break

            current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Ghi trạng thái nhịp tim vào bảng đệm SQLite (UPSERT)
            cursor.execute("""
            INSERT INTO realtime_edge_buffer (
                line_id, record_id, last_updated, machine_name, temp_cleanroom_c,
                temp_sonotrode_c, speed_servo_rpm, tension_torque_nm,
                cutting_knife_wear_min, delta_t, dt_dt, p_mech_kw,
                heat_strain_index, error_code, is_failure, alert_severity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(line_id) DO UPDATE SET
                record_id = excluded.record_id,
                last_updated = excluded.last_updated,
                temp_cleanroom_c = excluded.temp_cleanroom_c,
                temp_sonotrode_c = excluded.temp_sonotrode_c,
                speed_servo_rpm = excluded.speed_servo_rpm,
                tension_torque_nm = excluded.tension_torque_nm,
                cutting_knife_wear_min = excluded.cutting_knife_wear_min,
                delta_t = excluded.delta_t,
                dt_dt = excluded.dt_dt,
                p_mech_kw = excluded.p_mech_kw,
                heat_strain_index = excluded.heat_strain_index,
                error_code = excluded.error_code,
                is_failure = excluded.is_failure,
                alert_severity = excluded.alert_severity;
            """, (
                row["line_id"],
                int(row["record_id"]),
                current_time_str,
                row["machine_name"],
                row["temp_cleanroom_c"],
                row["temp_sonotrode_c"],
                row["speed_servo_rpm"],
                row["tension_torque_nm"],
                int(row["cutting_knife_wear_min"]),
                row["delta_t"],
                row["dt_dt"],
                row["p_mech_kw"],
                row["heat_strain_index"],
                row["error_code"],
                int(row["is_failure"]),
                row["alert_severity"]
            ))
            conn.commit()

            # Định dạng log in ra màn hình Terminal
            severity = row["alert_severity"]
            tag = "[NORMAL]  "
            if severity == "WARNING":
                tag = "\033[93m[WARNING] \033[0m"  # Màu vàng
            elif severity == "CRITICAL" or row["is_failure"] == 1:
                tag = "\033[91m[CRITICAL]\033[0m"  # Màu đỏ

            log_msg = (
                f"{tag} Frame #{step:03d} | Line: {row['line_id']} | "
                f"T_Sono: {row['temp_sonotrode_c']:>5.2f}°C | "
                f"ΔT: {row['delta_t']:>4.2f}°C | "
                f"RPM: {row['speed_servo_rpm']:>6.1f} | "
                f"Torque: {row['tension_torque_nm']:>4.1f}Nm | "
                f"P: {row['p_mech_kw']:>4.2f}kW | "
                f"Dao mòn: {row['cutting_knife_wear_min']:>3d}m | "
                f"Mã lỗi: {row['error_code']}"
            )
            print(log_msg)

            time.sleep(delay_seconds)

    except KeyboardInterrupt:
        logger.info("Nhận tín hiệu dừng từ người dùng (Ctrl+C). Đóng Gateway...")
    finally:
        conn.close()
        print("=" * 80)
        logger.info("Hoàn tất phiên phát dòng dữ liệu.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IoT Telemetry Stream Gateway")
    parser.add_argument("--line", type=str, default="LINE_01", help="Dây chuyền cần stream (LINE_01, LINE_02, LINE_03, ALL)")
    parser.add_argument("--delay", type=float, default=0.2, help="Độ trễ giữa các frame (giây)")
    parser.add_argument("--steps", type=int, default=25, help="Số khung hình mô phỏng kiểm thử (mặc định 25)")
    args = parser.parse_args()

    stream_telemetry(line_filter=args.line, delay_seconds=args.delay, max_steps=args.steps)