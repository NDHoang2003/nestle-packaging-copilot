
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "packaging_factory.db"

if not DB_PATH.exists():
    raise FileNotFoundError(f"Không tìm thấy database: {DB_PATH}")

with sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True) as conn:
    conn.row_factory = sqlite3.Row

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"Database integrity: {integrity}")

    print("\n=== E-401 severity distribution ===")
    rows = conn.execute("""
        SELECT error_code, is_failure, alert_severity, COUNT(*) AS total
        FROM fact_sensor_telemetry
        WHERE error_code = 'E-401'
        GROUP BY error_code, is_failure, alert_severity
        ORDER BY is_failure, alert_severity
    """).fetchall()

    if not rows:
        print("Không có bản ghi E-401 trong database.")
    else:
        for row in rows:
            print(
                f"error={row['error_code']}, "
                f"is_failure={row['is_failure']}, "
                f"severity={row['alert_severity']}, "
                f"count={row['total']}"
            )

    print("\n=== E-401 incorrectly marked NORMAL ===")
    bad_rows = conn.execute("""
        SELECT record_id, timestamp, line_id, is_failure, alert_severity
        FROM fact_sensor_telemetry
        WHERE error_code = 'E-401'
          AND alert_severity = 'NORMAL'
        ORDER BY record_id DESC
        LIMIT 20
    """).fetchall()

    if bad_rows:
        print(f"FAIL: Tìm thấy {len(bad_rows)} bản ghi sai (tối đa 20 dòng hiển thị).")
        for row in bad_rows:
            print(dict(row))
    else:
        print("PASS: Không có bản ghi E-401 mang severity NORMAL.")

    print("\n=== Latest E-401 records ===")
    latest = conn.execute("""
        SELECT record_id, timestamp, line_id, is_failure, alert_severity
        FROM fact_sensor_telemetry
        WHERE error_code = 'E-401'
        ORDER BY record_id DESC
        LIMIT 10
    """).fetchall()

    if not latest:
        print("Không có bản ghi E-401 để kiểm tra.")
    else:
        for row in latest:
            print(dict(row))
