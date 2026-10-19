
#!/usr/bin/env python3
"""
Nestle Dong Nai Factory - Industrial Packaging Digital Twin
Database: packaging_factory.db
"""

import logging
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (Nestle-DB) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("DatabaseSetup")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "packaging_factory.db"
DATA_DIR = BASE_DIR / "data"
PARQUET_PATH = DATA_DIR / "cleaned_telemetry.parquet"
CSV_PATH = DATA_DIR / "cleaned_telemetry.csv"


def create_connection():
    """Create a SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(cursor):
    """Recreate the demo schema from scratch."""
    logger.info("Creating database schema...")

    cursor.executescript("""
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
        rated_capacity_cph INTEGER NOT NULL,
        target_product TEXT NOT NULL,
        cleanroom_area TEXT NOT NULL,
        commissioning_date TEXT NOT NULL,
        status TEXT DEFAULT 'ACTIVE'
    );

    CREATE TABLE dim_error_catalog (
        error_code TEXT PRIMARY KEY,
        failure_type TEXT NOT NULL,
        description TEXT NOT NULL,
        root_cause_category TEXT NOT NULL,
        standard_recovery_time_min REAL NOT NULL,
        loto_procedure_required INTEGER NOT NULL,
        required_ppe TEXT NOT NULL,
        sop_reference TEXT NOT NULL
    );

    CREATE TABLE fact_sensor_telemetry (
        record_id INTEGER PRIMARY KEY,
        timestamp TEXT NOT NULL,
        shift_id TEXT NOT NULL,
        line_id TEXT NOT NULL,
        temp_cleanroom_c REAL NOT NULL,
        temp_sonotrode_c REAL NOT NULL,
        speed_servo_rpm REAL NOT NULL,
        tension_torque_nm REAL NOT NULL,

        -- Historical AI4I data: wear measured in minutes.
        cutting_knife_wear_min INTEGER,

        -- Runtime simulator data: wear measured in metres.
        cutting_knife_wear_m REAL,

        delta_t REAL NOT NULL,
        dt_dt REAL NOT NULL,
        p_mech_kw REAL NOT NULL,
        heat_strain_index REAL NOT NULL,
        error_code TEXT NOT NULL,
        is_failure INTEGER NOT NULL,
        alert_severity TEXT NOT NULL,

        -- Each record uses one wear unit, never both.
        CHECK (
            (
                cutting_knife_wear_min IS NOT NULL
                AND cutting_knife_wear_m IS NULL
            )
            OR
            (
                cutting_knife_wear_min IS NULL
                AND cutting_knife_wear_m IS NOT NULL
            )
        ),

        FOREIGN KEY (line_id)
            REFERENCES dim_machines(line_id),

        FOREIGN KEY (error_code)
            REFERENCES dim_error_catalog(error_code)
    );

    CREATE INDEX idx_telemetry_timestamp
        ON fact_sensor_telemetry(timestamp);

    CREATE INDEX idx_telemetry_line_time
        ON fact_sensor_telemetry(line_id, timestamp);

    CREATE INDEX idx_telemetry_failure
        ON fact_sensor_telemetry(is_failure, error_code);

    CREATE INDEX idx_telemetry_shift
        ON fact_sensor_telemetry(shift_id);

    CREATE TABLE fact_downtime_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_id INTEGER NOT NULL,
        line_id TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        shift_id TEXT NOT NULL,
        error_code TEXT NOT NULL,
        downtime_duration_minutes REAL NOT NULL,
        impact_units_lost INTEGER NOT NULL,

        FOREIGN KEY (record_id)
            REFERENCES fact_sensor_telemetry(record_id),

        FOREIGN KEY (line_id)
            REFERENCES dim_machines(line_id),

        FOREIGN KEY (error_code)
            REFERENCES dim_error_catalog(error_code)
    );

    CREATE INDEX idx_downtime_line
        ON fact_downtime_events(line_id);

    CREATE INDEX idx_downtime_error
        ON fact_downtime_events(error_code);

    CREATE INDEX idx_downtime_shift
        ON fact_downtime_events(shift_id);

    CREATE TABLE fact_work_orders (
        work_order_id TEXT PRIMARY KEY,
        event_id INTEGER NOT NULL,
        line_id TEXT NOT NULL,
        error_code TEXT NOT NULL,
        created_at TEXT NOT NULL,
        priority TEXT NOT NULL,
        loto_status TEXT NOT NULL DEFAULT 'PENDING_ISOLATION',
        technician_assigned TEXT NOT NULL,
        resolution_notes TEXT,
        order_status TEXT NOT NULL DEFAULT 'OPEN',
        closed_at TEXT,

        FOREIGN KEY (event_id)
            REFERENCES fact_downtime_events(event_id),

        FOREIGN KEY (line_id)
            REFERENCES dim_machines(line_id),

        FOREIGN KEY (error_code)
            REFERENCES dim_error_catalog(error_code)
    );

    CREATE INDEX idx_wo_status
        ON fact_work_orders(order_status);

    CREATE INDEX idx_wo_line
        ON fact_work_orders(line_id);
    """)

    logger.info("Schema created successfully.")


def seed_dimension_tables(cursor):
    """Load machine and error catalog demo data."""

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
            "ACTIVE",
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
            "ACTIVE",
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
            "ACTIVE",
        ),
    ]

    cursor.executemany("""
        INSERT INTO dim_machines (
            line_id,
            machine_name,
            manufacturer,
            model,
            rated_capacity_cph,
            target_product,
            cleanroom_area,
            commissioning_date,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, machines_data)

    catalog_data = [
        (
            "NORMAL",
            "No Failure",
            "Dây chuyền đang hoạt động trong ngưỡng chuẩn kỹ thuật",
            "Operations",
            0.0,
            0,
            "Standard Cleanroom PPE",
            "SOP-OPS-001",
        ),
        (
            "E-105",
            "Tool Wear Failure",
            "Mòn dao cắt bao bì định hình mép hộp",
            "Mechanical Cutting",
            25.0,
            1,
            "Safety Glasses, Cut-Resistant Gloves Level 5",
            "SOP-MEC-105",
        ),
        (
            "E-401",
            "Heat Dissipation Failure",
            "Quá nhiệt đầu hàn siêu âm Sonotrode",
            "Thermal & Ultrasonic",
            45.0,
            1,
            "Thermal Insulated Gloves, Face Shield, LOTO Padlock",
            "SOP-THM-401",
        ),
        (
            "E-204",
            "Power Failure",
            "Quá tải công suất động cơ Servo",
            "Electrical & Drive",
            30.0,
            1,
            "Arc Flash Shield, Electrical Safety Gloves Class 0",
            "SOP-ELE-204",
        ),
        (
            "E-302",
            "Overstrain Failure",
            "Quá lực căng màng cuộn giấy",
            "Packaging Material Strain",
            35.0,
            1,
            "Cut-Resistant Gloves, Standard PPE, LOTO Padlock",
            "SOP-MAT-302",
        ),
        (
            "E-999",
            "Random Sensor / Line Jam",
            "Lệch cảm biến hoặc kẹt bao bì",
            "Automation & Optical",
            15.0,
            0,
            "Standard Cleanroom PPE, Anti-static Wristband",
            "SOP-AUT-999",
        ),
    ]

    cursor.executemany("""
        INSERT INTO dim_error_catalog (
            error_code,
            failure_type,
            description,
            root_cause_category,
            standard_recovery_time_min,
            loto_procedure_required,
            required_ppe,
            sop_reference
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, catalog_data)

    logger.info("Dimension tables seeded.")


def load_telemetry_and_derive_facts(conn):
    """Load historical telemetry and generate demo maintenance events."""

    if PARQUET_PATH.exists():
        df = pd.read_parquet(PARQUET_PATH)
        logger.info("Loaded telemetry from %s", PARQUET_PATH)
    elif CSV_PATH.exists():
        df = pd.read_csv(CSV_PATH)
        logger.info("Loaded telemetry from %s", CSV_PATH)
    else:
        raise FileNotFoundError(
            "Không tìm thấy cleaned_telemetry.parquet hoặc "
            "cleaned_telemetry.csv trong thư mục data/."
        )

    required_columns = [
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
        "alert_severity",
    ]

    missing = set(required_columns) - set(df.columns)
    if missing:
        raise ValueError(
            f"Dataset thiếu các cột bắt buộc: {sorted(missing)}"
        )

    cursor = conn.cursor()

    logger.info("Loading historical telemetry...")

    telemetry_records = df[required_columns].values.tolist()

    # Use explicit column names. Historical records use minutes;
    # cutting_knife_wear_m remains NULL for those records.
    cursor.executemany("""
        INSERT INTO fact_sensor_telemetry (
            record_id,
            timestamp,
            shift_id,
            line_id,
            temp_cleanroom_c,
            temp_sonotrode_c,
            speed_servo_rpm,
            tension_torque_nm,
            cutting_knife_wear_min,
            delta_t,
            dt_dt,
            p_mech_kw,
            heat_strain_index,
            error_code,
            is_failure,
            alert_severity
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, telemetry_records)

    logger.info(
        "Loaded %s historical telemetry records.",
        len(telemetry_records),
    )

    # Generate downtime events from historical failures.
    failure_df = df[df["is_failure"] == 1].copy()

    cursor.execute(
        "SELECT line_id, rated_capacity_cph FROM dim_machines"
    )
    capacity_dict = {
        row[0]: row[1] for row in cursor.fetchall()
    }

    cursor.execute("""
        SELECT error_code, standard_recovery_time_min
        FROM dim_error_catalog
    """)
    recovery_dict = {
        row[0]: row[1] for row in cursor.fetchall()
    }

    np.random.seed(42)

    downtime_events = []
    work_orders = []

    technicians = [
        "KTV. Nguyen Van An",
        "KTV. Tran Dinh Binh",
        "KTV. Le Hoang Cuong",
        "KTV. Pham Minh Dung",
    ]

    for _, row in failure_df.iterrows():
        line = row["line_id"]
        error = row["error_code"]
        record_id = int(row["record_id"])
        timestamp = str(row["timestamp_str"])
        shift = row["shift_id"]

        standard_time = recovery_dict.get(error, 20.0)
        major_breakdown = np.random.rand() < 0.15

        if major_breakdown:
            downtime = round(
                standard_time * np.random.uniform(0.85, 1.25),
                1,
            )
        else:
            downtime = round(
                np.random.uniform(1.0, 3.5),
                1,
            )

        capacity = capacity_dict.get(line, 10000)
        units_lost = int((capacity / 60.0) * downtime)

        downtime_events.append((
            record_id,
            line,
            timestamp,
            shift,
            error,
            downtime,
            units_lost,
        ))

    cursor.executemany("""
        INSERT INTO fact_downtime_events (
            record_id,
            line_id,
            timestamp,
            shift_id,
            error_code,
            downtime_duration_minutes,
            impact_units_lost
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, downtime_events)

    logger.info(
        "Created %s downtime events.",
        len(downtime_events),
    )

    cursor.execute("""
        SELECT event_id, line_id, error_code, timestamp
        FROM fact_downtime_events
    """)
    db_events = cursor.fetchall()

    for event_id, line, error, timestamp in db_events:
        work_order_id = (
            f"WO-{timestamp[:10].replace('-', '')}-{event_id:04d}"
        )

        priority = (
            "P1_URGENT"
            if error in ["E-401", "E-204"]
            else "P2_HIGH"
        )

        technician = str(np.random.choice(technicians))

        if event_id > len(db_events) - 15:
            order_status = "IN_PROGRESS"
            loto_status = "VERIFIED_LOTO"
            notes = "Đang cô lập nguồn điện và tiến hành cân chỉnh kỹ thuật."
            closed_at = None
        else:
            order_status = "CLOSED"
            loto_status = "RESTORED"
            notes = (
                f"Đã khắc phục hoàn tất theo SOP chuẩn {error}. "
                "Bàn giao dây chuyền cho Trưởng ca."
            )
            closed_at = timestamp

        work_orders.append((
            work_order_id,
            event_id,
            line,
            error,
            timestamp,
            priority,
            loto_status,
            technician,
            notes,
            order_status,
            closed_at,
        ))

    cursor.executemany("""
        INSERT INTO fact_work_orders (
            work_order_id,
            event_id,
            line_id,
            error_code,
            created_at,
            priority,
            loto_status,
            technician_assigned,
            resolution_notes,
            order_status,
            closed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, work_orders)

    logger.info("Created %s work orders.", len(work_orders))

    conn.commit()


def print_database_audit_report(conn):
    """Print row counts and basic demo database statistics."""

    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("PACKAGING FACTORY DATABASE AUDIT")
    print("=" * 80)

    tables = [
        "dim_machines",
        "dim_error_catalog",
        "fact_sensor_telemetry",
        "fact_downtime_events",
        "fact_work_orders",
    ]

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"{table:<30} | {count:>8,} rows")

    cursor.execute("""
        SELECT
            COUNT(*) AS total_rows,
            SUM(
                CASE
                    WHEN cutting_knife_wear_min IS NOT NULL
                    THEN 1 ELSE 0
                END
            ) AS minute_rows,
            SUM(
                CASE
                    WHEN cutting_knife_wear_m IS NOT NULL
                    THEN 1 ELSE 0
                END
            ) AS metre_rows
        FROM fact_sensor_telemetry
    """)

    total, minute_rows, metre_rows = cursor.fetchone()

    print("-" * 80)
    print(f"Telemetry total:             {total}")
    print(f"Historical wear in minutes:  {minute_rows or 0}")
    print(f"Runtime wear in metres:      {metre_rows or 0}")

    lost_query = """
        SELECT
            e.error_code,
            c.failure_type,
            COUNT(e.event_id) AS event_count,
            ROUND(
                SUM(e.downtime_duration_minutes), 1
            ) AS total_downtime_min,
            SUM(e.impact_units_lost) AS total_units_lost
        FROM fact_downtime_events e
        JOIN dim_error_catalog c
            ON e.error_code = c.error_code
        GROUP BY e.error_code, c.failure_type
        ORDER BY total_units_lost DESC
    """

    lost_df = pd.read_sql_query(lost_query, conn)

    print("\nTOP DOWNTIME IMPACT:")
    print(lost_df.to_string(index=False))

    work_order_query = """
        SELECT order_status, loto_status, COUNT(*) AS total_tickets
        FROM fact_work_orders
        GROUP BY order_status, loto_status
    """

    work_order_df = pd.read_sql_query(
        work_order_query,
        conn,
    )

    print("\nWORK ORDERS:")
    print(work_order_df.to_string(index=False))
    print("=" * 80)


def main():
    logger.info("Starting demo database setup.")

    conn = create_connection()

    try:
        cursor = conn.cursor()

        create_schema(cursor)
        seed_dimension_tables(cursor)
        load_telemetry_and_derive_facts(conn)
        print_database_audit_report(conn)

        logger.info("Database created at %s", DB_PATH)

    except Exception:
        conn.rollback()
        logger.exception("Database setup failed.")
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    main()
