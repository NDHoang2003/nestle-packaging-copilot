"""Isolated persistence smoke/negative tests for simulate_line.py.

Run from the repository root:
    python /mnt/data/test_telemetry_persistence.py --db packaging_factory.db

The supplied database is copied into a temporary directory; this test never writes to --db.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

EXPECTED_FRAME_KEYS = {
    "timestamp", "line_id", "actual_speed_cph", "rot_speed_rpm",
    "tension_torque_nm", "cutting_knife_wear_min", "p_mech_kw",
    "ambient_temp_c", "ultrasonic_temp_c", "delta_t", "status",
    "is_failure", "fault_mode",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS: {label}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="packaging_factory.db", help="Existing database, used read-only as a copy source")
    args = parser.parse_args()
    db_source = Path(args.db).resolve()
    if not db_source.is_file():
        raise FileNotFoundError(f"Database not found: {db_source}")

    root = Path.cwd().resolve()
    sys.path.insert(0, str(root))
    simulator_module = importlib.import_module("simulate_line")
    before_hash = sha256(db_source)

    with tempfile.TemporaryDirectory(prefix="telemetry-persistence-test-") as td:
        temp = Path(td)
        positive_db = temp / "positive.db"
        negative_db = temp / "negative.db"
        shutil.copy2(db_source, positive_db)
        shutil.copy2(db_source, negative_db)

        with sqlite3.connect(positive_db) as conn:
            before_count = conn.execute("SELECT COUNT(*) FROM fact_sensor_telemetry").fetchone()[0]
        sim = simulator_module.StochasticPackagingLineSimulator("LINE_01", str(positive_db))
        frame = sim.step()
        check(set(frame) == EXPECTED_FRAME_KEYS, "all existing simulator frame keys are preserved")

        with sqlite3.connect(positive_db) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            after_count = conn.execute("SELECT COUNT(*) FROM fact_sensor_telemetry").fetchone()[0]
            check(after_count == before_count + 1, "one simulator step persists exactly one telemetry row")
            row = conn.execute(
                """SELECT record_id, timestamp, shift_id, line_id, temp_cleanroom_c,
                          temp_sonotrode_c, speed_servo_rpm, tension_torque_nm,
                          cutting_knife_wear_min, delta_t, dt_dt, p_mech_kw,
                          heat_strain_index, error_code, is_failure, alert_severity
                   FROM fact_sensor_telemetry
                   WHERE timestamp = ? AND line_id = ? ORDER BY record_id DESC LIMIT 1""",
                (frame["timestamp"], frame["line_id"]),
            ).fetchone()
            check(row is not None, "persisted row matches the frame timestamp and line")
            check(all(value is not None for value in row), "all required telemetry fields are populated")
            check(isinstance(row[0], int) and isinstance(row[14], int),
                  "SQLite generated record_id and is_failure has INTEGER storage values")
            check(abs(float(row[8]) - float(frame["cutting_knife_wear_min"])) < 1e-9,
                  "persisted knife-wear value matches simulator output without unit conversion or precision loss")
            check(isinstance(row[10], (int, float)), "dt_dt is populated as a numeric derivative in the database")
            check(conn.execute("SELECT 1 FROM dim_machines WHERE line_id = ?", (row[3],)).fetchone() is not None,
                  "line_id foreign-key target exists")
            check(conn.execute("SELECT 1 FROM dim_error_catalog WHERE error_code = ?", (row[13],)).fetchone() is not None,
                  "error_code foreign-key target exists")
            check(conn.execute("PRAGMA foreign_key_check").fetchall() == [], "foreign_key_check returns no violations")
            check(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "PRAGMA integrity_check returns ok")

        with sqlite3.connect(negative_db) as conn:
            negative_before = conn.execute("SELECT COUNT(*) FROM fact_sensor_telemetry").fetchone()[0]
            conn.execute(
                """CREATE TRIGGER force_telemetry_failure
                   BEFORE INSERT ON fact_sensor_telemetry
                   BEGIN SELECT RAISE(ABORT, 'controlled persistence failure'); END"""
            )
        negative_sim = simulator_module.StochasticPackagingLineSimulator("LINE_01", str(negative_db))
        caught = False
        try:
            negative_sim.step()
        except sqlite3.Error as exc:
            caught = True
            print(f"Observed expected database error: {type(exc).__name__}: {exc}")
        check(caught, "negative write raises an observable SQLite exception")
        with sqlite3.connect(negative_db) as conn:
            check(conn.execute("SELECT COUNT(*) FROM fact_sensor_telemetry").fetchone()[0] == negative_before,
                  "failed transaction leaves no partial telemetry row")
            check(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                  "negative-test database integrity remains ok")

    check(sha256(db_source) == before_hash, "source database SHA-256 unchanged")
    print("All telemetry-persistence checks passed.")


if __name__ == "__main__":
    main()
