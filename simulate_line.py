"""
simulate_line.py
----------------
Stochastic Multi-Fault Packaging Line Simulator for Nestle Dong Nai.
Monotonic physical degradation: Even in Limp-Home, faults progress toward RED!
"""

import os
import random
import sqlite3
from datetime import datetime
from typing import Dict, Any

from industrial_bridge import plc_bridge, PLCHoldingRegisters

DB_PATH = "packaging_factory.db"


class StochasticPackagingLineSimulator:
    def __init__(self, machine_id: str = "LINE_01", db_path: str = DB_PATH):
        self.machine_id = machine_id
        self.db_path = db_path
        self.is_tripped: bool = False
        self.fault_mode = random.choice(["CUTTER_WEAR", "CHILLER_OVERHEAT", "SERVO_OVERLOAD"])
        self._init_physics()

    def _init_physics(self):
        mode = getattr(self, "fault_mode", "CUTTER_WEAR")
        if mode == "CUTTER_WEAR":
            self.knife_wear_m = random.uniform(88.0, 96.0) # Gần mốc 100m
            self.ultrasonic_temp_c = 35.0
            self.torque_nm = 40.5
        elif mode == "CHILLER_OVERHEAT":
            self.knife_wear_m = 25.0
            self.ultrasonic_temp_c = random.uniform(38.0, 39.0) # Gần mốc Amber 39.5°C
            self.torque_nm = 40.5
        else: # SERVO_OVERLOAD
            self.knife_wear_m = 30.0
            self.ultrasonic_temp_c = 35.0
            self.torque_nm = random.uniform(47.0, 49.0) # Gần mốc quá tải
            
        self.rot_speed_rpm = 1500.0
        self.p_mech_kw = round((2 * 3.14159 * self.rot_speed_rpm * self.torque_nm) / 60000.0, 2)

    def replace_part_and_reset(self):
        self.fault_mode = random.choice(["CUTTER_WEAR", "CHILLER_OVERHEAT", "SERVO_OVERLOAD"])
        self.knife_wear_m = 0.0
        self.ultrasonic_temp_c = 33.0
        self.torque_nm = 39.5
        self.rot_speed_rpm = 1500.0
        self.p_mech_kw = 5.8
        self.is_tripped = False
        plc_bridge.write_holding_register(self.machine_id, PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED, 24000)
        plc_bridge.write_holding_register(self.machine_id, PLCHoldingRegisters.REG_SAFETY_INTERLOCK, 0)

    def step(self) -> Dict[str, Any]:
        plc_speed = plc_bridge.read_holding_register(self.machine_id, PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED) or 24000
        is_interlocked = (plc_bridge.read_holding_register(self.machine_id, PLCHoldingRegisters.REG_SAFETY_INTERLOCK) == 1)

        ambient_temp_c = 25.5
        mode = getattr(self, "fault_mode", "CUTTER_WEAR")

        if is_interlocked or self.is_tripped:
            actual_speed = 0
            self.torque_nm = 0.0
            self.p_mech_kw = 0.0
            if self.ultrasonic_temp_c > ambient_temp_c + 2.0:
                self.ultrasonic_temp_c -= 0.5
            status_text = "INTERLOCK_TRIP"
            is_fail = 1 if self.is_tripped else 0

        # KHI CHẠY LIMP-HOME: THÔNG SỐ VẪN TIẾP TỤC SUY THOÁI TỚI HẠN (CHẬM HƠN 24K)
        elif plc_speed <= 18000:
            actual_speed = 18000
            if mode == "CUTTER_WEAR":
                self.knife_wear_m += random.uniform(0.8, 1.5) # Vẫn tăng dần về 142m
                self.torque_nm = 42.0 + random.normalvariate(0, 1.5)
            elif mode == "CHILLER_OVERHEAT":
                self.knife_wear_m += 0.2
                self.ultrasonic_temp_c += random.uniform(0.2, 0.4) # Nhiệt vẫn dâng về 44°C
            elif mode == "SERVO_OVERLOAD":
                self.knife_wear_m += 0.2
                self.torque_nm += random.uniform(0.4, 0.8) # Torque vẫn leo về 58Nm

            self.rot_speed_rpm = 1350.0
            self.p_mech_kw = (2 * 3.14159 * self.rot_speed_rpm * self.torque_nm) / 60000.0
            status_text = "LIMP_HOME_ACTIVE"
            is_fail = 0

            # Chạm ngưỡng RED kể cả khi đang Limp-Home
            if self.knife_wear_m >= 142.0 or self.ultrasonic_temp_c >= 44.0 or self.p_mech_kw >= 8.8:
                self.is_tripped = True
                status_text = "CATASTROPHIC_FAILURE"
                is_fail = 1
                plc_bridge.write_holding_register(self.machine_id, PLCHoldingRegisters.REG_SAFETY_INTERLOCK, 1)

        # KHI CHẠY 24K: SUY THOÁI TỐC ĐỘ CAO
        else:
            actual_speed = 24000
            self.rot_speed_rpm = 1500.0
            if mode == "CUTTER_WEAR":
                self.knife_wear_m += random.uniform(1.8, 3.2) if self.knife_wear_m >= 95.0 else random.uniform(0.5, 1.0)
                self.torque_nm = 42.0 + random.normalvariate(0, 1.5)
            elif mode == "CHILLER_OVERHEAT":
                self.knife_wear_m += 0.3
                self.ultrasonic_temp_c += random.uniform(0.4, 0.8) # Dâng dốc mạnh
            elif mode == "SERVO_OVERLOAD":
                self.knife_wear_m += 0.3
                self.torque_nm += random.uniform(0.8, 1.6) # Quá tải dốc mạnh

            self.p_mech_kw = (2 * 3.14159 * self.rot_speed_rpm * self.torque_nm) / 60000.0
            status_text = "NOMINAL_RUNNING"
            is_fail = 0

            if self.knife_wear_m >= 142.0 or self.ultrasonic_temp_c >= 44.0 or self.p_mech_kw >= 8.8:
                self.is_tripped = True
                status_text = "CATASTROPHIC_FAILURE"
                is_fail = 1
                plc_bridge.write_holding_register(self.machine_id, PLCHoldingRegisters.REG_SAFETY_INTERLOCK, 1)

        self.knife_wear_m = round(self.knife_wear_m, 1)
        self.ultrasonic_temp_c = round(max(26.0, min(self.ultrasonic_temp_c, 52.0)), 1)
        self.torque_nm = round(self.torque_nm, 1)
        self.p_mech_kw = round(self.p_mech_kw, 2)
        delta_t = round(self.ultrasonic_temp_c - ambient_temp_c, 1)
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
                now_ts, self.machine_id,
                self.rot_speed_rpm, self.torque_nm,
                self.knife_wear_m, self.p_mech_kw,
                ambient_temp_c, self.ultrasonic_temp_c,
                delta_t, is_fail
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass

        return {
            "timestamp": now_ts,
            "line_id": self.machine_id,
            "actual_speed_cph": actual_speed,
            "rot_speed_rpm": round(self.rot_speed_rpm, 1) if actual_speed > 0 else 0.0,
            "tension_torque_nm": self.torque_nm,
            "cutting_knife_wear_min": self.knife_wear_m,
            "p_mech_kw": self.p_mech_kw,
            "ambient_temp_c": ambient_temp_c,
            "ultrasonic_temp_c": self.ultrasonic_temp_c,
            "delta_t": delta_t,
            "status": status_text,
            "is_failure": is_fail,
            "fault_mode": mode
        }


line_simulator = StochasticPackagingLineSimulator(machine_id="LINE_01")