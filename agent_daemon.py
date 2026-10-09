#!/usr/bin/env python3
"""
================================================================================
NESTLE DONG NAI FACTORY - INDUSTRIAL PACKAGING DIGITAL TWIN
Module: Autonomous Watchdog Agent Daemon (Sense - Think - Act Loop)
Role: Continuously monitors streaming telemetry, autonomously diagnoses RCA
      via Gemini, and automatically triggers maintenance Work Orders in DB.
Author: Nguyen Doan Hoang (Digital Technical Specialist Candidate)
Reviewed by: Lead Industrial Data & AI Engineer
================================================================================
"""

import os
import sys
import time
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import factory_tools
from agent_core import PackagingCopilotAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (Watchdog-Daemon) %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("WatchdogDaemon")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "packaging_factory.db"


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


class AutonomousIndustrialWatchdog:
    """Agent tự trị giám sát nhà máy 24/7."""

    def __init__(self, poll_interval_sec: float = 1.0):
        self.poll_interval = poll_interval_sec
        self.agent_brain = PackagingCopilotAgent()
        self.last_handled_records = {}

    def run_forever(self):
        print("\n" + "=" * 80)
        print("  KHỞI ĐỘNG AUTONOMOUS WATCHDOG AGENT DAEMON (SENSE - THINK - ACT)")
        print("  Chế độ: Canh gác tự động 24/7 | Không cần con người can thiệp")
        print("=" * 80 + "\n")

        while True:
            try:
                self.sense_think_act_cycle()
                time.sleep(self.poll_interval)
            except KeyboardInterrupt:
                logger.info("Nhận lệnh tắt Daemon từ người dùng (Ctrl+C). Dừng canh gác.")
                break
            except Exception as e:
                logger.error(f"Lỗi trong chu kỳ giám sát: {e}")
                time.sleep(2.0)

    def sense_think_act_cycle(self):
        """1 Chu kỳ: Cảm nhận (Sense) -> Suy luận AI (Think) -> Hành động (Act)."""
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. BƯỚC SENSE: Đọc dữ liệu từ bảng đệm và ÉP THẲNG THÀNH DICT NGUYÊN BẢN
        cursor.execute("""
        SELECT line_id, record_id, last_updated, machine_name, temp_cleanroom_c,
               temp_sonotrode_c, delta_t, speed_servo_rpm, tension_torque_nm,
               p_mech_kw, cutting_knife_wear_min, error_code, is_failure, alert_severity
        FROM realtime_edge_buffer;
        """)
        # Ép kiểu triệt để mọi dòng thành Python Dict thông thường
        active_lines = [dict(r) for r in cursor.fetchall()]
        conn.close()

        if not active_lines:
            return

        for state in active_lines:
            line = state["line_id"]
            severity = state["alert_severity"]
            err_code = state["error_code"]
            ts = state["last_updated"]

            # Kích hoạt khi có bất thường (WARNING hoặc CRITICAL)
            if severity in ["WARNING", "CRITICAL"] or state["is_failure"] == 1:
                signature = f"{line}_{ts}_{err_code}"
                if signature in self.last_handled_records:
                    continue
                self.last_handled_records[signature] = True

                # THỰC THI CHU TRÌNH TỰ TRỊ
                self.execute_autonomous_intervention(state)

    def execute_autonomous_intervention(self, sensor_state: dict):
        """Thực thi hành động can thiệp tự động."""
        line = sensor_state["line_id"]
        err = sensor_state["error_code"]
        p_kw = sensor_state["p_mech_kw"]
        t_sono = sensor_state["temp_sonotrode_c"]
        delta_t = sensor_state["delta_t"]
        knife = sensor_state["cutting_knife_wear_min"]

        print("\n" + "🚨" * 40)
        logger.warning(
            f"[SENSE TRIGGERED] Phát hiện bất thường cấp {sensor_state['alert_severity']} trên {line}!\n"
            f"   >> Mã lỗi: {err} | T_sono: {t_sono}°C | ΔT: {delta_t}°C | P: {p_kw}kW | Dao mòn: {knife}m"
        )

        # 2. BƯỚC THINK: Đánh thức Gemini tự chẩn đoán RCA
        prompt_autonomous = (
            f"CẢNH BÁO TỰ ĐỘNG TỪ HỆ THỐNG GIÁM SÁT THỜI GIAN THỰC:\n"
            f"Dây chuyền {line} vừa phát sinh sự cố bất thường!\n"
            f"- Mã lỗi cảm biến: {err}\n"
            f"- Nhiệt độ Sonotrode: {t_sono}°C (Delta_T: {delta_t}°C)\n"
            f"- Công suất cơ học P_mech: {p_kw} kW\n"
            f"- Độ mài mòn dao cắt: {knife} phút\n\n"
            f"Hãy thực hiện chẩn đoán nguyên nhân gốc rễ (RCA) ngắn gọn và đưa ra hướng dẫn kỹ thuật ngay lập tức."
        )

        logger.info("🧠 [THINKING] Đang kích hoạt Bộ não Gemini tự động phân tích RCA...")
        rca_diagnosis = self.agent_brain.chat(prompt_autonomous)

        print("\n" + "-" * 80)
        print("📋 [KẾT QUẢ CHẨN ĐOÁN TỰ ĐỘNG CỦA COPILOT]:")
        print(rca_diagnosis)
        print("-" * 80)

        # 3. BƯỚC ACT: TỰ ĐỘNG GHI NHẬN SỰ CỐ & TẠO PHIẾU BẢO TRÌ VÀO DATABASE
        self.act_create_work_order(sensor_state, rca_diagnosis)
        print("🚨" * 40 + "\n")

    def act_create_work_order(self, sensor_state: dict, rca_text: str):
        """Hành động thực tế: Ghi phiếu bảo trì khẩn cấp vào SQLite."""
        conn = get_db_connection()
        cursor = conn.cursor()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        wo_id = f"WO-AUTO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        line = sensor_state["line_id"]
        err = sensor_state["error_code"]
        rec_id = int(sensor_state.get("record_id", 1))

        try:
            # 1. Ghi nhận sự cố vào fact_downtime_events
            cursor.execute("""
            INSERT INTO fact_downtime_events (record_id, line_id, timestamp, shift_id, error_code, downtime_duration_minutes, impact_units_lost)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (rec_id, line, now_str, "Shift 1", err, 15.0, 6000))
            event_id = cursor.lastrowid

            # 2. Tự động tạo Work Order cấp P1_URGENT với trạng thái LOTO PENDING_ISOLATION
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
                f"[AUTO-GENERATED BY COPILOT RCA]: {rca_text[:300]}...",
                "OPEN"
            ))

            conn.commit()
            logger.info(
                f"⚡ [ACTION EXECUTED] Đã tự động tạo Phiếu Bảo Trì: {wo_id}\n"
                f"   >> Sự kiện Event ID: {event_id} | Record ID: {rec_id}\n"
                f"   >> Độ ưu tiên: P1_URGENT | Trạng thái LOTO: PENDING_ISOLATION\n"
                f"   >> Phân công: {tech_assigned}\n"
                f"   >> Ghi nhận vào Database packaging_factory.db THÀNH CÔNG 100%!"
            )
        except Exception as e:
            conn.rollback()
            logger.error(f"Lỗi thực thi Action Work Order: {e}")
        finally:
            conn.close()


if __name__ == "__main__":
    daemon = AutonomousIndustrialWatchdog(poll_interval_sec=0.5)
    daemon.run_forever()