"""
app.py
------
Nestle Dong Nai - Maintenance Technician Copilot HMI Console.
Pure Stochastic Physical Simulation with Live SCADA Historian Recording.
"""

import time
import streamlit as st
from datetime import datetime

from simulate_line import line_simulator, StochasticPackagingLineSimulator
from degradation_engine import DegradationDetector, DegradationState
from industrial_bridge import plc_bridge, PLCHoldingRegisters
from factory_tools import (
    execute_line_derate,
    reserve_sap_spare_part,
    check_loto_thermal_gate,
    approve_loto_unlock
)

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

if "sim" not in st.session_state:
    st.session_state["sim"] = StochasticPackagingLineSimulator(machine_id="LINE_01")

if "detector" not in st.session_state:
    st.session_state["detector"] = DegradationDetector(window_size=15)

if "active_sap_slip" not in st.session_state:
    st.session_state["active_sap_slip"] = None

if "shift_log" not in st.session_state:
    st.session_state["shift_log"] = [
        f"{datetime.now().strftime('%H:%M:%S')} - Dây chuyền LINE_01 sẵn sàng chạy ngẫu nhiên thực tế."
    ]

sim: StochasticPackagingLineSimulator = st.session_state["sim"]
detector: DegradationDetector = st.session_state["detector"]


def trigger_simulation_tick(num_ticks: int = 1):
    for _ in range(num_ticks):
        frame = sim.step()
        st.session_state["latest_frame"] = frame
        
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

        # Khi Copilot phát hiện AMBER ngẫu nhiên từ dòng dữ liệu
        if assessment.state == DegradationState.AMBER and st.session_state["active_sap_slip"] is None:
            execute_line_derate("LINE_01", 18000, f"Phát hiện suy thoái ngẫu nhiên: {assessment.drift_reasons[0]}")
            sap_res = reserve_sap_spare_part("LINE_01", "CUTTER_WEAR")
            st.session_state["active_sap_slip"] = sap_res.get("requisition_slip")
            st.session_state["shift_log"].append(
                f"{datetime.now().strftime('%H:%M:%S')} - ⚠️ CẢNH BÁO AMBER: Copilot hạ tốc độ 18k cph & xuất phiếu dao cắt Kệ B2-Ô 04."
            )

        if assessment.state == DegradationState.RED:
            st.session_state["shift_log"].append(
                f"{datetime.now().strftime('%H:%M:%S')} - 🛑 SẬP MÁY RED: Dao cắt chạm giới hạn gãy hoặc mất lực căng!"
            )


if "latest_frame" not in st.session_state:
    st.session_state["latest_frame"] = sim.step()
    st.session_state["assessment"] = detector.evaluate_machine("LINE_01")

latest_frame = st.session_state["latest_frame"]
assessment = st.session_state["assessment"]
current_speed = plc_bridge.read_holding_register("LINE_01", PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED) or 24000
is_interlocked = (plc_bridge.read_holding_register("LINE_01", PLCHoldingRegisters.REG_SAFETY_INTERLOCK) == 1)

# Header
st.markdown("### 🏭 NESTLÉ ĐỒNG NAI — PACKAGING COPILOT HMI")
st.caption("Bảng Điều Khiển Tác Nghiệp Kỹ Thuật Viên Ca | Chế Độ Mô Phỏng Vật Lý Ngẫu Nhiên (Stochastic)")

# Trạng thái
if is_interlocked or assessment.state == DegradationState.RED:
    badge_html = '<span class="badge-red">🔴 SẬP MÁY / INTERLOCK KHÓA</span>'
elif current_speed <= 18000 or assessment.state == DegradationState.AMBER:
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
    wear_m = latest_frame['cutting_knife_wear_min']
    st.metric(label="Độ Mòn Dao Cắt", value=f"{wear_m:.1f} m")
with c3:
    st.metric(label="Lực Căng Mô-men", value=f"{latest_frame['tension_torque_nm']} Nm")
with c4:
    temp_c = latest_frame['ultrasonic_temp_c']
    st.metric(label="Nhiệt Độ Sonotrode", value=f"{temp_c} °C", delta="An toàn <=40°C" if temp_c <= 40 else "Quá nhiệt", delta_color="normal" if temp_c <= 40 else "inverse")

st.progress(min(wear_m / 140.0, 1.0))
st.caption(f"Tiến trình mài mòn dao: **{wear_m:.1f}m / 140.0m** (Dữ liệu ghi liên tục vào fact_sensor_telemetry)")

st.markdown("---")

# 2. Điều Khiển Nhịp Vận Hành Ngẫu Nhiên
st.markdown("##### 🎛️ Vận Hành Dây Chuyền Thực Tế")
btn1, btn2, btn3 = st.columns([1, 1, 1])

with btn1:
    if st.button("▶ Bước 1 Giây Vận Hành"):
        trigger_simulation_tick(1)
        st.rerun()

with btn2:
    if st.button("⏩ Bước 5 Giây (Tua Nhanh Chu Trình)"):
        trigger_simulation_tick(5)
        st.rerun()

with btn3:
    if st.button("🔄 Reset Ca Mới (Lắp Dao Mới)"):
        sim.replace_knife_and_service()
        st.session_state["active_sap_slip"] = None
        st.session_state["shift_log"].append(f"{datetime.now().strftime('%H:%M:%S')} - Reset máy về trạng thái ban đầu.")
        st.rerun()

st.markdown("---")

# 3. Chỉ Dẫn Copilot & Phiếu SAP
col_left, col_right = st.columns([1, 1])

with col_left:
    st.markdown("##### 🤖 Trợ Lý Copilot Túc Trực Hiện Trường")
    if assessment.state == DegradationState.AMBER:
        st.warning(f"""
        **PHÁT HIỆN SUY THOÁI TIỆM TIẾN:**
        - Cảm biến ghi nhận: {assessment.drift_reasons[0] if assessment.drift_reasons else 'Dao mòn tiệm cận mốc cảnh báo.'}
        - **Hành động tự trị:** Đã hạ tốc độ PLC xuống 18.000 cph để bảo vệ cuộn màng Milo.
        - **Khuyến nghị KTV:** Nhận dao mới tại Kệ B2-Ô 04 và thực hiện dừng máy chủ động thay thế.
        """)
    elif assessment.state == DegradationState.RED:
        st.error(f"""
        **MÁY ĐÃ SẬP ĐỘT NGỘT (UNPLANNED DOWNTIME):**
        - Dao cắt đã chạm ngưỡng gãy mỏi cơ học (>140m).
        - Ghi nhận sự cố vào bảng `fact_downtime_events`.
        - Yêu cầu thực hiện quy trình LOTO ngay lập tức.
        """)
    else:
        st.success("**DÂY CHUYỀN HOẠT ĐỘNG HOÀN TOÀN BÌNH THƯỜNG:** Tốc độ 24.000 cph định mức.")

with col_right:
    st.markdown("##### 📦 Phiếu Lĩnh Phụ Tùng SAP PM Tự Động")
    slip = st.session_state["active_sap_slip"]
    if slip:
        st.markdown(f"""
        <div style="background-color: #1A2230; border: 1px dashed #D9822B; border-radius: 8px; padding: 14px;">
            <b style="color: #ECC94B;">📋 MÃ PHIẾU SAP: {slip.get('requisition_id')}</b>
            <div style="font-size: 13px; margin-top: 6px; line-height: 1.6;">
                <div>Linh kiện: <b>{slip.get('part_name')}</b></div>
                <div>Mã số SAP: <code>{slip.get('sap_material_code')}</code></div>
                <div>Vị trí lấy hàng: <b style="color: #48BB78; font-size: 15px;">{slip.get('shelf_location')}</b></div>
                <div>Tồn kho: <b>{slip.get('remaining_warehouse_stock')} bộ</b> | Đơn giá: <b>{slip.get('unit_cost_vnd'):,.0f} VNĐ</b></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info("Chưa có phiếu xuất kho. Khi dao mòn đến vùng AMBER, phiếu kho sẽ tự động xuất hiện.")

st.markdown("---")

# 4. Thao Tác Kỹ Thuật Viên: Dừng Chủ Động & LOTO
st.markdown("##### 🛠️ Trung Tâm Thao Tác Kỹ Thuật Viên (Dừng Chủ Động & Mở Khóa LOTO)")
act1, act2 = st.columns([1, 1])

with act1:
    st.markdown("**1. Dừng Máy Chủ Động (Planned Maintenance Stop)**")
    st.caption("KTV chủ động dừng máy để thay dao (chỉ mất 3 phút thay vì để máy sập mất 30 phút).")
    if st.button("🛑 DỪNG MÁY CHỦ ĐỘNG ĐỂ THAY DAO"):
        plc_bridge.write_holding_register("LINE_01", PLCHoldingRegisters.REG_CURRENT_ACTUAL_SPEED, 0)
        plc_bridge.write_holding_register("LINE_01", PLCHoldingRegisters.REG_SAFETY_INTERLOCK, 1)
        st.session_state["shift_log"].append(f"{datetime.now().strftime('%H:%M:%S')} - KTV dừng máy chủ động để thay dao dạng hộp.")
        st.success("Máy đã dừng an toàn!")
        st.rerun()

with act2:
    st.markdown("**2. Xác Nhận Đã Thay Dao & Mở Khóa LOTO**")
    t_sonotrode = latest_frame['ultrasonic_temp_c']
    safe_loto = (t_sonotrode <= 40.0)

    with st.form("loto_stochastic_form"):
        ktv_name = st.text_input("Kỹ thuật viên thực hiện", value="Nguyễn Doãn Hoàng (KTV Ca 1)")
        padlock = st.text_input("Mã khóa LOTO", value="PADLOCK-BH2-094")
        confirm_knife = st.checkbox("Đã rút dao cũ và lắp cụm dao mới từ Kệ B2-Ô 04 (Lực siết 35 Nm).")
        
        btn_unlock = st.form_submit_button("🔓 XÁC NHẬN HOÀN TẤT & KHỞI ĐỘNG LẠI MÁY")
        
        if btn_unlock:
            if not confirm_knife:
                st.error("CẢNH BÁO: Phải xác nhận đã lắp cụm dao mới!")
            elif not safe_loto:
                st.error(f"TỪ CHỐI AN TOÀN EHS: Nhiệt độ {t_sonotrode}°C > 40°C. Nguy cơ bỏng nhiệt!")
            else:
                sim.replace_knife_and_service()
                approve_loto_unlock("LINE_01", ktv_name, padlock)
                st.session_state["active_sap_slip"] = None
                st.session_state["shift_log"].append(
                    f"{datetime.now().strftime('%H:%M:%S')} - 🎉 KTV {ktv_name} hoàn tất thay dao. Mở khóa LOTO -> Máy trở lại 24.000 cph!"
                )
                st.success("🎉 THAY DAO THÀNH CÔNG! Dây chuyền trở lại định mức 24.000 cph màu XANH!")
                st.rerun()