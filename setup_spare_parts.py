"""
setup_spare_parts.py
--------------------
Khởi tạo bảng dim_spare_parts trong packaging_factory.db.
Mô phỏng module Quản lý Phụ tùng bảo trì SAP PM (Plant Maintenance) 
cho Nhà máy Nestlé Đồng Nai.
"""

import sqlite3
import os

DB_PATH = "packaging_factory.db"


def init_spare_parts_table():
    if not os.path.exists(DB_PATH):
        print(f"❌ Không tìm thấy database '{DB_PATH}'. Vui lòng kiểm tra lại thư mục!")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Tạo bảng dim_spare_parts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dim_spare_parts (
            part_id TEXT PRIMARY KEY,
            sap_material_code TEXT UNIQUE NOT NULL,
            part_name TEXT NOT NULL,
            target_machine_id TEXT NOT NULL,
            shelf_location TEXT NOT NULL,
            stock_quantity INTEGER NOT NULL,
            min_safety_stock INTEGER NOT NULL,
            unit_cost_vnd REAL NOT NULL,
            replacement_time_mins INTEGER NOT NULL,
            supplier TEXT NOT NULL
        )
    """)

    # 2. Tạo bảng nhật ký điều khiển tốc độ máy (Line Speed Derating Log)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fact_line_speed_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            machine_id TEXT NOT NULL,
            previous_speed_cph INTEGER NOT NULL,
            target_speed_cph INTEGER NOT NULL,
            reason TEXT NOT NULL,
            operator_notified BOOLEAN DEFAULT 1
        )
    """)

    # 3. Nạp danh mục phụ tùng thực tế của Nestlé Packaging Lines
    spare_parts_data = [
        (
            "PART-CUT-TP115",
            "SAP-MAT-991024",
            "Cụm dao cắt màng vô trùng Tetra Pak A3/Speed 115ml",
            "LINE_01",
            "Kệ B2-Ô 04 (Warehouse 1)",
            8,
            2,
            12500000.0,
            15,
            "Tetra Pak Parts Logistics"
        ),
        (
            "PART-JAW-TP180",
            "SAP-MAT-884012",
            "Cặp má hàm hàn siêu âm TBA/19 180ml (Sonotrode Jaw)",
            "LINE_02",
            "Kệ A1-Ô 12 (Warehouse 1)",
            4,
            1,
            28000000.0,
            25,
            "Tetra Pak Technical Service"
        ),
        (
            "PART-VLV-SIG250",
            "SAP-MAT-773099",
            "Cụm van chiết rót định lượng SIG CFA 312 250ml",
            "LINE_03",
            "Kệ C3-Ô 08 (Warehouse 2)",
            5,
            2,
            18500000.0,
            20,
            "SIG Combibloc Spare Parts"
        ),
        (
            "PART-BELT-SERVO",
            "SAP-MAT-662015",
            "Dây đai răng truyền động servo đồng tốc",
            "ALL_LINES",
            "Kệ D1-Ô 02 (Warehouse 1)",
            15,
            5,
            3200000.0,
            10,
            "Gates Industrial Vietnam"
        )
    ]

    cursor.executemany("""
        INSERT OR REPLACE INTO dim_spare_parts (
            part_id, sap_material_code, part_name, target_machine_id,
            shelf_location, stock_quantity, min_safety_stock, 
            unit_cost_vnd, replacement_time_mins, supplier
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, spare_parts_data)

    conn.commit()
    conn.close()

    print("================================================================================")
    print("✅ ĐÃ KHỞI TẠO BẢNG dim_spare_parts & fact_line_speed_log THÀNH CÔNG!")
    print("📦 Đã nạp danh mục phụ tùng chuẩn SAP PM cho các dây chuyền Nestlé.")
    print("================================================================================")


if __name__ == "__main__":
    init_spare_parts_table()