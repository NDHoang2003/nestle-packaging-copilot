
"""
simulate_line.py
----------------
Stochastic Multi-Fault Packaging Line Simulator for Nestle Dong Nai.

Simulated runtime telemetry:
- Knife wear is measured in metres (cutting_knife_wear_m).
- AI4I historical tool wear is measured in minutes (cutting_knife_wear_min).
- Runtime persistence uses the existing fact_sensor_telemetry schema.
"""

import logging
import random
import sqlite3
from datetime import datetime
from typing import Any, Dict

from industrial_bridge import plc_bridge, PLCHoldingRegisters


DB_PATH = "packaging_factory.db"
logger = logging.getLogger(__name__)


class StochasticPackagingLineSimulator:
    def __init__(
        self,
        machine_id: str = "LINE_01",
        db_path: str = DB_PATH,
    ):
        self.machine_id = machine_id
        self.db_path = db_path
        self.is_tripped: bool = False
        self.fault_mode = random.choice(
            ["CUTTER_WEAR", "CHILLER_OVERHEAT", "SERVO_OVERLOAD"]
        )
        self._init_physics()

    def _init_physics(self):
        mode = getattr(self, "fault_mode", "CUTTER_WEAR")

        if mode == "CUTTER_WEAR":
            self.knife_wear_m = random.uniform(88.0, 96.0)
            self.ultrasonic_temp_c = 35.0
            self.torque_nm = 40.5

        elif mode == "CHILLER_OVERHEAT":
            self.knife_wear_m = 25.0
            self.ultrasonic_temp_c = random.uniform(38.0, 39.0)
            self.torque_nm = 40.5

        else:  # SERVO_OVERLOAD
            self.knife_wear_m = 30.0
            self.ultrasonic_temp_c = 35.0
            self.torque_nm = random.uniform(47.0, 49.0)

        self.rot_speed_rpm = 1500.0
        self.p_mech_kw = round(
            (2 * 3.14159 * self.rot_speed_rpm * self.torque_nm)
            / 60000.0,
            2,
        )

    def replace_part_and_reset(self):
        """Reset simulated equipment after replacing the worn component."""
        self.fault_mode = random.choice(
            ["CUTTER_WEAR", "CHILLER_OVERHEAT", "SERVO_OVERLOAD"]
        )

        self.knife_wear_m = 0.0
        self.ultrasonic_temp_c = 33.0
        self.torque_nm = 39.5
        self.rot_speed_rpm = 1500.0
        self.p_mech_kw = 5.8
        self.is_tripped = False

        plc_bridge.write_holding_register(
            self.machine_id,
            PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED,
            24000,
        )
        plc_bridge.write_holding_register(
            self.machine_id,
            PLCHoldingRegisters.REG_SAFETY_INTERLOCK,
            0,
        )

    @staticmethod
    def _shift_for_timestamp(timestamp: datetime) -> str:
        if 6 <= timestamp.hour < 14:
            return "Shift 1"
        if 14 <= timestamp.hour < 22:
            return "Shift 2"
        return "Shift 3"

    @staticmethod
    def _error_and_severity(
        mode: str,
        is_failure: int,
        actual_speed: int,
    ) -> tuple[str, str]:
        error_codes = {
            "CUTTER_WEAR": "E-105",
            "CHILLER_OVERHEAT": "E-401",
            "SERVO_OVERLOAD": "E-204",
        }

        error_code = error_codes.get(mode, "NORMAL")

        if is_failure:
            return error_code, "CRITICAL"

        if actual_speed <= 18000:
            return error_code, "WARNING"

        return error_code, "NORMAL"

    def _persist_telemetry(
        self,
        *,
        timestamp: str,
        timestamp_dt: datetime,
        actual_speed: int,
        ambient_temp_c: float,
        delta_t: float,
        previous_sonotrode_temp_c: float,
        is_failure: int,
        mode: str,
    ) -> None:
        """Persist one runtime frame atomically; propagate write failures."""
        error_code, alert_severity = self._error_and_severity(
            mode,
            is_failure,
            actual_speed,
        )

        # Simulator step is assumed to run once per second.
        # dt_dt is the temperature derivative expressed in °C/min.
        dt_dt = round(
            (
                self.ultrasonic_temp_c
                - previous_sonotrode_temp_c
            ) * 60.0,
            3,
        )

        heat_strain_index = round(
            (self.p_mech_kw * 100.0) / (abs(delta_t) + 0.1),
            2,
        )

        conn = None
        cursor = None

        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO fact_sensor_telemetry (
                    timestamp,
                    shift_id,
                    line_id,
                    temp_cleanroom_c,
                    temp_sonotrode_c,
                    speed_servo_rpm,
                    tension_torque_nm,
                    cutting_knife_wear_min,
                    cutting_knife_wear_m,
                    delta_t,
                    dt_dt,
                    p_mech_kw,
                    heat_strain_index,
                    error_code,
                    is_failure,
                    alert_severity
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    self._shift_for_timestamp(timestamp_dt),
                    self.machine_id,
                    ambient_temp_c,
                    self.ultrasonic_temp_c,
                    self.rot_speed_rpm if actual_speed > 0 else 0.0,
                    self.torque_nm,

                    # Runtime simulator has metre units, not AI4I minutes.
                    None,
                    self.knife_wear_m,

                    delta_t,
                    dt_dt,
                    self.p_mech_kw,
                    heat_strain_index,
                    error_code,
                    int(is_failure),
                    alert_severity,
                ),
            )

            # record_id is generated by SQLite.
            conn.commit()

        except Exception:
            if conn is not None:
                conn.rollback()
            raise

        finally:
            if cursor is not None:
                cursor.close()

            if conn is not None:
                conn.close()

    def step(self) -> Dict[str, Any]:
        plc_speed = (
            plc_bridge.read_holding_register(
                self.machine_id,
                PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED,
            )
            or 24000
        )

        is_interlocked = (
            plc_bridge.read_holding_register(
                self.machine_id,
                PLCHoldingRegisters.REG_SAFETY_INTERLOCK,
            )
            == 1
        )

        ambient_temp_c = 25.5
        mode = getattr(self, "fault_mode", "CUTTER_WEAR")
        previous_sonotrode_temp_c = self.ultrasonic_temp_c

        if is_interlocked or self.is_tripped:
            actual_speed = 0
            self.torque_nm = 0.0
            self.p_mech_kw = 0.0

            if self.ultrasonic_temp_c > ambient_temp_c + 2.0:
                self.ultrasonic_temp_c -= 0.5

            status_text = "INTERLOCK_TRIP"
            is_fail = 1 if self.is_tripped else 0

        # LIMP-HOME: degradation continues at a slower rate.
        elif plc_speed <= 18000:
            actual_speed = 18000

            if mode == "CUTTER_WEAR":
                self.knife_wear_m += random.uniform(0.8, 1.5)
                self.torque_nm = 42.0 + random.normalvariate(0, 1.5)

            elif mode == "CHILLER_OVERHEAT":
                self.knife_wear_m += 0.2
                self.ultrasonic_temp_c += random.uniform(0.2, 0.4)

            elif mode == "SERVO_OVERLOAD":
                self.knife_wear_m += 0.2
                self.torque_nm += random.uniform(0.4, 0.8)

            self.rot_speed_rpm = 1350.0
            self.p_mech_kw = (
                2 * 3.14159 * self.rot_speed_rpm * self.torque_nm
            ) / 60000.0

            status_text = "LIMP_HOME_ACTIVE"
            is_fail = 0

            if (
                self.knife_wear_m >= 142.0
                or self.ultrasonic_temp_c >= 44.0
                or self.p_mech_kw >= 8.8
            ):
                self.is_tripped = True
                status_text = "CATASTROPHIC_FAILURE"
                is_fail = 1

                plc_bridge.write_holding_register(
                    self.machine_id,
                    PLCHoldingRegisters.REG_SAFETY_INTERLOCK,
                    1,
                )

        # Nominal 24K operation: faster degradation.
        else:
            actual_speed = 24000
            self.rot_speed_rpm = 1500.0

            if mode == "CUTTER_WEAR":
                if self.knife_wear_m >= 95.0:
                    self.knife_wear_m += random.uniform(1.8, 3.2)
                else:
                    self.knife_wear_m += random.uniform(0.5, 1.0)

                self.torque_nm = 42.0 + random.normalvariate(0, 1.5)

            elif mode == "CHILLER_OVERHEAT":
                self.knife_wear_m += 0.3
                self.ultrasonic_temp_c += random.uniform(0.4, 0.8)

            elif mode == "SERVO_OVERLOAD":
                self.knife_wear_m += 0.3
                self.torque_nm += random.uniform(0.8, 1.6)

            self.p_mech_kw = (
                2 * 3.14159 * self.rot_speed_rpm * self.torque_nm
            ) / 60000.0

            status_text = "NOMINAL_RUNNING"
            is_fail = 0

            if (
                self.knife_wear_m >= 142.0
                or self.ultrasonic_temp_c >= 44.0
                or self.p_mech_kw >= 8.8
            ):
                self.is_tripped = True
                status_text = "CATASTROPHIC_FAILURE"
                is_fail = 1

                plc_bridge.write_holding_register(
                    self.machine_id,
                    PLCHoldingRegisters.REG_SAFETY_INTERLOCK,
                    1,
                )

        self.knife_wear_m = round(self.knife_wear_m, 1)
        self.ultrasonic_temp_c = round(
            max(26.0, min(self.ultrasonic_temp_c, 52.0)),
            1,
        )
        self.torque_nm = round(self.torque_nm, 1)
        self.p_mech_kw = round(self.p_mech_kw, 2)

        delta_t = round(
            self.ultrasonic_temp_c - ambient_temp_c,
            1,
        )

        now_dt = datetime.now()
        now_ts = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        # Do not return a successful-looking frame if persistence fails.
        try:
            self._persist_telemetry(
                timestamp=now_ts,
                timestamp_dt=now_dt,
                actual_speed=actual_speed,
                ambient_temp_c=ambient_temp_c,
                delta_t=delta_t,
                previous_sonotrode_temp_c=previous_sonotrode_temp_c,
                is_failure=is_fail,
                mode=mode,
            )
        except sqlite3.Error:
            logger.exception(
                "Telemetry persistence failed for line_id=%s timestamp=%s",
                self.machine_id,
                now_ts,
            )
            raise

        return {
            "timestamp": now_ts,
            "line_id": self.machine_id,
            "actual_speed_cph": actual_speed,
            "rot_speed_rpm": (
                round(self.rot_speed_rpm, 1)
                if actual_speed > 0
                else 0.0
            ),
            "tension_torque_nm": self.torque_nm,

            # Runtime simulator wear is measured in metres.
            "cutting_knife_wear_m": self.knife_wear_m,

            "p_mech_kw": self.p_mech_kw,
            "ambient_temp_c": ambient_temp_c,
            "ultrasonic_temp_c": self.ultrasonic_temp_c,
            "delta_t": delta_t,
            "status": status_text,
            "is_failure": is_fail,
            "fault_mode": mode,
        }


line_simulator = StochasticPackagingLineSimulator(
    machine_id="LINE_01"
)
