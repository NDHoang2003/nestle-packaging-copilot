"""
inspect_db.py
-------------
Database Inspector for Nestle Dong Nai Packaging Copilot.
Prints out records from all fact and dimension tables for operational verification.
"""

import sqlite3
import pandas as pd

DB_PATH = "packaging_factory.db"


def inspect_database():
    conn = sqlite3.connect(DB_PATH)
    
    print("================================================================================")
    print("🗄️ TỔNG QUAN HỆ CƠ SỞ DỮ LIỆU NHÀ MÁY (packaging_factory.db)")
    print("================================================================================")

    tables = [
        ("fact_sensor_telemetry", "Dữ liệu cảm biến SCADA thời gian thực (1 Hz)"),
        ("fact_downtime_events", "Nhật ký dừng máy sự cố (Downtime & Thất thoát)"),
        ("fact_work_orders", "Phiếu bảo trì công tác số hóa (Work Orders)"),
        ("fact_financial_roi_ledger", "Sổ cái thất thoát & Giá trị kinh tế bảo toàn (ROI)"),
        ("fact_line_speed_log", "Nhật ký lệnh điều khiển PLC Holding Registers"),
        ("dim_spare_parts", "Kho phụ tùng thay thế chuẩn SAP PM")
    ]

    for tbl, desc in tables:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {tbl} ORDER BY rowid DESC LIMIT 5", conn)
            total_count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"\n📊 BẢNG: {tbl} ({total_count:,} bản ghi) — {desc}")
            if not df.empty:
                print(df.to_string(index=False))
            else:
                print("   (Chưa có bản ghi nào)")
        except Exception as e:
            print(f"⚠️ Bảng {tbl} chưa được khởi tạo: {e}")

    conn.close()
    print("\n================================================================================")


if __name__ == "__main__":
    inspect_database()