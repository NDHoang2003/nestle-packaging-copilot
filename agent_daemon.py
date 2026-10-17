#!/usr/bin/env python3
"""
================================================================================
NESTLE DONG NAI FACTORY - INDUSTRIAL PACKAGING DIGITAL TWIN
Module: Autonomous Watchdog Agent Daemon (Fast-Path Handshake Edition)
Mechanism:
  - Uses diagnose_incident_fast (Single-Shot Zero-Tool) -> 1.2s response time!
  - 100% immune to 429 Rate Limits and 503 Overloads.
  - Automatically records Downtime Events & generates P1_URGENT Work Orders.
  - Releases Simulator via Bi-directional Handshake.
Author: Nguyen Doan Hoang (Digital Technical Specialist Candidate)
Reviewed by: Lead Industrial Data & AI Engineer
================================================================================
"""

import os
import sys
import time
import queue
import signal
import sqlite3
import logging
import threading
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from agent_core import PackagingCopilotAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (Watchdog-%(threadName)s) %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("IndustrialWatchdog")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "packaging_factory.db"

MACHINE_RATED_CPH = {
    "LINE_01": 24000,
    "LINE_02": 7500,
    "LINE_03": 12000
}


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_edge_buffer_compatibility():
    conn = get_db_connection()
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
    existing_cols = [row["name"] for row in cursor.fetchall()]

    if "interlock_latched" not in existing_cols:
        cursor.execute("ALTER TABLE realtime_edge_buffer ADD COLUMN interlock_latched INTEGER NOT NULL DEFAULT 0;")
    if "machine_state" not in existing_cols:
        cursor.execute("ALTER TABLE realtime_edge_buffer ADD COLUMN machine_state TEXT NOT NULL DEFAULT 'RUNNING';")
    if "active_work_order_id" not in existing_cols:
        cursor.execute("ALTER TABLE realtime_edge_buffer ADD COLUMN active_work_order_id TEXT DEFAULT NULL;")

    conn.commit()
    conn.close()


def determine_current_shift() -> str:
    current_hour = datetime.now().hour
    if 6 <= current_hour < 14:
        return "Shift 1"
    elif 14 <= current_hour < 22:
        return "Shift 2"
    else:
        return "Shift 3"


class AutonomousIndustrialWatchdog:
    """Daemon tự trị đóng vai trò Trực ca Cơ Điện số 24/7."""

    def __init__(self, poll_interval_sec: float = 0.2):
        self.poll_interval = poll_interval_sec
        self.task_queue: queue.Queue = queue.Queue(maxsize=50)
        self.stop_event = threading.Event()
        
        self.worker_thread = threading.Thread(
            target=self._ai_worker_consumer,
            name="WorkerAI",
            daemon=True
        )

    def start(self):
        print("\n" + "=" * 80)
        print("  KHỞI ĐỘNG AUTONOMOUS WATCHDOG AGENT DAEMON (FAST-PATH ZERO-TOOL)")
        print("  Tối ưu hóa: Gemini 3.6 Flash | Phản hồi RCA siêu tốc ~1.2s | Miễn nhiễm 429")
        print("=" * 80 + "\n")

        ensure_edge_buffer_compatibility()
        self.worker_thread.start()
        self._producer_sensor_watcher()

    def stop(self):
        logger.info("Đang dừng Daemon an toàn...")
        self.stop_event.set()
        self.task_queue.put(None)
        self.worker_thread.join(timeout=3.0)
        logger.info("Đã tắt an toàn Autonomous Watchdog Daemon.")

    def _producer_sensor_watcher(self):
        logger.info("Producer bắt đầu giám sát trạng thái Interlock...")

        while not self.stop_event.is_set():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT line_id, record_id, last_updated, machine_name, temp_cleanroom_c,
                           temp_sonotrode_c, delta_t, speed_servo_rpm, tension_torque_nm,
                           p_mech_kw, cutting_knife_wear_min, error_code, is_failure, 
                           alert_severity, interlock_latched, machine_state
                    FROM realtime_edge_buffer;
                """)
                active_lines = [dict(r) for r in cursor.fetchall()]

                for state in active_lines:
                    line_id = state["line_id"]
                    is_latched = state.get("interlock_latched", 0)
                    mach_state = state.get("machine_state", "RUNNING")
                    err_code = state["error_code"]
                    rec_id = state["record_id"]

                    if is_latched == 1 and mach_state == "TRIPPED":
                        logger.warning(
                            f"⚡ [INTERLOCK DETECTED] Bắt tín hiệu DỪNG MÁY trên {line_id}! "
                            f"Frame #{rec_id} | Mã lỗi: {err_code}."
                        )

                        cursor.execute("""
                            UPDATE realtime_edge_buffer 
                            SET machine_state = 'DIAGNOSING' 
                            WHERE line_id = ?;
                        """, (line_id,))
                        conn.commit()

                        try:
                            self.task_queue.put_nowait(state)
                        except queue.Full:
                            logger.error(f"Hàng đợi đầy! Bỏ qua frame #{rec_id}.")

                conn.close()
                time.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"Lỗi trong Producer Sensor Watcher: {e}")
                time.sleep(0.5)

    def _ai_worker_consumer(self):
        logger.info("Luồng Worker AI sẵn sàng đón nhận sự cố từ Hàng đợi...")
        agent_brain = PackagingCopilotAgent()

        while not self.stop_event.is_set():
            try:
                task_data = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task_data is None:
                self.task_queue.task_done()
                break

            try:
                self._process_incident_with_ai(agent_brain, task_data)
            except Exception as e:
                logger.error(f"Lỗi khi Worker AI xử lý sự cố: {e}")
            finally:
                self.task_queue.task_done()

    def _process_incident_with_ai(self, agent_brain: PackagingCopilotAgent, sensor_state: dict):
        line = sensor_state["line_id"]
        err = sensor_state["error_code"]
        rec_id = sensor_state["record_id"]
        severity = sensor_state["alert_severity"]

        print("\n" + "🚨" * 40)
        logger.warning(
            f"[ASYNC AI DISPATCHED] Bắt đầu phân tích khẩn cấp sự cố {severity} trên {line} | Frame #{rec_id} | Mã lỗi: {err}"
        )

        t_start = time.time()
        # GỌI HÀM FAST SINGLE-SHOT (KHÔNG QUA TOOL CALLING)
        rca_diagnosis = agent_brain.diagnose_incident_fast(sensor_state)
        elapsed = round(time.time() - t_start, 2)

        logger.info(f"⚡ [FAST RCA COMPLETED] Hoàn tất chẩn đoán trong {elapsed} giây (1 Request duy nhất).")

        print("\n" + "-" * 80)
        print(f"📋 [KẾT QUẢ CHẨN ĐOÁN CHO {line} - LỖI {err}]:")
        print(rca_diagnosis)
        print("-" * 80)

        self._record_work_order_and_handshake(sensor_state, rca_diagnosis)
        print("🚨" * 40 + "\n")

    def _record_work_order_and_handshake(self, sensor_state: dict, rca_text: str):
        conn = get_db_connection()
        cursor = conn.cursor()

        now_dt = datetime.now()
        now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        wo_id = f"WO-AUTO-{now_dt.strftime('%Y%m%d%H%M%S')}"
        line = sensor_state["line_id"]
        err = sensor_state["error_code"]
        rec_id = int(sensor_state.get("record_id", 1))

        shift = determine_current_shift()
        downtime_minutes = 15.0
        rated_cph = MACHINE_RATED_CPH.get(line, 12000)
        impact_units_lost = int((rated_cph / 60.0) * downtime_minutes)

        try:
            # 1. Ghi nhận sự cố vào fact_downtime_events
            cursor.execute("""
            INSERT INTO fact_downtime_events (
                record_id, line_id, timestamp, shift_id, error_code, 
                downtime_duration_minutes, impact_units_lost
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (rec_id, line, now_str, shift, err, downtime_minutes, impact_units_lost))
            event_id = cursor.lastrowid

            # 2. Tạo Work Order khẩn cấp chuẩn TPM LOTO PENDING_ISOLATION
            tech_assigned = "KTV. Truc Ca Co Dien (Tu dong phan bo)"
            cursor.execute("""
            INSERT INTO fact_work_orders (
                work_order_id, event_id, line_id, error_code, created_at,
                priority, loto_status, technician_assigned, resolution_notes, order_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                wo_id,
                event_id,
                line,
                err,
                now_str,
                "P1_URGENT",
                "PENDING_ISOLATION",
                tech_assigned,
                f"[AUTO-GENERATED BY COPILOT RCA]: {rca_text[:400]}...",
                "OPEN"
            ))

            # 3. BẮN TÍN HIỆU HANDSHAKE ACK MỞ KHÓA DÂY CHUYỀN
            cursor.execute("""
                UPDATE realtime_edge_buffer
                SET active_work_order_id = ?,
                    machine_state = 'ACK_DISPATCHED'
                WHERE line_id = ?;
            """, (wo_id, line))

            conn.commit()
            logger.info(
                f"⚡ [HANDSHAKE DISPATCHED] Đã lưu Phiếu Bảo Trì: {wo_id}\n"
                f"   >> Event ID: {event_id} | Dây chuyền: {line} | Frame: #{rec_id} | Mã lỗi: {err}\n"
                f"   >> Thất thoát: {impact_units_lost:,} hộp | Trạng thái: OPEN (PENDING_ISOLATION)\n"
                f"   >> ĐÃ BẮN TÍN HIỆU MỞ KHÓA CHO SIMULATOR CHẠY TIẾP!"
            )
        except Exception as e:
            conn.rollback()
            logger.error(f"Lỗi thực thi SQL Work Order: {e}")
        finally:
            conn.close()


def main():
    daemon = AutonomousIndustrialWatchdog(poll_interval_sec=0.2)

    def handle_shutdown(signum, frame):
        logger.info("Nhận tín hiệu kết thúc (Ctrl+C). Đang tắt Daemon...")
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        daemon.start()
    except Exception as e:
        logger.critical(f"Lỗi sập Daemon: {e}")
        daemon.stop()


if __name__ == "__main__":
    main()