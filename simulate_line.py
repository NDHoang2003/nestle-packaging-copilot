"""
simulate_line.py
----------------
Stochastic Industrial Packaging Line Simulator (Real Shop-floor Physics).
Simulates continuous, probabilistic machinery degradation without hardcoded scripts.
Fully integrated with SQLite telemetry historian, PLC registers, and LOTO resets.
"""

import os
import random
import sqlite3
from datetime import datetime
from typing import Dict, Any

from industrial_bridge import plc_bridge, PLCHoldingRegisters

DB_PATH = "packaging_factory.db"


class StochasticPackagingLineSimulator:
    """
    Cỗ máy Digital Twin mô phỏng vật lý ngẫu nhiên thời gian thực.
    Không dùng kịch bản cố định - Các hiện tượng cơ nhiệt tích lũy tự nhiên.
    """

    def __init__(self, machine_id: str = "LINE_01", db_path: str = DB_PATH):
        self.machine_id = machine_id
        self.db_path = db_path
        
        # Điểm xuất phát vật lý ngẫu nhiên ban đầu
        self.knife_wear_m: float = random.uniform(60.0, 85.0) # Bắt đầu ở dải vận hành giữa ca
        self.ultrasonic_temp_c: float = random.uniform(34.0, 36.5)
        self.ambient_temp_c: float = 25.5
        self.rot_speed_rpm: float = 1500.0
        self.torque_nm: float = 40.0
        self.p_mech_kw: float = 6.28
        self.is_tripped: bool = False

    def replace_knife_and_service(self):
        """Kỹ thuật viên hoàn tất bảo trì, thay dao mới và vệ sinh máy."""
        self.knife_wear_m = 0.0
        self.ultrasonic_temp_c = 33.0
        self.torque_nm = 39.5
        self.p_mech_kw = 5.8
        self.is_tripped = False
        plc_bridge.write_holding_register(self.machine_id, PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED, 24000)
        plc_bridge.write_holding_register(self.machine_id, PLCHoldingRegisters.REG_SAFETY_INTERLOCK, 0)

    def step(self) -> Dict[str, Any]:
        """
        Thực thi 1 giây vận hành thực tế (1 tick = 1 frame SCADA):
        """
        plc_speed = plc_bridge.read_holding_register(self.machine_id, PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED) or 24000
        is_interlocked = (plc_bridge.read_holding_register(self.machine_id, PLCHoldingRegisters.REG_SAFETY_INTERLOCK) == 1)

        # 1. Trạng thái dừng khẩn cấp (Interlock Trip / LOTO)
        if is_interlocked or self.is_tripped:
            actual_speed = 0
            self.torque_nm = 0.0
            self.p_mech_kw = 0.0
            # Khi máy dừng, nhiệt độ đầu hàn nguội dần về nhiệt độ phòng
            if self.ultrasonic_temp_c > self.ambient_temp_c + 2.0:
                self.ultrasonic_temp_c -= 0.5
            status_text = "INTERLOCK_TRIP"
            is_fail = 1 if self.is_tripped else 0

        # 2. Trạng thái chạy cầm chừng Limp-Home (AMBER do Agent hạ tốc độ)
        elif plc_speed <= 18000:
            actual_speed = 18000
            # Giảm 25% tốc độ -> Ứng suất giảm mạnh, mòn dao chậm lại rất nhiều
            wear_rate = random.uniform(0.1, 0.25)
            self.knife_wear_m += wear_rate
            self.torque_nm = 35.0 + random.normalvariate(0, 1.0)
            self.p_mech_kw = (2 * 3.14159 * 1350.0 * self.torque_nm) / 60000.0
            self.ultrasonic_temp_c += random.choice([-0.1, 0.0, 0.1])
            status_text = "LIMP_HOME_ACTIVE"
            is_fail = 0

        # 3. Trạng thái chạy định mức 24.000 cph (NOMINAL)
        else:
            actual_speed = 24000
            # Dao càng mòn thì tốc độ mòn càng gia tốc
            if self.knife_wear_m >= 100.0:
                # Vùng suy thoái: ma sát tăng, chấn động ngẫu nhiên xuất hiện
                wear_rate = random.uniform(1.2, 2.8)
                self.torque_nm = 46.0 + random.normalvariate(0, 4.5) # Rung lắc phương sai cao
                self.ultrasonic_temp_c += random.uniform(0.05, 0.2)
            else:
                wear_rate = random.uniform(0.4, 0.8)
                self.torque_nm = 40.5 + random.normalvariate(0, 1.2)
                self.ultrasonic_temp_c += random.choice([-0.1, 0.0, 0.1])

            self.knife_wear_m += wear_rate
            self.p_mech_kw = (2 * 3.14159 * self.rot_speed_rpm * self.torque_nm) / 60000.0
            status_text = "NOMINAL_RUNNING"
            is_fail = 0

            # Nguy cơ sập máy tự nhiên nếu KTV bỏ mặc vượt 140m
            if self.knife_wear_m >= 142.0:
                self.is_tripped = True
                self.torque_nm = 4.6 # Đứt tải
                self.p_mech_kw = 1.38
                status_text = "CATASTROPHIC_KNIFE_BREAK"
                is_fail = 1
                plc_bridge.write_holding_register(self.machine_id, PLCHoldingRegisters.REG_SAFETY_INTERLOCK, 1)

        # Chặn nhiệt độ trong dải vật lý hợp lý
        self.ultrasonic_temp_c = round(max(26.0, min(self.ultrasonic_temp_c, 52.0)), 1)
        delta_t = round(self.ultrasonic_temp_c - self.ambient_temp_c, 1)

        frame = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "line_id": self.machine_id,
            "actual_speed_cph": actual_speed,
            "rot_speed_rpm": round(self.rot_speed_rpm, 1) if actual_speed > 0 else 0.0,
            "tension_torque_nm": round(self.torque_nm, 1),
            "cutting_knife_wear_min": round(self.knife_wear_m, 1),
            "p_mech_kw": round(self.p_mech_kw, 2),
            "ambient_temp_c": self.ambient_temp_c,
            "ultrasonic_temp_c": self.ultrasonic_temp_c,
            "delta_t": delta_t,
            "status": status_text,
            "is_failure": is_fail
        }

        # Lưu liên tục vào fact_sensor_telemetry như một hệ thống SCADA Historian thực tế
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO fact_sensor_telemetry (
                    timestamp, line_id, rot_speed_rpm, tension_torque_nm,
                    cutting_knife_wear_min, p_mech_kw, ambient_temp_c,
                    ultrasonic_temp_c, delta_t, is_failure
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                frame["timestamp"], frame["line_id"],
                frame["rot_speed_rpm"], frame["tension_torque_nm"],
                frame["cutting_knife_wear_min"], frame["p_mech_kw"],
                frame["ambient_temp_c"], frame["ultrasonic_temp_c"],
                frame["delta_t"], frame["is_failure"]
            ))

            # Nếu máy sập khẩn cấp (is_fail = 1), ghi ngay 1 bản ghi vào fact_downtime_events
            if is_fail == 1:
                cursor.execute("""
                    INSERT INTO fact_downtime_events (
                        machine_id, start_time, duration_minutes, error_code, root_cause
                    ) VALUES (?, ?, 30.0, 'E-201', 'Gãy dao cắt màng vô trùng do mòn quá hạn')
                """, (frame["line_id"], frame["timestamp"]))

            conn.commit()
            conn.close()
        except Exception:
            pass

        return frame


line_simulator = StochasticPackagingLineSimulator(machine_id="LINE_01")