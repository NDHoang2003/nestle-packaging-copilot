"""
export_powerbi_data.py
----------------------
Exports Star Schema datasets from packaging_factory.db to CSVs 
for Power BI Dashboard visualization & Lean Six Sigma Before/After Reporting.
"""

import os
import sqlite3
import pandas as pd

DB_PATH = "packaging_factory.db"
EXPORT_DIR = "powerbi_exports"


def export_for_powerbi():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    tables = {
        "fact_sensor_telemetry": "fact_telemetry.csv",
        "fact_downtime_events": "fact_downtimes.csv",
        "fact_financial_roi_ledger": "fact_roi_ledger.csv",
        "fact_work_orders": "fact_work_orders.csv",
        "fact_line_speed_log": "fact_speed_derating.csv",
        "dim_spare_parts": "dim_spare_parts.csv",
        "dim_machines": "dim_machines.csv"
    }

    print("================================================================================")
    print("📤 XUẤT DỮ LIỆU STAR SCHEMA CHO POWER BI DASHBOARD")
    print(f"Thư mục lưu trữ: {os.path.abspath(EXPORT_DIR)}")
    print("================================================================================")

    for tbl, filename in tables.items():
        try:
            df = pd.read_sql_query(f"SELECT * FROM {tbl}", conn)
            filepath = os.path.join(EXPORT_DIR, filename)
            df.to_csv(filepath, index=False, encoding="utf-8-sig")
            print(f"✅ Đã xuất {tbl:<26} -> {filename:<22} ({len(df):>5} dòng)")
        except Exception as e:
            print(f"⚠️ Bỏ qua bảng {tbl}: {e}")

    conn.close()

    print("\n--------------------------------------------------------------------------------")
    print("💡 HƯỚNG DẪN IMPORT VÀO POWER BI:")
    print("1. Mở Power BI Desktop -> Get Data -> Folder (hoặc Text/CSV).")
    print(f"2. Trỏ vào thư mục: {os.path.abspath(EXPORT_DIR)}")
    print("3. Thiết lập mối quan hệ Model View (Star Schema):")
    print("   - dim_machines[line_id] -> fact_telemetry[line_id]")
    print("   - dim_machines[line_id] -> fact_downtimes[machine_id]")
    print("   - dim_machines[line_id] -> fact_roi_ledger[machine_id]")
    print("   - dim_spare_parts[target_machine_id] -> dim_machines[line_id]")
    print("================================================================================")


if __name__ == "__main__":
    export_for_powerbi()