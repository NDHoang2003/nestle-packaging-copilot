#!/usr/bin/env python3
"""
================================================================================
NESTLE DONG NAI FACTORY - INDUSTRIAL PACKAGING DIGITAL TWIN
Module: IoT Edge Gateway Simulator (Closed-Loop Handshake - Clean Output Edition)
Mechanism:
  - Streams telemetry frames sequentially.
  - Activates Safety Interlock upon failure (Single clean notification).
  - Silent Polling: Silently waits in background until AI Copilot dispatches Work Order.
  - Automatically clears fault, resets interlock, and resumes streaming.
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
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def ensure_edge_buffer_table(conn: sqlite3.Connection):
    """Khởi tạo và tự động migrate các cột Handshake cần thiết."""
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
        alert_severity TEXT NOT NULL,
        interlock_latched INTEGER NOT NULL DEFAULT 0,
        machine_state TEXT NOT NULL DEFAULT 'RUNNING',
        active_work_order_id TEXT DEFAULT NULL
    );
    """)

    cursor.execute("PRAGMA table_info(realtime_edge_buffer);")
    existing_cols = [row[1] for row in cursor.fetchall()]
    
    if "interlock_latched" not in existing_cols:
        cursor.execute("ALTER TABLE realtime_edge_buffer ADD COLUMN interlock_latched INTEGER NOT NULL DEFAULT 0;")
    if "machine_state" not in existing_cols:
        cursor.execute("ALTER TABLE realtime_edge_buffer ADD COLUMN machine_state TEXT NOT NULL DEFAULT 'RUNNING';")
    if "active_work_order_id" not in existing_cols:
        cursor.execute("ALTER TABLE realtime_edge_buffer ADD COLUMN active_work_order_id TEXT DEFAULT NULL;")
    
    conn.commit()


def load_telemetry_source() -> pd.DataFrame:
    if PARQUET_PATH.exists():
        df = pd.read_parquet(PARQUET_PATH)
    elif CSV_PATH.exists():
        df = pd.read_csv(CSV_PATH)
    else:
        raise FileNotFoundError("Không tìm thấy file telemetry sạch! Hãy chạy scripts/etl_telemetry.py trước.")
    return df


def stream_telemetry(line_filter: str = "LINE_01", delay_seconds: float = 0.3, max_steps: int = 100):
    df = load_telemetry_source()

    if line_filter != "ALL":
        df = df[df["line_id"] == line_filter].copy()

    df = df.sort_values(by="timestamp").reset_index(drop=True)
    total_records = len(df)

    conn = get_db_connection()
    ensure_edge_buffer_table(conn)
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print(f"   KHỞI ĐỘNG IOT EDGE GATEWAY (CLOSED-LOOP DIGITAL TWIN)")
    print(f"   Dây chuyền: {line_filter} | Tổng số bản ghi: {total_records:,}")
    print(f"   Cơ chế: Safety Interlock Latch & Silent Handshake")
    print("=" * 80)

    try:
        step = 0
        for idx, row in df.iterrows():
            step += 1
            if max_steps and step > max_steps:
                logger.info(f"Đã đạt giới hạn mô phỏng kiểm thử ({max_steps} frames). Dừng stream.")
                break

            current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            is_fail = int(row["is_failure"])
            severity = row["alert_severity"]
            err_code = str(row["error_code"]).strip()
            line_id = row["line_id"]

            is_critical_fault = (is_fail == 1) or (severity == "CRITICAL") or (err_code not in ["NORMAL", "NONE", ""])

            # Cập nhật buffer thời gian thực
            cursor.execute("""
            INSERT INTO realtime_edge_buffer (
                line_id, record_id, last_updated, machine_name, temp_cleanroom_c,
                temp_sonotrode_c, speed_servo_rpm, tension_torque_nm,
                cutting_knife_wear_min, delta_t, dt_dt, p_mech_kw,
                heat_strain_index, error_code, is_failure, alert_severity,
                interlock_latched, machine_state, active_work_order_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                alert_severity = excluded.alert_severity,
                interlock_latched = excluded.interlock_latched,
                machine_state = excluded.machine_state,
                active_work_order_id = excluded.active_work_order_id;
            """, (
                line_id, int(row["record_id"]), current_time_str, row["machine_name"],
                row["temp_cleanroom_c"], row["temp_sonotrode_c"], row["speed_servo_rpm"],
                row["tension_torque_nm"], int(row["cutting_knife_wear_min"]), row["delta_t"],
                row["dt_dt"], row["p_mech_kw"], row["heat_strain_index"], err_code,
                is_fail, severity,
                1 if is_critical_fault else 0,
                "TRIPPED" if is_critical_fault else "RUNNING",
                None
            ))
            conn.commit()

            # Định dạng màu cho log frame
            tag = "\033[92m[NORMAL]  \033[0m"
            if severity == "WARNING":
                tag = "\033[93m[WARNING] \033[0m"
            elif is_critical_fault:
                tag = "\033[91m[CRITICAL]\033[0m"

            print(
                f"{tag} Frame #{step:03d} | Line: {line_id} | "
                f"T_Sono: {row['temp_sonotrode_c']:>5.2f}°C | ΔT: {row['delta_t']:>4.2f}°C | "
                f"RPM: {row['speed_servo_rpm']:>6.1f} | Torque: {row['tension_torque_nm']:>4.1f}Nm | "
                f"P: {row['p_mech_kw']:>4.2f}kW | Dao mòn: {row['cutting_knife_wear_min']:>3d}m | "
                f"Mã lỗi: {err_code}"
            )

            # ------------------------------------------------------------------
            # KHI CÓ SỰ CỐ: KHÓA DÂY CHUYỀN VÀ CHỜ TĨNH LẶNG (SILENT POLLING)
            # ------------------------------------------------------------------
            if is_critical_fault:
                print(
                    f"\n\033[91m🛑 [SAFETY INTERLOCK KÍCH HOẠT] {line_id} phát hiện sự cố {err_code} tại Frame #{step:03d}!\033[0m\n"
                    f"   >> Băng chuyền dừng khẩn cấp. Đang chờ Watchdog Agent tạo Work Order..."
                )

                # Vòng lặp chờ Handshake tĩnh lặng hoàn toàn (Không in log lặp)
                while True:
                    cursor.execute("""
                        SELECT machine_state, active_work_order_id 
                        FROM realtime_edge_buffer 
                        WHERE line_id = ?;
                    """, (line_id,))
                    status_row = cursor.fetchone()

                    # Khi Watchdog Agent đã bắn tín hiệu ACK_DISPATCHED kèm mã Work Order
                    if status_row and status_row[0] == "ACK_DISPATCHED" and status_row[1]:
                        wo_id = status_row[1]
                        print(
                            f"\033[92m✅ [HANDSHAKE ACK] Đã nhận Phiếu bảo trì {wo_id} từ AI Copilot!\033[0m\n"
                            f"   >> Mô phỏng KTV thực thi LOTO & khắc phục sự cố (2.0s)..."
                        )
                        time.sleep(2.0)

                        # Giải phóng Interlock, phục hồi trạng thái máy về RUNNING
                        reset_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cursor.execute("""
                            UPDATE realtime_edge_buffer
                            SET interlock_latched = 0,
                                machine_state = 'RUNNING',
                                active_work_order_id = NULL,
                                error_code = 'NORMAL',
                                is_failure = 0,
                                alert_severity = 'NORMAL',
                                last_updated = ?
                            WHERE line_id = ?;
                        """, (reset_time_str, line_id))
                        conn.commit()

                        print(f"\033[92m🔄 [MACHINE RESET] {line_id} đã hồi phục trạng thái RUNNING. Tiếp tục phát dòng dữ liệu!\033[0m\n")
                        break

                    # Kiểm tra ngầm mỗi 0.3s không in log
                    time.sleep(0.3)

            else:
                time.sleep(delay_seconds)

    except KeyboardInterrupt:
        logger.info("Nhận lệnh dừng (Ctrl+C). Đóng Gateway...")
    finally:
        conn.close()
        print("=" * 80)
        logger.info("Hoàn tất phiên mô phỏng IoT Gateway.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IoT Telemetry Stream Gateway (Closed-Loop Handshake)")
    parser.add_argument("--line", type=str, default="LINE_01", help="Dây chuyền cần stream (LINE_01, LINE_02, LINE_03, ALL)")
    parser.add_argument("--delay", type=float, default=0.25, help="Độ trễ giữa các frame khi bình thường (giây)")
    parser.add_argument("--steps", type=int, default=100, help="Số khung hình mô phỏng kiểm thử (mặc định 100)")
    args = parser.parse_args()

    stream_telemetry(line_filter=args.line, delay_seconds=args.delay, max_steps=args.steps)