#!/usr/bin/env python3
"""
================================================================================
NESTLE DONG NAI FACTORY - INDUSTRIAL PACKAGING DIGITAL TWIN
Module: Enterprise Relational Data Warehouse Modeling (Phase 2)
Database: packaging_factory.db (SQLite Star Schema / 3NF)
Author: Nguyen Doan Hoang (Digital Technical Specialist Candidate)
Reviewed by: Lead Industrial Data & AI Engineer
================================================================================
"""

import os
import sys
import sqlite3
import logging
from pathlib import Path
import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (Nestle-DB) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DatabaseSetup")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "packaging_factory.db"
DATA_DIR = BASE_DIR / "data"
PARQUET_PATH = DATA_DIR / "cleaned_telemetry.parquet"
CSV_PATH = DATA_DIR / "cleaned_telemetry.csv"


def create_connection():
    """Tạo kết nối SQLite có hỗ trợ khóa ngoại (Foreign Keys)."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def create_schema(cursor):
    """
    Khởi tạo cấu trúc bảng Star Schema chuẩn Enterprise.
    Xóa bảng cũ nếu tồn tại để tái tạo sạch sẽ.
    """
    logger.info("Đang khởi tạo cấu trúc bảng (DDL Schema)...")

    cursor.executescript("""
    -- 1. BẢNG CHIỀU: DÂY CHUYỀN THIẾT BỊ (dim_machines)
    DROP TABLE IF EXISTS fact_work_orders;
    DROP TABLE IF EXISTS fact_downtime_events;
    DROP TABLE IF EXISTS fact_sensor_telemetry;
    DROP TABLE IF EXISTS dim_error_catalog;
    DROP TABLE IF EXISTS dim_machines;

    CREATE TABLE dim_machines (
        line_id TEXT PRIMARY KEY,
        machine_name TEXT NOT NULL,
        manufacturer TEXT NOT NULL,
        model TEXT NOT NULL,
        rated_capacity_cph INTEGER NOT NULL, -- Công suất định danh: Hộp/Giờ (Cartons Per Hour)
        target_product TEXT NOT NULL,
        cleanroom_area TEXT NOT NULL,
        commissioning_date TEXT NOT NULL,
        status TEXT DEFAULT 'ACTIVE'
    );

    -- 2. BẢNG CHIỀU: SỔ TAY MÃ LỖI BẢO TRÌ TIÊU CHUẨN (dim_error_catalog)
    CREATE TABLE dim_error_catalog (
        error_code TEXT PRIMARY KEY,
        failure_type TEXT NOT NULL,
        description TEXT NOT NULL,
        root_cause_category TEXT NOT NULL,
        standard_recovery_time_min REAL NOT NULL,
        loto_procedure_required INTEGER NOT NULL, -- 1: Bắt buộc LOTO, 0: Kiểm tra nhanh
        required_ppe TEXT NOT NULL,
        sop_reference TEXT NOT NULL
    );

    -- 3. BẢNG SỰ KIỆN: DỮ LIỆU CẢM BIẾN TELEMETRY (fact_sensor_telemetry)
    CREATE TABLE fact_sensor_telemetry (
        record_id INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        shift_id TEXT NOT NULL,
        line_id TEXT NOT NULL,
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
        FOREIGN KEY (line_id) REFERENCES dim_machines(line_id),
        FOREIGN KEY (error_code) REFERENCES dim_error_catalog(error_code)
    );

    -- Tối ưu hóa truy vấn thời gian thực cho Streamlit & AI Agent
    CREATE INDEX idx_telemetry_timestamp ON fact_sensor_telemetry(timestamp);
    CREATE INDEX idx_telemetry_line_time ON fact_sensor_telemetry(line_id, timestamp);
    CREATE INDEX idx_telemetry_failure ON fact_sensor_telemetry(is_failure, error_code);
    CREATE INDEX idx_telemetry_shift ON fact_sensor_telemetry(shift_id);

    -- 4. BẢNG SỰ KIỆN: SỰ CỐ DỪNG MÁY DOWNTIME (fact_downtime_events)
    CREATE TABLE fact_downtime_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id INTEGER NOT NULL,
        line_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        shift_id TEXT NOT NULL,
        error_code TEXT NOT NULL,
        downtime_duration_minutes REAL NOT NULL,
        impact_units_lost INTEGER NOT NULL,
        FOREIGN KEY (record_id) REFERENCES fact_sensor_telemetry(record_id),
        FOREIGN KEY (line_id) REFERENCES dim_machines(line_id),
        FOREIGN KEY (error_code) REFERENCES dim_error_catalog(error_code)
    );

    CREATE INDEX idx_downtime_line ON fact_downtime_events(line_id);
    CREATE INDEX idx_downtime_error ON fact_downtime_events(error_code);
    CREATE INDEX idx_downtime_shift ON fact_downtime_events(shift_id);

    -- 5. BẢNG SỰ KIỆN: PHIẾU BẢO TRÌ BẢO DƯỠNG (fact_work_orders)
    CREATE TABLE fact_work_orders (
        work_order_id TEXT PRIMARY KEY,
        event_id INTEGER NOT NULL,
        line_id TEXT NOT NULL,
        error_code TEXT NOT NULL,
        created_at TEXT NOT NULL,
        priority TEXT NOT NULL,
        loto_status TEXT NOT NULL DEFAULT 'PENDING_ISOLATION', -- PENDING_ISOLATION, VERIFIED_LOTO, RESTORED
        technician_assigned TEXT NOT NULL,
        resolution_notes TEXT,
        order_status TEXT NOT NULL DEFAULT 'OPEN', -- OPEN, IN_PROGRESS, CLOSED
        closed_at TEXT,
        FOREIGN KEY (event_id) REFERENCES fact_downtime_events(event_id),
        FOREIGN KEY (line_id) REFERENCES dim_machines(line_id),
        FOREIGN KEY (error_code) REFERENCES dim_error_catalog(error_code)
    );

    CREATE INDEX idx_wo_status ON fact_work_orders(order_status);
    CREATE INDEX idx_wo_line ON fact_work_orders(line_id);
    """);
    logger.info("Đã tạo hoàn tất Schema DDL với các quan hệ Khóa ngoại và Index tối ưu.")


def seed_dimension_tables(cursor):
    """
    Nạp dữ liệu danh mục chuẩn cho dim_machines và dim_error_catalog.
    """
    logger.info("Đang nạp dữ liệu Bảng Chiều (Dimension Tables)...")

    # Dữ liệu dim_machines
    machines_data = [
        (
            "LINE_01",
            "Tetra Pak A3/Speed 115ml",
            "Tetra Pak",
            "A3/Speed iLine",
            24000,
            "MILO_115ML",
            "Aseptic Cleanroom 1A",
            "2023-01-15",
            "ACTIVE"
        ),
        (
            "LINE_02",
            "Tetra Pak TBA/19 180ml",
            "Tetra Pak",
            "TBA/19 Slim",
            7500,
            "MILO_180ML",
            "Aseptic Cleanroom 1B",
            "2021-08-10",
            "ACTIVE"
        ),
        (
            "LINE_03",
            "SIG Combibloc CFA 312",
            "SIG Combibloc",
            "CFA 312-32",
            12000,
            "NESTLE_PURE_250ML",
            "Aseptic Cleanroom 2",
            "2022-04-20",
            "ACTIVE"
        )
    ]
    cursor.executemany("""
    INSERT INTO dim_machines VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, machines_data)

    # Dữ liệu dim_error_catalog
    catalog_data = [
        (
            "NORMAL",
            "No Failure",
            "Dây chuyền đang hoạt động trong ngưỡng chuẩn kỹ thuật",
            "Operations",
            0.0,
            0,
            "Standard Cleanroom PPE",
            "SOP-OPS-001"
        ),
        (
            "E-105",
            "Tool Wear Failure",
            "Mòn dao cắt bao bì định hình mép hộp - mép cắt không đứt gây kẹt phôi",
            "Mechanical Cutting",
            25.0,
            1,
            "Safety Glasses, Cut-Resistant Gloves Level 5",
            "SOP-MEC-105"
        ),
        (
            "E-401",
            "Heat Dissipation Failure",
            "Quá nhiệt đầu hàn siêu âm Sonotrode / nghẽn đường chiller làm mát",
            "Thermal & Ultrasonic",
            45.0,
            1,
            "Thermal Insulated Gloves, Face Shield, LOTO Padlock",
            "SOP-THM-401"
        ),
        (
            "E-204",
            "Power Failure",
            "Quá tải công suất động cơ Servo kéo màng giấy / Sụt áp biến tần",
            "Electrical & Drive",
            30.0,
            1,
            "Arc Flash Shield, Electrical Safety Gloves Class 0",
            "SOP-ELE-204"
        ),
        (
            "E-302",
            "Overstrain Failure",
            "Quá lực căng màng cuộn giấy vượt giới hạn bền - đứt cuộn giấy vô trùng",
            "Packaging Material Strain",
            35.0,
            1,
            "Cut-Resistant Gloves, Standard PPE, LOTO Padlock",
            "SOP-MAT-302"
        ),
        (
            "E-999",
            "Random Sensor / Line Jam",
            "Cảm biến quang học lệch vạch đọc mã / Kẹt bao bì đột xuất",
            "Automation & Optical",
            15.0,
            0,
            "Standard Cleanroom PPE, Anti-static Wristband",
            "SOP-AUT-999"
        )
    ]
    cursor.executemany("""
    INSERT INTO dim_error_catalog VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, catalog_data)
    logger.info("Đã nạp thành công dim_machines (3 dòng) và dim_error_catalog (6 dòng).")


def load_telemetry_and_derive_facts(conn):
    """
    Nạp 10.000 dòng telemetry từ Parquet/CSV vào fact_sensor_telemetry.
    Đồng thời tự động trích xuất fact_downtime_events và fact_work_orders.
    """
    logger.info("Đang đọc dữ liệu sạch từ Pha 1...")
    if PARQUET_PATH.exists():
        df = pd.read_parquet(PARQUET_PATH)
        logger.info(f"Đã nạp thành công từ: {PARQUET_PATH}")
    elif CSV_PATH.exists():
        df = pd.read_csv(CSV_PATH)
        logger.info(f"Đã nạp thành công từ: {CSV_PATH}")
    else:
        raise FileNotFoundError("Không tìm thấy cleaned_telemetry.parquet hoặc cleaned_telemetry.csv trong data/!")

    cursor = conn.cursor()

    # 1. Nạp dữ liệu vào fact_sensor_telemetry
    logger.info("Đang nạp 10.000 bản ghi vào fact_sensor_telemetry...")
    telemetry_records = df[[
        "record_id",
        "timestamp_str",
        "shift_id",
        "line_id",
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
        "alert_severity"
    ]].values.tolist()

    cursor.executemany("""
    INSERT INTO fact_sensor_telemetry VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, telemetry_records)
    logger.info(f"Đã nạp thành công {len(telemetry_records)} bản ghi telemetry.")

    # 2. Xây dựng fact_downtime_events từ các bản ghi có sự cố (is_failure == 1)
    logger.info("Đang trích xuất và tính toán fact_downtime_events...")
    failure_df = df[df["is_failure"] == 1].copy()

    # Lấy thông tin định mức thời gian và công suất máy để tính sản lượng thất thoát
    cursor.execute("SELECT line_id, rated_capacity_cph FROM dim_machines;")
    capacity_dict = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("SELECT error_code, standard_recovery_time_min FROM dim_error_catalog;")
    recovery_dict = {row[0]: row[1] for row in cursor.fetchall()}

    # Tái tạo thời gian dừng máy thực tế dựa trên định mức chuẩn + biến thiên ngẫu nhiên có kiểm soát
    np.random.seed(42)
    downtime_events = []
    work_orders = []

    technicians = ["KTV. Nguyen Van An", "KTV. Tran Dinh Binh", "KTV. Le Hoang Cuong", "KTV. Pham Minh Dung"]

    for idx, row in failure_df.iterrows():
        line = row["line_id"]
        err = row["error_code"]
        rec_id = int(row["record_id"])
        ts = str(row["timestamp_str"])
        shift = row["shift_id"]

        std_time = recovery_dict.get(err, 20.0)
        # Thời gian downtime thực tế dao động quanh định mức chuẩn (±20%)
        is_major_breakdown = np.random.rand() < 0.15

        if is_major_breakdown:
            # Sự cố lớn: mất 20 - 45 phút sửa chữa có LOTO
            actual_downtime = round(std_time * np.random.uniform(0.85, 1.25), 1)
        else:
            # Dừng nhỏ (Micro-stop): xử lý kẹt giấy, lau cảm biến chỉ mất 1 - 3 phút
            actual_downtime = round(np.random.uniform(1.0, 3.5), 1)

        # Sản lượng thất thoát (Lost Cartons) = (Công suất/giờ / 60) * số phút dừng máy
        cph = capacity_dict.get(line, 10000)
        units_lost = int((cph / 60.0) * actual_downtime)

        downtime_events.append((
            rec_id,
            line,
            ts,
            shift,
            err,
            actual_downtime,
            units_lost
        ))

    cursor.executemany("""
    INSERT INTO fact_downtime_events (record_id, line_id, timestamp, shift_id, error_code, downtime_duration_minutes, impact_units_lost)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """, downtime_events)
    logger.info(f"Đã trích xuất thành công {len(downtime_events)} sự cố dừng máy vào fact_downtime_events.")

    # 3. Xây dựng fact_work_orders khép kín tương ứng với các sự cố dừng máy
    logger.info("Đang sinh phiếu bảo trì khép kín fact_work_orders...")
    cursor.execute("SELECT event_id, line_id, error_code, timestamp FROM fact_downtime_events;")
    db_events = cursor.fetchall()

    for row in db_events:
        ev_id, line, err, ts = row
        wo_id = f"WO-{ts[:10].replace('-', '')}-{ev_id:04d}"

        priority = "P1_URGENT" if err in ["E-401", "E-204"] else "P2_HIGH"
        tech = np.random.choice(technicians)

        # Giả lập trạng thái bảo trì: 95% sự cố trong quá khứ đã được đóng (CLOSED), 5% gần nhất đang mở/xử lý
        if ev_id > len(db_events) - 15:
            order_status = "IN_PROGRESS"
            loto_status = "VERIFIED_LOTO"
            res_notes = "Đang cô lập nguồn điện và tiến hành cân chỉnh kỹ thuật."
            closed_at = None
        else:
            order_status = "CLOSED"
            loto_status = "RESTORED"
            res_notes = f"Đã khắc phục hoàn tất theo SOP chuẩn {err}. Bàn giao dây chuyền cho Trưởng ca."
            closed_at = ts

        work_orders.append((
            wo_id,
            ev_id,
            line,
            err,
            ts,
            priority,
            loto_status,
            tech,
            res_notes,
            order_status,
            closed_at
        ))

    cursor.executemany("""
    INSERT INTO fact_work_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, work_orders)
    logger.info(f"Đã tạo thành công {len(work_orders)} phiếu bảo trì vào fact_work_orders.")

    conn.commit()


def print_database_audit_report(conn):
    """
    Truy vấn kiểm tra tính toàn vẹn của Data Warehouse và in báo cáo thẩm định.
    """
    cursor = conn.cursor()
    print("\n" + "=" * 80)
    print("      BÁO CÁO THẨM ĐỊNH DATA WAREHOUSE - PACKAGING_FACTORY.DB")
    print("=" * 80)

    tables = [
        "dim_machines",
        "dim_error_catalog",
        "fact_sensor_telemetry",
        "fact_downtime_events",
        "fact_work_orders"
    ]

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table};")
        cnt = cursor.fetchone()[0]
        print(f"Bảng: {table:<25} | Số dòng: {cnt:>8,}")

    print("-" * 80)
    print("TOP 5 SỰ CỐ GÂY THẤT THOÁT SẢN LƯỢNG CAO NHẤT (PARETO LOST UNITS):")
    query_lost = """
    SELECT 
        e.error_code,
        c.failure_type,
        COUNT(e.event_id) AS event_count,
        ROUND(SUM(e.downtime_duration_minutes), 1) AS total_downtime_min,
        SUM(e.impact_units_lost) AS total_units_lost
    FROM fact_downtime_events e
    JOIN dim_error_catalog c ON e.error_code = c.error_code
    GROUP BY e.error_code, c.failure_type
    ORDER BY total_units_lost DESC;
    """
    lost_df = pd.read_sql_query(query_lost, conn)
    print(lost_df.to_string(index=False))

    print("-" * 80)
    print("THỐNG KÊ PHIẾU BẢO TRÌ (WORK ORDERS) THEO TRẠNG THÁI LOTO AN TOÀN:")
    query_wo = """
    SELECT 
        order_status,
        loto_status,
        COUNT(*) AS total_tickets
    FROM fact_work_orders
    GROUP BY order_status, loto_status;
    """
    wo_df = pd.read_sql_query(query_wo, conn)
    print(wo_df.to_string(index=False))
    print("=" * 80 + "\n")


def main():
    logger.info("=== BẮT ĐẦU PHA 2: KHỞI TẠO RELATIONAL DATA WAREHOUSE ===")
    conn = create_connection()
    try:
        cursor = conn.cursor()
        create_schema(cursor)
        seed_dimension_tables(cursor)
        load_telemetry_and_derive_facts(conn)
        print_database_audit_report(conn)
        logger.info(f"Database đã được tạo thành công tại: {DB_PATH.resolve()}")
    except Exception as e:
        logger.error(f"Lỗi khởi tạo database: {e}", exc_info=True)
        conn.rollback()
    finally:
        conn.close()
    logger.info("=== HOÀN TẤT PHA 2 XUẤT SẮC ===")


if __name__ == "__main__":
    main()