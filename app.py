"""
app.py
------
Nestle Dong Nai - Maintenance Technician Copilot HMI Console.
Full-Loop Persistence & Bulletproof Session State Logging (Zero KeyError).
"""

import importlib
import sqlite3
import streamlit as st
from datetime import datetime

import simulate_line
importlib.reload(simulate_line)
from simulate_line import StochasticPackagingLineSimulator

from degradation_engine import DegradationDetector, DegradationState
from industrial_bridge import plc_bridge, PLCHoldingRegisters
from factory_tools import (
    execute_line_derate,
    reserve_sap_spare_part,
    approve_loto_unlock
)
from roi_engine import roi_engine

DB_PATH = "packaging_factory.db"

st.set_page_config(
    page_title="Nestle Technician Copilot Console",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    .main { background-color: #0F141C; color: #FFFFFF; }
    .stMetric { background-color: #1A2230; padding: 12px; border-radius: 6px; border: 1px solid #2A3649; }
    .badge-green { background-color: #007A33; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold; font-size: 15px; }
    .badge-amber { background-color: #D9822B; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold; font-size: 15px; }
    .badge-red { background-color: #DB3737; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold; font-size: 15px; }
    .stButton>button { width: 100%; height: 46px; font-weight: bold; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# SHIFT LOG
# ==============================================================================
def append_shift_log(message: str):
    """Append to the UI session log while defending against missing state."""
    if "shift_log" not in st.session_state or not isinstance(st.session_state["shift_log"], list):
        st.session_state["shift_log"] = []
    st.session_state["shift_log"].append(message)


# ==============================================================================
# DATABASE HELPERS
# ==============================================================================
def get_part_stock(target_part_pattern: str) -> int:
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT stock_quantity FROM dim_spare_parts WHERE part_id LIKE ? LIMIT 1",
            (f"%{target_part_pattern}%",),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        # Do not report a fabricated stock value as though the query succeeded.
        return 0
    finally:
        if conn is not None:
            conn.close()


def restock_all_spare_parts():
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.execute("UPDATE dim_spare_parts SET stock_quantity = stock_quantity + 10")
        conn.commit()
        return True
    except sqlite3.Error:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()


def create_app_work_order(machine_id, error_code, summary, downtime_duration_minutes=0.0, existing_event_id=None):
    """Create a downtime/event record and linked work order atomically.

    The current schema requires downtime.record_id and work_order.event_id.
    A work order cannot be created if no telemetry row exists to link it to.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        wo_id = f"WO-APP-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        if existing_event_id is None:
            cursor.execute("""
                INSERT INTO fact_downtime_events (
                    record_id, line_id, timestamp, shift_id, error_code,
                    downtime_duration_minutes, impact_units_lost
                )
                SELECT record_id, ?, ?, ?, ?, ?, ?
                FROM fact_sensor_telemetry
                WHERE line_id = ?
                ORDER BY record_id DESC
                LIMIT 1
            """, (machine_id, now_ts, "Shift 1", error_code,
                    float(downtime_duration_minutes), int(float(downtime_duration_minutes) * 400), machine_id))
            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"Cannot create work order for {machine_id}: no telemetry row exists to link."
                )
            event_id = cursor.lastrowid
        else:
            cursor.execute("""
                SELECT event_id FROM fact_downtime_events
                WHERE event_id = ? AND line_id = ?
            """, (existing_event_id, machine_id))
            if cursor.fetchone() is None:
                raise RuntimeError(f"Cannot link work order: event {existing_event_id} does not exist for {machine_id}.")
            event_id = existing_event_id

        cursor.execute("""
            INSERT INTO fact_work_orders (
                work_order_id, event_id, line_id, error_code, created_at,
                priority, loto_status, technician_assigned, resolution_notes, order_status
            ) VALUES (?, ?, ?, ?, ?, 'P1_URGENT', 'LOTO_REQUIRED',
                      'Nguyễn Doãn Hoàng (KTV Ca 1)', ?, 'OPEN')
        """, (wo_id, event_id, machine_id, error_code, now_ts, summary))
        conn.commit()
        return wo_id, event_id
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()


def close_app_work_order(work_order_id, technician_name):
    """Close only the supplied open work order; never bulk-close other orders."""
    if not work_order_id:
        raise ValueError("Cannot close work order: no work_order_id was supplied.")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            UPDATE fact_work_orders
            SET order_status = 'CLOSED', loto_status = 'RESTORED',
                closed_at = ?, technician_assigned = ?
            WHERE work_order_id = ? AND order_status = 'OPEN'
        """, (now_ts, technician_name, work_order_id))
        if cursor.rowcount != 1:
            raise RuntimeError(
                f"Work order {work_order_id!r} was not updated; verify its ID and status."
            )
        conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()


def update_downtime_event(event_id, duration_mins, machine_id, error_code, work_order_id=None):
    """Update the existing incident row when an AMBER incident escalates to RED."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE fact_downtime_events
            SET downtime_duration_minutes = ?, impact_units_lost = ?, error_code = ?
            WHERE event_id = ? AND line_id = ?
        """, (float(duration_mins), int(float(duration_mins) * 400), error_code, event_id, machine_id))
        if cursor.rowcount != 1:
            raise RuntimeError(f"Cannot update downtime event {event_id}: event not found for {machine_id}.")
        if work_order_id:
            cursor.execute("""
                UPDATE fact_work_orders
                SET error_code = ?
                WHERE work_order_id = ? AND event_id = ? AND line_id = ? AND order_status = 'OPEN'
            """, (error_code, work_order_id, event_id, machine_id))
            if cursor.rowcount != 1:
                raise RuntimeError(f"Cannot synchronize Work Order {work_order_id} with RED event {event_id}.")
        conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()


def record_downtime_event(machine_id, error_code, root_cause, duration_mins=15.0):
    """Persist downtime linked to the latest telemetry row for this line.

    root_cause is included in the signature for caller compatibility; this
    schema version has no root_cause column in fact_downtime_events.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # error_code is a foreign key. PLANNED_PM is not present in the
        # current catalog, so resolve unknown codes to the latest telemetry
        # code until the schema includes a dedicated planned-maintenance code.
        cursor.execute(
            "SELECT 1 FROM dim_error_catalog WHERE error_code = ? LIMIT 1",
            (error_code,),
        )
        if cursor.fetchone() is None:
            cursor.execute("""
                SELECT error_code
                FROM fact_sensor_telemetry
                WHERE line_id = ?
                ORDER BY record_id DESC
                LIMIT 1
            """, (machine_id,))
            latest = cursor.fetchone()
            if latest is None:
                raise RuntimeError(
                    f"Cannot record downtime for {machine_id}: no telemetry row exists to link."
                )
            error_code = latest[0]

        cursor.execute("""
            INSERT INTO fact_downtime_events (
                record_id, line_id, timestamp, shift_id, error_code,
                downtime_duration_minutes, impact_units_lost
            )
            SELECT record_id, ?, ?, ?, ?, ?, ?
            FROM fact_sensor_telemetry
            WHERE line_id = ?
            ORDER BY record_id DESC
            LIMIT 1
        """, (
            machine_id, now_ts, "Shift 1", error_code,
            duration_mins, int(duration_mins * 400), machine_id
        ))
        if cursor.rowcount != 1:
            raise RuntimeError(
                f"Cannot record downtime for {machine_id}: no telemetry row exists to link."
            )
        conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()


# ==============================================================================
# SAFE SESSION INITIALIZATION
# ==============================================================================
if "shift_log" not in st.session_state:
    st.session_state["shift_log"] = []

# A simulated PLC register is process-local RAM, not persisted machine state.
# On first bootstrap of this UI session, clear an orphaned interlock only when
# there is no active incident/WO in session state. A live RED incident remains latched.
if "plc_session_initialized" not in st.session_state:
    has_active_incident = bool(
        st.session_state.get("red_latched", False)
        or st.session_state.get("current_wo_id")
        or st.session_state.get("current_event_id")
    )
    if not has_active_incident:
        plc_bridge.write_holding_register(
            "LINE_01", PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED, 24000
        )
        plc_bridge.write_holding_register(
            "LINE_01", PLCHoldingRegisters.REG_SAFETY_INTERLOCK, 0
        )
    st.session_state["plc_session_initialized"] = True

if "sim" not in st.session_state or not hasattr(st.session_state["sim"], "fault_mode"):
    st.session_state["sim"] = StochasticPackagingLineSimulator(machine_id="LINE_01")

if not hasattr(st.session_state["sim"], "fault_mode"):
    st.session_state["sim"].fault_mode = "CUTTER_WEAR"

if "detector" not in st.session_state:
    st.session_state["detector"] = DegradationDetector(window_size=15)

if "active_sap_slip" not in st.session_state:
    st.session_state["active_sap_slip"] = None

if "current_wo_id" not in st.session_state:
    st.session_state["current_wo_id"] = None

if "current_event_id" not in st.session_state:
    st.session_state["current_event_id"] = None

if "red_latched" not in st.session_state:
    st.session_state["red_latched"] = False

if "red_event_persisted" not in st.session_state:
    st.session_state["red_event_persisted"] = False

if "maintenance_stop_latched" not in st.session_state:
    st.session_state["maintenance_stop_latched"] = False

if "derate_seconds_count" not in st.session_state:
    st.session_state["derate_seconds_count"] = 0

sim: StochasticPackagingLineSimulator = st.session_state["sim"]
detector: DegradationDetector = st.session_state["detector"]

fault_mode_now = getattr(sim, "fault_mode", "CUTTER_WEAR")
if len(st.session_state["shift_log"]) == 0:
    append_shift_log(f"{datetime.now().strftime('%H:%M:%S')} - Trạm HMI sẵn sàng. Dây chuyền tiềm ẩn: {fault_mode_now}")


def advance_simulation_step(num_steps: int = 1):
    if st.session_state.get("red_latched", False):
        append_shift_log("RED đang được giữ chốt: cần hoàn tất bảo trì mô phỏng trước khi chạy tiếp.")
        return

    for _ in range(num_steps):
        if st.session_state.get("red_latched", False):
            break
        frame = sim.step()
        st.session_state["latest_frame"] = frame

        if frame["actual_speed_cph"] == 18000:
            st.session_state["derate_seconds_count"] += 1

        assessment = detector.ingest_frame("LINE_01", {
            "air_temp": frame["ambient_temp_c"],
            "process_temp": frame["ultrasonic_temp_c"],
            "rot_speed": frame["rot_speed_rpm"],
            "torque": frame["tension_torque_nm"],
            "tool_wear": frame["cutting_knife_wear_m"],
            "p_mech": frame["p_mech_kw"],
            "delta_t": frame["delta_t"],
        })
        st.session_state["assessment"] = assessment

        current_f = frame.get("fault_mode", getattr(sim, "fault_mode", "CUTTER_WEAR"))

        # EARLY WARNING / AMBER: reserve stock once; retry a failed WO write without reserving again.
        amber_triggered = assessment.state == DegradationState.AMBER or frame["actual_speed_cph"] == 18000
        if amber_triggered and st.session_state.get("current_wo_id") is None:
            if current_f == "CHILLER_OVERHEAT" or frame["ultrasonic_temp_c"] >= 38.5:
                err_code = "E-105"
                part_type = "JAW"
                reason_txt = f"Nhiệt độ Sonotrode dâng cao: {frame['ultrasonic_temp_c']}°C (Chiller nghẽn cặn)"
            elif current_f == "SERVO_OVERLOAD" or frame["p_mech_kw"] >= 7.2:
                err_code = "E-302"
                part_type = "BELT"
                reason_txt = f"Quá tải động cơ Servo kéo màng: P_mech={frame['p_mech_kw']}kW"
            else:
                err_code = "E-204"
                part_type = "CUT"
                reason_txt = f"Dao cắt màng mòn tiệm cận ngưỡng: {frame['cutting_knife_wear_m']}m"

            derate_result = execute_line_derate("LINE_01", 18000, reason_txt)
            execution = derate_result.get("execution_result", {})
            if execution.get("status") != "SUCCESS":
                raise RuntimeError(
                    f"Line derate was not confirmed: {execution.get('status', 'unknown status')}"
                )

            if st.session_state.get("active_sap_slip") is None:
                sap_res = reserve_sap_spare_part("LINE_01", part_type)
                slip = sap_res.get("requisition_slip")
                if not slip:
                    raise RuntimeError(
                        f"Spare-part reservation not confirmed: {sap_res.get('message', sap_res.get('status', 'unknown error'))}"
                    )
                # Store immediately after confirmed reservation so a WO write failure cannot reserve twice.
                st.session_state["active_sap_slip"] = slip
            slip = st.session_state["active_sap_slip"]
            shelf = slip.get("shelf_location", "Kho chính")

            wo_id, event_id = create_app_work_order("LINE_01", err_code, f"[COPILOT INTERVENTION]: {reason_txt}. Lấy phụ tùng tại {shelf}.")
            st.session_state["current_wo_id"] = wo_id
            st.session_state["current_event_id"] = event_id

            roi_engine.compute_intervention_roi("LINE_01", "AMBER_AUTONOMOUS_INTERVENTION", wo_id)
            append_shift_log(
                f"{datetime.now().strftime('%H:%M:%S')} - CẢNH BÁO AMBER ({err_code}): mô phỏng hạ tốc 18k cph, tạo phiếu {wo_id}, phụ tùng tại {shelf}."
            )

        # RED: latch once, stop further simulation steps, and persist one incident only.
        if assessment.state == DegradationState.RED or frame["is_failure"] == 1:
            st.session_state["red_latched"] = True
            err = "E-204" if current_f == "CUTTER_WEAR" else ("E-105" if current_f == "CHILLER_OVERHEAT" else "E-302")
            cause = f"Sập máy khẩn cấp: {', '.join(assessment.drift_reasons) if assessment.drift_reasons else 'Chạm ngưỡng tới hạn vật lý'}"
            try:
                existing_event_id = st.session_state.get("current_event_id")
                if existing_event_id:
                    wo_id = st.session_state.get("current_wo_id")
                    if not wo_id:
                        wo_id, _ = create_app_work_order(
                            "LINE_01", err, f"[RED INCIDENT]: {cause}", existing_event_id=existing_event_id
                        )
                        st.session_state["current_wo_id"] = wo_id
                    update_downtime_event(existing_event_id, 30.0, "LINE_01", err, wo_id)
                else:
                    wo_id, event_id = create_app_work_order(
                        "LINE_01", err, f"[RED INCIDENT]: {cause}", downtime_duration_minutes=30.0
                    )
                    st.session_state["current_wo_id"] = wo_id
                    st.session_state["current_event_id"] = event_id
                st.session_state["red_event_persisted"] = True
                append_shift_log(
                    f"{datetime.now().strftime('%H:%M:%S')} - SẬP MÁY RED ({err}): giữ chốt RED; downtime 30 phút gắn với event #{st.session_state.get('current_event_id')}; Work Order {st.session_state.get('current_wo_id')}."
                )
            except Exception as exc:
                st.session_state["red_event_persisted"] = False
                append_shift_log(
                    f"{datetime.now().strftime('%H:%M:%S')} - RED đã giữ chốt nhưng ghi nhận nghiệp vụ thất bại: {exc}"
                )
            break


# Initial frame. Simulator persistence failure raises rather than showing a fake frame.
if "latest_frame" not in st.session_state:
    st.session_state["latest_frame"] = sim.step()

if "assessment" not in st.session_state:
    st.session_state["assessment"] = detector.evaluate_machine("LINE_01")

latest_frame = st.session_state["latest_frame"]
assessment = st.session_state["assessment"]
current_speed_reading = plc_bridge.read_holding_register("LINE_01", PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED)
is_interlocked = (plc_bridge.read_holding_register("LINE_01", PLCHoldingRegisters.REG_SAFETY_INTERLOCK) == 1)
# An asserted interlock means actual line speed is zero, even if the simulated
# PLC's last speed register still contains the previous limp-home setpoint.
current_speed = 0 if is_interlocked else (24000 if current_speed_reading is None else current_speed_reading)

# Header
st.markdown("### 🏭 PACKAGING COPILOT — SIMULATED LINE_01")
st.caption("Prototype giao diện cho dây chuyền mô phỏng; không phải HMI đã kết nối thiết bị Nestlé.")

current_fault = latest_frame.get("fault_mode", getattr(sim, "fault_mode", "CUTTER_WEAR"))
part_key = "CUT" if current_fault == "CUTTER_WEAR" else ("JAW" if current_fault == "CHILLER_OVERHEAT" else "BELT")
current_warehouse_stock = get_part_stock(part_key)

st.caption(f"Trạm Tác Nghiệp Kỹ Thuật Viên | LINE_01 | Kịch bản mô phỏng: **{current_fault}** | Tồn kho demo: **{current_warehouse_stock} bộ**")

is_red_state = st.session_state.get("red_latched", False) or is_interlocked or assessment.state == DegradationState.RED or latest_frame.get("is_failure") == 1
is_amber_state = (current_speed <= 18000 or assessment.state == DegradationState.AMBER) and not is_red_state

if is_red_state:
    badge_html = '<span class="badge-red">RED — INTERLOCK MÔ PHỎNG</span>'
elif is_amber_state:
    badge_html = '<span class="badge-amber">AMBER — LIMP-HOME 18.000 CPH</span>'
else:
    badge_html = '<span class="badge-green">GREEN — 24.000 CPH (MÔ PHỎNG)</span>'

st.markdown(f"**Trạng thái mô phỏng:** {badge_html} &nbsp;&nbsp;|&nbsp;&nbsp; Điểm suy thoái: **{assessment.degradation_score}%**", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# 1. Telemetry KPIs
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(label="Tốc độ mô phỏng", value=f"{current_speed:,} cph")
with c2:
    wear_m = latest_frame["cutting_knife_wear_m"]
    st.metric(label="Độ mòn dao cắt", value=f"{wear_m:.1f} m")
with c3:
    st.metric(label="Công suất cơ P_mech", value=f"{latest_frame['p_mech_kw']:.2f} kW")
with c4:
    temp_c = latest_frame["ultrasonic_temp_c"]
    st.metric(label="Nhiệt độ Sonotrode", value=f"{temp_c:.1f} °C", delta="Trong giới hạn demo ≤40°C" if temp_c <= 40 else "QUÁ NHIỆT (>40°C)", delta_color="normal" if temp_c <= 40 else "inverse")

st.progress(min(wear_m / 140.0, 1.0))
st.caption(f"Thanh đo mài mòn dao (ngưỡng mô hình): **{wear_m:.1f}m / 140.0m**")
st.markdown("---")

# 2. Simulation controls
st.markdown("##### Bảng điều khiển dây chuyền mô phỏng")
btn1, btn2, btn3, btn4 = st.columns([1, 1, 1, 1])
with btn1:
    if st.button("▶ Bước 1 giây", disabled=is_red_state):
        advance_simulation_step(1)
        st.rerun()
with btn2:
    if st.button("⏩ Bước 5 giây", disabled=is_red_state):
        advance_simulation_step(5)
        st.rerun()
with btn3:
    if st.button("🔄 Đổi kịch bản / ca mới", disabled=is_red_state or bool(st.session_state.get("current_wo_id"))):
        sim.replace_part_and_reset()
        st.session_state["active_sap_slip"] = None
        st.session_state["current_wo_id"] = None
        st.session_state["current_event_id"] = None
        st.session_state["red_latched"] = False
        st.session_state["red_event_persisted"] = False
        st.session_state["maintenance_stop_latched"] = False
        st.session_state["derate_seconds_count"] = 0
        st.session_state["detector"] = DegradationDetector(window_size=15)
        st.session_state["latest_frame"] = sim.step()
        new_mode = getattr(st.session_state["sim"], "fault_mode", "CUTTER_WEAR")
        append_shift_log(f"{datetime.now().strftime('%H:%M:%S')} - Bắt đầu kịch bản mới. Chế độ: {new_mode}")
        st.rerun()
with btn4:
    if st.button("📥 Nhập kho demo (+10)"):
        try:
            restock_all_spare_parts()
        except sqlite3.Error as exc:
            st.error(f"Không thể cập nhật tồn kho demo: {exc}")
        else:
            st.success("Đã cộng thêm 10 bộ vào catalog phụ tùng SQLite của prototype.")
            append_shift_log(f"{datetime.now().strftime('%H:%M:%S')} - Tăng tồn kho demo +10.")
            st.rerun()

# Scenario economics; explicitly labeled as a model, not realized savings.
if st.session_state["derate_seconds_count"] > 0:
    secs = st.session_state["derate_seconds_count"]
    speed_loss_vnd = int(secs * (6000 / 3600) * 8000)
    net_avoidance_vnd = max(0, 103500000 - speed_loss_vnd - 9600000)
    st.info(f"""
    **Mô hình chi phí limp-home (kịch bản, không phải saving thực tế):** đã chạy chậm **{secs} giây**.
    - Tổn thất ước tính do giảm tốc: **-{speed_loss_vnd:,.0f} VNĐ**.
    - Giá trị bảo toàn ròng theo giả định trong code: **+{net_avoidance_vnd:,.0f} VNĐ**.
    """)

st.markdown("---")
col_left, col_right = st.columns([1, 1])
with col_left:
    st.markdown("##### Copilot — gợi ý cho kỹ thuật viên")
    if is_red_state:
        st.error(f"""
        **RED — dừng bảo vệ trong mô hình**
        - Lý do: {', '.join(assessment.drift_reasons) if assessment.drift_reasons else 'Vượt ngưỡng mô hình'}
        - RED được giữ chốt đến khi hoàn tất bảo trì mô phỏng; không thể tiếp tục bước mô phỏng hoặc đổi kịch bản.
        - {('Đã lưu event downtime và Work Order liên kết.' if st.session_state.get('red_event_persisted') else 'Chưa xác nhận lưu event downtime/Work Order; xem nhật ký để biết lỗi ghi dữ liệu.')}
        - Quy trình LOTO sản xuất thật phải theo quy định EHS đã phê duyệt.
        """)
    elif is_amber_state:
        st.warning(f"""
        **AMBER — cảnh báo trong mô hình**
        - Tốc độ mô phỏng: **18.000 cph**.
        - Work Order gần nhất: `{st.session_state.get('current_wo_id')}`.
        - Khuyến nghị demo: xem phiếu phụ tùng, chủ động dừng và giải thích lý do kỹ thuật.
        """)
    else:
        st.success("**Mô hình đang ở trạng thái GREEN:** tốc độ danh định mô phỏng 24.000 cph.")

with col_right:
    st.markdown("##### Phiếu phụ tùng — catalog demo SQLite")
    slip = st.session_state["active_sap_slip"]
    if slip and is_amber_state:
        st.markdown(f"""
        <div style="background-color: #1A2230; border: 1px dashed #D9822B; border-radius: 8px; padding: 14px;">
            <b style="color: #ECC94B;">MÃ PHIẾU: {slip.get('requisition_id')}</b>
            <div style="font-size: 13px; margin-top: 6px; line-height: 1.6;">
                <div>Linh kiện: <b>{slip.get('part_name')}</b></div>
                <div>Mã vật tư: <code>{slip.get('sap_material_code')}</code></div>
                <div>Vị trí kệ demo: <b style="color: #48BB78; font-size: 15px;">{slip.get('shelf_location')}</b></div>
                <div>Tồn kho: <b>{slip.get('remaining_warehouse_stock', current_warehouse_stock)} bộ</b> | Đơn giá catalog: <b>{slip.get('unit_cost_vnd', 0):,.0f} VNĐ</b></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("Chưa có phiếu phụ tùng. Khi detector kích hoạt luồng AMBER, prototype sẽ tra catalog nội bộ.")

st.markdown("---")
st.markdown("##### Thao tác bảo trì mô phỏng — không phải hệ thống an toàn được chứng nhận")
act1, act2 = st.columns([1, 1])
with act1:
    st.markdown("**1. Dừng chủ động (mô phỏng)**")
    st.caption("Ghi nhận sự kiện downtime liên kết với telemetry gần nhất nếu thao tác hoàn tất.")
    if st.button("🛑 Dừng mô phỏng để bảo trì", disabled=is_red_state or st.session_state.get("maintenance_stop_latched", False)):
        plc_bridge.write_holding_register("LINE_01", PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED, 0)
        plc_bridge.write_holding_register("LINE_01", PLCHoldingRegisters.REG_SAFETY_INTERLOCK, 1)
        try:
            active_event_id = st.session_state.get("current_event_id")
            if active_event_id:
                active_fault = latest_frame.get("fault_mode", getattr(sim, "fault_mode", "CUTTER_WEAR"))
                active_error = "E-204" if active_fault == "CUTTER_WEAR" else ("E-105" if active_fault == "CHILLER_OVERHEAT" else "E-302")
                update_downtime_event(active_event_id, 3.0, "LINE_01", active_error, st.session_state.get("current_wo_id"))
            else:
                record_downtime_event("LINE_01", "PLANNED_PM", "KTV dừng mô phỏng để thay linh kiện", duration_mins=3.0)
        except Exception as exc:
            st.error(f"Không ghi được downtime; không báo thành công: {exc}")
        else:
            st.session_state["maintenance_stop_latched"] = True
            append_shift_log(f"{datetime.now().strftime('%H:%M:%S')} - Dừng mô phỏng, downtime 3 phút đã ghi.")
            st.success("Đã dừng mô phỏng và ghi nhận downtime vào SQLite.")
            st.rerun()

with act2:
    st.markdown("**2. Xác nhận bảo trì & mở khóa LOTO mô phỏng**")
    t_sonotrode = latest_frame["ultrasonic_temp_c"]
    safe_loto = t_sonotrode <= 40.0
    if current_warehouse_stock <= 0 and not st.session_state.get("active_sap_slip"):
        st.error(f"Catalog demo báo hết phụ tùng (tồn kho = {current_warehouse_stock}).")
    with st.form("loto_stochastic_form"):
        ktv_name = st.text_input("Kỹ thuật viên", value="Nguyễn Doãn Hoàng (KTV Ca 1)")
        padlock = st.text_input("Mã khóa demo", value="PADLOCK-DEMO-001")
        confirm_ok = st.checkbox("Xác nhận hoàn tất thay thế linh kiện trong kịch bản mô phỏng.")
        btn_unlock = st.form_submit_button("Xác nhận hoàn tất & khởi động lại (mô phỏng)")
        if btn_unlock:
            if not (is_red_state or st.session_state.get("maintenance_stop_latched", False) or st.session_state.get("current_wo_id")):
                st.error("Chỉ có thể hoàn tất bảo trì sau khi mô phỏng đã dừng hoặc có Work Order đang mở.")
            elif current_warehouse_stock <= 0 and not st.session_state.get("active_sap_slip"):
                st.error("Bị từ chối trong demo: catalog không có phụ tùng thay thế.")
            elif not confirm_ok:
                st.error("Cần xác nhận đã hoàn tất thay thế linh kiện.")
            elif not safe_loto:
                st.error(f"Cổng nhiệt demo từ chối: {t_sonotrode:.1f}°C > 40°C.")
            else:
                try:
                    if st.session_state.get("red_latched", False) and not st.session_state.get("red_event_persisted", False):
                        retry_fault = latest_frame.get("fault_mode", getattr(sim, "fault_mode", "CUTTER_WEAR"))
                        retry_err = "E-204" if retry_fault == "CUTTER_WEAR" else ("E-105" if retry_fault == "CHILLER_OVERHEAT" else "E-302")
                        retry_event_id = st.session_state.get("current_event_id")
                        retry_wo_id = st.session_state.get("current_wo_id")
                        if retry_event_id:
                            if not retry_wo_id:
                                retry_wo_id, _ = create_app_work_order(
                                    "LINE_01", retry_err, "[RED INCIDENT RETRY]: Khôi phục Work Order cho event hiện có.", existing_event_id=retry_event_id
                                )
                                st.session_state["current_wo_id"] = retry_wo_id
                            update_downtime_event(retry_event_id, 30.0, "LINE_01", retry_err, retry_wo_id)
                        else:
                            retry_wo_id, retry_event_id = create_app_work_order(
                                "LINE_01", retry_err, "[RED INCIDENT RETRY]: Khôi phục ghi nhận sự cố RED.", downtime_duration_minutes=30.0
                            )
                            st.session_state["current_wo_id"] = retry_wo_id
                            st.session_state["current_event_id"] = retry_event_id
                        st.session_state["red_event_persisted"] = True
                        append_shift_log(f"{datetime.now().strftime('%H:%M:%S')} - Đã khôi phục ghi nhận RED trước khi mở khóa.")
                    loto_result = approve_loto_unlock("LINE_01", ktv_name, padlock)
                    if loto_result.get("status") != "SUCCESS":
                        raise RuntimeError(loto_result.get("message", loto_result.get("reason", "LOTO unlock was not confirmed")))
                    if st.session_state.get("current_wo_id"):
                        close_app_work_order(st.session_state["current_wo_id"], ktv_name)
                except Exception as exc:
                    st.error(f"Không thể xác nhận đóng Work Order/mở khóa: {exc}")
                else:
                    sim.replace_part_and_reset()
                    st.session_state["active_sap_slip"] = None
                    st.session_state["current_wo_id"] = None
                    st.session_state["current_event_id"] = None
                    st.session_state["red_latched"] = False
                    st.session_state["red_event_persisted"] = False
                    st.session_state["maintenance_stop_latched"] = False
                    st.session_state["derate_seconds_count"] = 0
                    st.session_state["detector"] = DegradationDetector(window_size=15)
                    try:
                        st.session_state["latest_frame"] = sim.step()
                    except sqlite3.Error as exc:
                        st.error(f"Máy mô phỏng đã được reset trong bộ nhớ nhưng frame không lưu được: {exc}")
                        st.stop()
                    append_shift_log(f"{datetime.now().strftime('%H:%M:%S')} - KTV {ktv_name} hoàn tất bảo trì mô phỏng; khóa {padlock}.")
                    st.success("Đã hoàn tất chu trình bảo trì mô phỏng.")
                    st.rerun()

st.markdown("---")
with st.expander("📜 Nhật ký sự cố & thao tác ca trực", expanded=True):
    logs_to_show = st.session_state.get("shift_log", [])
    for item in reversed(logs_to_show[-8:]):
        st.markdown(f"- `{item}`")
