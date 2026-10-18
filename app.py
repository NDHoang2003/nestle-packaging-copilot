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
# HÀM GHI NHẬT KÝ AN TOÀN TUYỆT ĐỐI (CHỐNG MỌI LỖI KEYERROR)
# ==============================================================================
def append_shift_log(message: str):
    """Ghi log ca trực an toàn, tự động khởi tạo nếu session state bị thiếu key."""
    if "shift_log" not in st.session_state or not isinstance(st.session_state["shift_log"], list):
        st.session_state["shift_log"] = []
    st.session_state["shift_log"].append(message)


# ==============================================================================
# HÀM DATABASE THAO TÁC THỰC
# ==============================================================================
def get_part_stock(target_part_pattern: str) -> int:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT stock_quantity FROM dim_spare_parts WHERE part_id LIKE ? LIMIT 1", (f"%{target_part_pattern}%",))
        row = cursor.fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def restock_all_spare_parts():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE dim_spare_parts SET stock_quantity = stock_quantity + 10")
        conn.commit()
        conn.close()
    except Exception:
        pass


def create_app_work_order(machine_id, error_code, summary):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        wo_id = f"WO-APP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        cursor.execute("""
            INSERT INTO fact_work_orders (
                work_order_id, line_id, error_code, created_at,
                priority, loto_status, technician_assigned, resolution_notes, order_status
            ) VALUES (?, ?, ?, ?, 'P1_URGENT', 'LOTO_REQUIRED', 'Nguyễn Doãn Hoàng (KTV Ca 1)', ?, 'OPEN')
        """, (wo_id, machine_id, error_code, now_ts, summary))
        conn.commit()
        conn.close()
        return wo_id
    except Exception:
        return f"WO-{datetime.now().strftime('%H%M%S')}"


def close_app_work_order(work_order_id, technician_name):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            UPDATE fact_work_orders
            SET order_status = 'CLOSED', loto_status = 'RESTORED',
                closed_at = ?, technician_assigned = ?
            WHERE work_order_id = ? OR order_status = 'OPEN'
        """, (now_ts, technician_name, work_order_id))
        conn.commit()
        conn.close()
    except Exception:
        pass


def record_downtime_event(machine_id, error_code, root_cause, duration_mins=15.0):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO fact_downtime_events (
                line_id, timestamp, shift_id, error_code, downtime_duration_minutes, impact_units_lost
            ) VALUES (?, ?, 'Shift 1', ?, ?, ?)
        """, (machine_id, now_ts, error_code, duration_mins, int(duration_mins * 400)))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ==============================================================================
# KHỞI TẠO STATE AN TOÀN
# ==============================================================================
if "shift_log" not in st.session_state:
    st.session_state["shift_log"] = []

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

if "derate_seconds_count" not in st.session_state:
    st.session_state["derate_seconds_count"] = 0

sim: StochasticPackagingLineSimulator = st.session_state["sim"]
detector: DegradationDetector = st.session_state["detector"]

fault_mode_now = getattr(sim, "fault_mode", "CUTTER_WEAR")
if len(st.session_state["shift_log"]) == 0:
    append_shift_log(f"{datetime.now().strftime('%H:%M:%S')} - Trạm HMI sẵn sàng. Dây chuyền tiềm ẩn: {fault_mode_now}")


def advance_simulation_step(num_steps: int = 1):
    for _ in range(num_steps):
        frame = sim.step()
        st.session_state["latest_frame"] = frame

        if frame["actual_speed_cph"] == 18000:
            st.session_state["derate_seconds_count"] += 1

        assessment = detector.ingest_frame("LINE_01", {
            "air_temp": frame["ambient_temp_c"],
            "process_temp": frame["ultrasonic_temp_c"],
            "rot_speed": frame["rot_speed_rpm"],
            "torque": frame["tension_torque_nm"],
            "tool_wear": frame["cutting_knife_wear_min"],
            "p_mech": frame["p_mech_kw"],
            "delta_t": frame["delta_t"],
        })
        st.session_state["assessment"] = assessment

        current_f = frame.get("fault_mode", getattr(sim, "fault_mode", "CUTTER_WEAR"))

        # KHI GẶP AMBER
        if (assessment.state == DegradationState.AMBER or frame["actual_speed_cph"] == 18000) and st.session_state["active_sap_slip"] is None:
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
                reason_txt = f"Dao cắt màng mòn tiệm cận ngưỡng: {frame['cutting_knife_wear_min']}m"

            execute_line_derate("LINE_01", 18000, reason_txt)

            sap_res = reserve_sap_spare_part("LINE_01", part_type)
            st.session_state["active_sap_slip"] = sap_res.get("requisition_slip")
            shelf = st.session_state["active_sap_slip"].get("shelf_location") if st.session_state["active_sap_slip"] else "Kho chính"

            wo_id = create_app_work_order("LINE_01", err_code, f"[COPILOT INTERVENTION]: {reason_txt}. Lấy phụ tùng tại {shelf}.")
            st.session_state["current_wo_id"] = wo_id

            roi_engine.compute_intervention_roi("LINE_01", "AMBER_AUTONOMOUS_INTERVENTION", wo_id)

            append_shift_log(
                f"{datetime.now().strftime('%H:%M:%S')} - ⚠️ CẢNH BÁO AMBER ({err_code}): Copilot hạ tốc độ 18k cph, tạo phiếu {wo_id}, xuất kho tại {shelf}."
            )

        # KHI GẶP RED: GHI DOWNTIME THẬT VÀ GHI LOG AN TOÀN
        if assessment.state == DegradationState.RED or frame["is_failure"] == 1:
            err = "E-204" if current_f == "CUTTER_WEAR" else ("E-105" if current_f == "CHILLER_OVERHEAT" else "E-302")
            record_downtime_event("LINE_01", err, f"Sập máy khẩn cấp: {', '.join(assessment.drift_reasons) if assessment.drift_reasons else 'Chạm ngưỡng tới hạn vật lý'}", duration_mins=30.0)
            append_shift_log(
                f"{datetime.now().strftime('%H:%M:%S')} - 🛑 SẬP MÁY RED ({err}): Ghi nhận 30 phút dừng máy vào fact_downtime_events!"
            )


# Khởi tạo frame ban đầu nếu chưa có
if "latest_frame" not in st.session_state:
    st.session_state["latest_frame"] = sim.step()

if "assessment" not in st.session_state:
    st.session_state["assessment"] = detector.evaluate_machine("LINE_01")

latest_frame = st.session_state["latest_frame"]
assessment = st.session_state["assessment"]
current_speed = plc_bridge.read_holding_register("LINE_01", PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED) or 24000
is_interlocked = (plc_bridge.read_holding_register("LINE_01", PLCHoldingRegisters.REG_SAFETY_INTERLOCK) == 1)

# Header
st.markdown("### 🏭 NESTLÉ ĐỒNG NAI — PACKAGING COPILOT HMI")

current_fault = latest_frame.get("fault_mode", getattr(sim, "fault_mode", "CUTTER_WEAR"))
part_key = "CUT" if current_fault == "CUTTER_WEAR" else ("JAW" if current_fault == "CHILLER_OVERHEAT" else "BELT")
current_warehouse_stock = get_part_stock(part_key)

st.caption(f"Trạm Tác Nghiệp Kỹ Thuật Viên Ca | LINE_01 | Trục trặc tiềm ẩn ca này: **{current_fault}** | Tồn kho phụ tùng: **{current_warehouse_stock} bộ**")

# TRẠNG THÁI DÂY CHUYỀN
is_red_state = is_interlocked or assessment.state == DegradationState.RED or latest_frame.get("is_failure") == 1
is_amber_state = (current_speed <= 18000 or assessment.state == DegradationState.AMBER) and not is_red_state

if is_red_state:
    badge_html = '<span class="badge-red">🔴 SẬP MÁY / INTERLOCK KHÓA</span>'
elif is_amber_state:
    badge_html = '<span class="badge-amber">🟡 CHẠY CẦM CHỪNG (LIMP-HOME 18.000 CPH)</span>'
else:
    badge_html = '<span class="badge-green">🟢 CHẠY ĐỊNH MỨC (24.000 CPH)</span>'

st.markdown(f"**Tình trạng Dây chuyền:** {badge_html} &nbsp;&nbsp;|&nbsp;&nbsp; Điểm suy thoái AI: **{assessment.degradation_score}%**", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# 1. Đồng Hồ Đo Telemetry
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric(label="Tốc Độ Đóng Gói (PLC)", value=f"{current_speed:,} cph")
with c2:
    wear_m = latest_frame["cutting_knife_wear_min"]
    st.metric(label="Độ Mòn Dao Cắt", value=f"{wear_m:.1f} m")
with c3:
    st.metric(label="Công Suất Cơ P_mech", value=f"{latest_frame['p_mech_kw']:.2f} kW")
with c4:
    temp_c = latest_frame["ultrasonic_temp_c"]
    st.metric(
        label="Nhiệt Độ Sonotrode", 
        value=f"{temp_c:.1f} °C", 
        delta="An toàn <=40°C" if temp_c <= 40 else "QUÁ NHIỆT (>40°C)",
        delta_color="normal" if temp_c <= 40 else "inverse"
    )

st.progress(min(wear_m / 140.0, 1.0))
st.caption(f"Thanh đo mài mòn dao: **{wear_m:.1f}m / 140.0m**")

st.markdown("---")

# 2. Điều Khiển Vận Hành
st.markdown("##### 🎛️ Bảng Điều Khiển Vận Hành Dây Chuyền")
btn1, btn2, btn3, btn4 = st.columns([1, 1, 1, 1])

with btn1:
    if st.button("▶ Bước 1 Giây Vận Hành"):
        advance_simulation_step(1)
        st.rerun()

with btn2:
    if st.button("⏩ Bước 5 Giây (Tua Nhanh)"):
        advance_simulation_step(5)
        st.rerun()

with btn3:
    if st.button("🔄 Đổi Ca / Ngẫu Nhiên Mới"):
        sim.replace_part_and_reset()
        st.session_state["active_sap_slip"] = None
        st.session_state["derate_seconds_count"] = 0
        st.session_state["detector"] = DegradationDetector(window_size=15)
        st.session_state["latest_frame"] = sim.step()
        new_mode = getattr(st.session_state['sim'], 'fault_mode', 'CUTTER_WEAR')
        append_shift_log(f"{datetime.now().strftime('%H:%M:%S')} - Bắt đầu ca mới. Điểm yếu tiềm ẩn: {new_mode}")
        st.rerun()

with btn4:
    if st.button("📥 Nhập Kho SAP (+10 Bộ)"):
        restock_all_spare_parts()
        st.success("Đã nhập thêm +10 bộ phụ tùng vào kho SAP PM!")
        append_shift_log(f"{datetime.now().strftime('%H:%M:%S')} - KTV nhập kho khẩn cấp +10 bộ linh kiện SAP PM.")
        st.rerun()

# BẢNG TÍNH TOÁN KINH TẾ
if st.session_state["derate_seconds_count"] > 0:
    secs = st.session_state["derate_seconds_count"]
    speed_loss_vnd = int(secs * (6000 / 3600) * 8000)
    net_avoidance_vnd = max(0, 103500000 - speed_loss_vnd - 9600000)
    st.info(f"""
    ⏱️ **Theo dõi Chi phí Chạy Cầm Chừng (Limp-Home):** Đã chạy chậm trong **{secs} giây**. 
    - 📉 Tổn thất do giảm tốc (-6k cph): **-{speed_loss_vnd:,.0f} VNĐ** (chấp nhận được để cứu cuộn giấy).
    - 💎 **Giá trị bảo toàn ròng so với sập máy 30p:** **+{net_avoidance_vnd:,.0f} VNĐ**!
    """)

st.markdown("---")

# 3. Chỉ Dẫn Copilot & Phiếu SAP
col_left, col_right = st.columns([1, 1])

with col_left:
    st.markdown("##### 🤖 Trợ Lý Copilot Túc Trực Hiện Trường")
    if is_red_state:
        st.error(f"""
        **MÁY ĐÃ SẬP ĐỘT NGỘT (UNPLANNED DOWNTIME):**
        - Lý do: {', '.join(assessment.drift_reasons) if assessment.drift_reasons else 'Vượt giới hạn cơ nhiệt tới hạn'}
        - Đã tự động ghi nhận 30 phút dừng máy vào bảng `fact_downtime_events`.
        - Bắt buộc kiểm tra LOTO trước khi thay thế.
        """)
    elif is_amber_state:
        st.warning(f"""
        **CẢNH BÁO SỚM (LIMP-HOME HOẠT ĐỘNG):**
        - Dây chuyền đang chạy giảm tải **18.000 cph** để chờ Kỹ thuật viên.
        - **Work Order kích hoạt:** `{st.session_state.get('current_wo_id')}` trong Database.
        - **Khuyến nghị KTV:** Khẩn trương lấy phụ tùng và ấn 'Dừng máy chủ động' trước khi thông số chạm ngưỡng đỏ RED!
        """)
    else:
        st.success("**DÂY CHUYỀN HOẠT ĐỘNG ỔN ĐỊNH:** Tốc độ 24.000 cph định mức.")

with col_right:
    st.markdown("##### 📦 Phiếu Lĩnh Phụ Tùng SAP PM Tương Ứng")
    slip = st.session_state["active_sap_slip"]
    if slip and is_amber_state:
        st.markdown(f"""
        <div style="background-color: #1A2230; border: 1px dashed #D9822B; border-radius: 8px; padding: 14px;">
            <b style="color: #ECC94B;">📋 MÃ PHIẾU SAP: {slip.get('requisition_id')}</b>
            <div style="font-size: 13px; margin-top: 6px; line-height: 1.6;">
                <div>Linh kiện: <b>{slip.get('part_name')}</b></div>
                <div>Mã số SAP: <code>{slip.get('sap_material_code')}</code></div>
                <div>Vị trí lấy hàng: <b style="color: #48BB78; font-size: 15px;">{slip.get('shelf_location')}</b></div>
                <div>Tồn kho: <b>{current_warehouse_stock} bộ</b> | Đơn giá: <b>{slip.get('unit_cost_vnd'):,.0f} VNĐ</b></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("Chưa có phiếu xuất kho. Khi phát hiện suy thoái, Copilot sẽ tự động điều phối đúng loại linh kiện.")

st.markdown("---")

# 4. Thao Tác Kỹ Thuật Viên: Dừng Chủ Động & LOTO
st.markdown("##### 🛠️ Trung Tâm Thao Tác Kỹ Thuật Viên (Dừng Chủ Động & Mở Khóa LOTO)")
act1, act2 = st.columns([1, 1])

with act1:
    st.markdown("**1. Dừng Máy Chủ Động (Planned Maintenance Stop)**")
    st.caption("KTV dừng máy có kế hoạch (ghi nhận vào fact_downtime_events chỉ mất 3 phút thay vì 30 phút).")
    if st.button("🛑 DỪNG MÁY CHỦ ĐỘNG ĐỂ BẢO TRÌ"):
        plc_bridge.write_holding_register("LINE_01", PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED, 0)
        plc_bridge.write_holding_register("LINE_01", PLCHoldingRegisters.REG_SAFETY_INTERLOCK, 1)
        record_downtime_event("LINE_01", "PLANNED_PM", "KTV dừng máy chủ động thay thế phụ tùng theo cảnh báo Copilot", duration_mins=3.0)
        append_shift_log(f"{datetime.now().strftime('%H:%M:%S')} - KTV dừng máy chủ động (Ghi nhận 3 phút planned downtime).")
        st.success("Máy đã dừng an toàn!")
        st.rerun()

with act2:
    st.markdown("**2. Xác Nhận Đã Thay Linh Kiện & Mở Khóa LOTO**")
    t_sonotrode = latest_frame["ultrasonic_temp_c"]
    safe_loto = (t_sonotrode <= 40.0)

    if current_warehouse_stock <= 0:
        st.error(f"🚨 **HẾT HÀNG TRONG KHO SAP (Tồn kho = {current_warehouse_stock})!** Bạn không thể thay linh kiện vì không có đồ mới trong kho. Hãy ấn nút '📥 Nhập Kho SAP' ở trên!")

    with st.form("loto_stochastic_form"):
        ktv_name = st.text_input("Kỹ thuật viên thực hiện", value="Nguyễn Doãn Hoàng (KTV Ca 1)")
        padlock = st.text_input("Mã khóa LOTO", value="PADLOCK-BH2-094")
        confirm_ok = st.checkbox("Xác nhận: Đã hoàn tất thay thế linh kiện mới theo chỉ dẫn Copilot.")

        btn_unlock = st.form_submit_button("🔓 XÁC NHẬN HOÀN TẤT & KHỞI ĐỘNG LẠI MÁY")

        if btn_unlock:
            if current_warehouse_stock <= 0:
                st.error("❌ TỪ CHỐI THỰC THI: Kho SAP không còn phụ tùng thay thế! Không thể hoàn tất bảo trì khi không có linh kiện mới!")
            elif not confirm_ok:
                st.error("CẢNH BÁO: Phải xác nhận đã hoàn tất thay thế linh kiện!")
            elif not safe_loto:
                st.error(f"TỪ CHỐI AN TOÀN EHS: Nhiệt độ đầu hàn {t_sonotrode}°C > 40°C! Nguy cơ bỏng nhiệt. Chờ Chiller giải nhiệt!")
            else:
                sim.replace_part_and_reset()
                approve_loto_unlock("LINE_01", ktv_name, padlock)

                close_app_work_order(st.session_state.get("current_wo_id"), ktv_name)

                st.session_state["active_sap_slip"] = None
                st.session_state["derate_seconds_count"] = 0
                st.session_state["detector"] = DegradationDetector(window_size=15)
                append_shift_log(
                    f"{datetime.now().strftime('%H:%M:%S')} - 🎉 KTV {ktv_name} hoàn tất bảo trì. Đóng phiếu Work Order. Mở khóa LOTO -> Máy trở lại 24.000 cph!"
                )
                st.success("🎉 BẢO TRÌ THÀNH CÔNG! Đã đóng phiếu Work Order. Dây chuyền trở lại định mức 24.000 cph màu XANH!")
                st.rerun()

st.markdown("---")

# 5. Nhật Ký Ca Trực
with st.expander("📜 Nhật Ký Sự Cố & Thao Tác Ca Trực (Shift Audit Trail)", expanded=True):
    logs_to_show = st.session_state.get("shift_log", [])
    for item in reversed(logs_to_show[-8:]):
        st.markdown(f"- `{item}`")