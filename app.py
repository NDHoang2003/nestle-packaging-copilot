#!/usr/bin/env python3
"""
================================================================================
NESTLE DONG NAI FACTORY - INDUSTRIAL PACKAGING DIGITAL TWIN
Module: Industrial Operations Center Dashboard (Phase 5 - Enterprise Edition)
Fixes:
  - Fixed SQL OperationalError at line 81 by using Canonical Machine Mapping.
  - Accurate Line Filtering: Selecting LINE_03 displays only LINE_03.
  - Full-Page Auto-Refresh: Real-time Incident Alert Banner & Live Work Order Feed.
  - Built-in Demo Data Reset Tool.
Author: Nguyen Doan Hoang (Digital Technical Specialist Candidate)
Reviewed by: Lead Industrial Data & AI Engineer
================================================================================
"""

import os
import time
import sqlite3
import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import datetime

st.set_page_config(
    page_title="Nestlé Đồng Nai — Industrial Packaging Operations Center",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "packaging_factory.db"

import factory_tools
from agent_core import PackagingCopilotAgent

# Bản đồ định danh 3 dây chuyền chuẩn của Nhà máy Nestlé Đồng Nai (SSOT README.md)
CANONICAL_MACHINES = {
    "LINE_01": {
        "name": "Tetra Pak A3/Speed 115ml",
        "product": "Milo 115ml",
        "rated_cph": 24000
    },
    "LINE_02": {
        "name": "Tetra Pak TBA/19 180ml",
        "product": "Milo 180ml",
        "rated_cph": 7500
    },
    "LINE_03": {
        "name": "SIG Combibloc CFA 312",
        "product": "Sữa Vô trùng 250ml",
        "rated_cph": 12000
    }
}


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def load_all_machines_status(selected_line: str = "ALL") -> list:
    """
    Tải trạng thái thời gian thực độc lập, an toàn 100% không lo lỗi thiếu cột SQL.
    Hỗ trợ lọc chính xác theo từng Line hoặc hiển thị toàn bộ (ALL).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Truy vấn trực tiếp bảng đệm thời gian thực
    cursor.execute("SELECT * FROM realtime_edge_buffer;")
    buffer_records = {dict(r)["line_id"]: dict(r) for r in cursor.fetchall()}
    conn.close()

    lines_to_render = [selected_line] if selected_line != "ALL" else ["LINE_01", "LINE_02", "LINE_03"]

    results = []
    for line_id in lines_to_render:
        meta = CANONICAL_MACHINES.get(line_id, {"name": line_id, "rated_cph": 12000, "product": "Standard"})

        if line_id in buffer_records:
            b = buffer_records[line_id]
            results.append({
                "line_id": line_id,
                "machine_name": meta["name"],
                "product": meta["product"],
                "rated_cph": meta["rated_cph"],
                "record_id": b.get("record_id", 0),
                "last_updated": b.get("last_updated", "Vừa cập nhật"),
                "temp_sonotrode_c": b.get("temp_sonotrode_c", 35.0),
                "speed_servo_rpm": b.get("speed_servo_rpm", 0.0),
                "tension_torque_nm": b.get("tension_torque_nm", 0.0),
                "cutting_knife_wear_min": b.get("cutting_knife_wear_min", 0),
                "delta_t": b.get("delta_t", 0.0),
                "dt_dt": b.get("dt_dt", 0.0),
                "p_mech_kw": b.get("p_mech_kw", 0.0),
                "error_code": b.get("error_code", "NORMAL"),
                "is_failure": b.get("is_failure", 0),
                "alert_severity": b.get("alert_severity", "NORMAL"),
                "interlock_latched": b.get("interlock_latched", 0),
                "machine_state": b.get("machine_state", "RUNNING"),
                "active_work_order_id": b.get("active_work_order_id")
            })
        else:
            # Dây chuyền chưa chạy mô phỏng -> Hiển thị trạng thái chờ STANDBY
            results.append({
                "line_id": line_id,
                "machine_name": meta["name"],
                "product": meta["product"],
                "rated_cph": meta["rated_cph"],
                "record_id": 0,
                "last_updated": "Chưa có luồng dữ liệu",
                "temp_sonotrode_c": 35.0,
                "speed_servo_rpm": 0.0,
                "tension_torque_nm": 0.0,
                "cutting_knife_wear_min": 0,
                "delta_t": 0.0,
                "dt_dt": 0.0,
                "p_mech_kw": 0.0,
                "error_code": "NORMAL",
                "is_failure": 0,
                "alert_severity": "NORMAL",
                "interlock_latched": 0,
                "machine_state": "STANDBY",
                "active_work_order_id": None
            })

    return results


def load_open_work_orders(selected_line: str = "ALL") -> list:
    conn = get_db_connection()
    cursor = conn.cursor()

    where_sql = "WHERE w.order_status = 'OPEN'"
    params = []
    if selected_line != "ALL":
        where_sql += " AND w.line_id = ?"
        params.append(selected_line)

    query = f"""
        SELECT w.work_order_id, w.event_id, w.line_id, w.error_code, w.created_at,
               w.priority, w.loto_status, w.technician_assigned, w.resolution_notes, w.order_status,
               d.impact_units_lost, d.downtime_duration_minutes
        FROM fact_work_orders w
        LEFT JOIN fact_downtime_events d ON w.event_id = d.event_id
        {where_sql}
        ORDER BY w.created_at DESC
        LIMIT 15;
    """
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def reset_demo_work_orders():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE fact_work_orders 
        SET order_status = 'CLOSED', loto_status = 'RESTORED' 
        WHERE work_order_id LIKE 'WO-AUTO-%';
    """)
    cursor.execute("""
        UPDATE realtime_edge_buffer
        SET interlock_latched = 0, machine_state = 'RUNNING', 
            error_code = 'NORMAL', alert_severity = 'NORMAL', is_failure = 0,
            active_work_order_id = NULL;
    """)
    conn.commit()
    conn.close()


# ==============================================================================
# CSS GIAO DIỆN CÔNG NGHIỆP
# ==============================================================================
st.markdown("""
<style>
    .machine-running {
        background-color: #0E3A24;
        border-radius: 8px;
        padding: 16px;
        border-left: 6px solid #28A745;
        color: white;
    }
    .machine-tripped {
        background-color: #5A0E17;
        border-radius: 8px;
        padding: 16px;
        border-left: 6px solid #DC3545;
        color: white;
        box-shadow: 0 0 15px rgba(220, 53, 69, 0.5);
    }
    .machine-standby {
        background-color: #1F242D;
        border-radius: 8px;
        padding: 16px;
        border-left: 6px solid #6C757D;
        color: #CCC;
    }
    .incident-ticker {
        background: #DC3545;
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 16px;
        margin-bottom: 15px;
        animation: pulse 1s infinite alternate;
    }
    @keyframes pulse {
        0% { opacity: 0.85; }
        100% { opacity: 1.0; }
    }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# SIDEBAR
# ==============================================================================
with st.sidebar:
    # Logo Nestlé dạng HTML/CSS thuần (100% offline-safe)
    st.markdown("""
    <div style="background-color: #004578; padding: 15px; border-radius: 8px; text-align: center; margin-bottom: 15px;">
        <h2 style="color: white; margin: 0; font-family: sans-serif; letter-spacing: 2px;">Nestlé</h2>
        <p style="color: #A6D2FF; margin: 0; font-size: 12px;">ĐỒNG NAI FACTORY (BIÊN HÒA 2)</p>
    </div>
    """, unsafe_allow_html=True)

    st.header("⚙️ Bảng Điều Khiển")
    selected_line = st.selectbox(
        "Chọn Dây chuyền Giám sát",
        ["ALL", "LINE_01", "LINE_02", "LINE_03"],
        index=0
    )

    st.divider()
    auto_refresh = st.toggle("Kích hoạt Auto-refresh (Live Stream)", value=True)
    refresh_rate = st.slider("Chu kỳ làm mới (giây)", 1, 5, 2)

    st.divider()
    st.subheader("🛠️ Công cụ Demo Thực chiến")
    if st.button("🧹 Reset / Dọn dẹp Work Orders Mở"):
        reset_demo_work_orders()
        st.success("Đã dọn dẹp các Work Order cũ. Sẵn sàng đón sự cố mới!")
        time.sleep(1.0)
        st.rerun()

    st.divider()
    st.caption(
        "**Ứng viên:** Nguyễn Doãn Hoàng (B.E. HCMUT)\n\n"
        "**Vị trí:** Digital Technical Specialist\n\n"
        "**Tuyến báo cáo:** Manufacturing Excellence Manager"
    )

st.title("🏭 Nestlé Packaging Operations Center — Digital Twin")
st.caption("Hệ thống Giám sát Cảm biến Thời gian thực, Chốt chặn An toàn LOTO & Điều phối Tự trị")


# ==============================================================================
# PHẦN 1: LIVE OPERATIONS CENTER (FRAGMENT AUTO-REFRESH)
# ==============================================================================
@st.fragment(run_every=f"{refresh_rate}s" if auto_refresh else None)
def render_live_operations_center():
    machines = load_all_machines_status(selected_line)
    open_wos = load_open_work_orders(selected_line)

    # 1. CÒI BÁO ĐỘNG SỰ CỐ KHẨN CẤP (NẾU CÓ DÂY CHUYỀN BỊ TRIPPED)
    tripped_machines = [m for m in machines if m["interlock_latched"] == 1 or m["machine_state"] == "TRIPPED"]
    if tripped_machines:
        for tm in tripped_machines:
            st.markdown(f"""
            <div class="incident-ticker">
                🚨 KHÓA LIÊN ĐỘNG AN TOÀN ĐANG KÍCH HOẠT: Dây chuyền {tm['line_id']} dừng khẩn cấp! 
                Mã lỗi: {tm['error_code']} | Frame #{tm['record_id']} | Đang phối hợp AI chẩn đoán & điều phối bảo trì.
            </div>
            """, unsafe_allow_html=True)

    # 2. THẺ TRẠNG THÁI CÁC DÂY CHUYỀN ĐÓNG GÓI
    st.subheader("📡 Nhịp tim Cảm biến Thời gian thực (Shopfloor Telemetry)")
    cols = st.columns(len(machines))

    for idx, m in enumerate(machines):
        line = m["line_id"]
        name = m["machine_name"]
        prod = m["product"]
        state = m["machine_state"]
        err = m["error_code"]
        t_sono = m["temp_sonotrode_c"]
        delta_t = m["delta_t"]
        p_kw = m["p_mech_kw"]
        knife = m["cutting_knife_wear_min"]
        ts = m["last_updated"]

        if state == "TRIPPED" or m["interlock_latched"] == 1:
            card_class = "machine-tripped"
            status_text = "🚨 DỪNG KHẨN CẤP (TRIPPED)"
        elif state == "RUNNING":
            card_class = "machine-running"
            status_text = "🟢 ĐANG SẢN XUẤT (RUNNING)"
        else:
            card_class = "machine-standby"
            status_text = "⚪ CHỜ DỮ LIỆU (STANDBY)"

        with cols[idx]:
            st.markdown(f"""
            <div class="{card_class}">
                <h4 style="margin:0;">{line}</h4>
                <p style="margin:0; font-size:12px; color:#DDD;">{name} ({prod})</p>
                <hr style="margin:8px 0; border-color:rgba(255,255,255,0.2);">
                <p style="margin:0; font-size:14px; font-weight:bold;">{status_text}</p>
                <p style="margin:4px 0 0 0; font-size:13px;">Mã cảnh báo: <b>{err}</b></p>
                <div style="font-size:12px; margin-top:8px; line-height:1.6;">
                    <div>🌡️ T_Sonotrode: <b>{t_sono:.1f}°C</b> (ΔT: {delta_t:.1f}°C)</div>
                    <div>⚡ Công suất P_mech: <b>{p_kw:.2f} kW</b></div>
                    <div>🔪 Dao cắt: <b>{knife}m</b> / 200m</div>
                    <div style="font-size:10px; color:#CCC; margin-top:6px;">🕒 Cập nhật: {ts}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.write("")

    # 3. LIVE WORK ORDER FEED
    st.subheader("🛡️ Phiếu Bảo Trì Mở & Chốt Chặn LOTO (Cập nhật Trực tiếp)")

    col_wos, col_loto = st.columns([3, 2])

    with col_wos:
        st.markdown(f"**Danh sách Sự cố Cần Can thiệp ({len(open_wos)} phiếu đang mở):**")
        if not open_wos:
            st.success("Tất cả các dây chuyền đang vận hành ổn định. Không có phiếu sự cố tồn đọng!")
        else:
            for wo in open_wos:
                is_auto = str(wo["work_order_id"]).startswith("WO-AUTO-")
                badge = "⚡ [AI TỰ TRỊ TẠO]" if is_auto else "📝 [THỦ CÔNG]"

                with st.expander(f"🔴 {badge} {wo['work_order_id']} — {wo['line_id']} (Lỗi: {wo['error_code']})", expanded=is_auto):
                    st.write(f"**Thời gian phát sinh:** {wo['created_at']}")
                    st.write(f"**Mức độ ưu tiên:** `{wo['priority']}` | **LOTO:** `{wo['loto_status']}`")
                    st.write(f"**Thất thoát ước tính:** {wo['impact_units_lost']:,} hộp Milo ({wo['downtime_duration_minutes']} phút)")
                    st.info(f"**Chẩn đoán Nguyên nhân Gốc rễ (RCA):**\n{wo['resolution_notes']}")

    with col_loto:
        st.markdown("**Form Nghiệm Thu & Kiểm Định An Toàn LOTO:**")
        with st.form(key="loto_quick_form"):
            wo_options = [w["work_order_id"] for w in open_wos] if open_wos else ["Không có phiếu cần xử lý"]
            target_wo = st.selectbox("Chọn phiếu bảo trì để giải tỏa", wo_options)

            temp_check = st.number_input("Nhiệt độ Sonotrode đo thực tế trước khi tháo khóa (°C)", value=34.5, step=0.5)
            loto_check = st.checkbox("Đã cô lập nguồn điện & hoàn tất quy trình gắn khóa thẻ LOTO", value=True)
            eng_notes = st.text_input("Ghi chú xử lý kỹ thuật", value="Đã thay thế linh kiện, vệ sinh ngàm và cân chỉnh khe hở.")

            btn_verify = st.form_submit_button("XÁC NHẬN LOTO & ĐÓNG PHIẾU")

            if btn_verify:
                if target_wo == "Không có phiếu cần xử lý":
                    st.error("Không có phiếu bảo trì nào được chọn.")
                else:
                    gate_result = factory_tools.verify_loto_and_update_work_order(
                        work_order_id=target_wo,
                        current_temp_sonotrode_c=temp_check,
                        loto_confirmed=loto_check,
                        resolution_notes=eng_notes,
                        target_action="CLOSE"
                    )
                    if gate_result["status"] == "SUCCESS":
                        st.success(f"✅ {gate_result['message']}")
                        time.sleep(1.0)
                        st.rerun()
                    else:
                        st.error(f"🚨 {gate_result['message']}")
                        st.warning(f"**Yêu cầu an toàn bắt buộc:** {gate_result.get('required_action')}")


render_live_operations_center()

st.divider()

# ==============================================================================
# PHẦN 2: CHỈ SỐ ĐỘ TIN CẬY TPM & BIỂU ĐỒ PARETO 80/20
# ==============================================================================
st.subheader("📊 Phân Tích Độ Tin Cậy Thiết Bị (TPM Reliability & Pareto Loss)")

filter_id = None if selected_line == "ALL" else selected_line
tpm = factory_tools.calculate_line_reliability_metrics(line_id=filter_id)

kp1, kp2, kp3, kp4 = st.columns(4)
kp1.metric("Tính sẵn sàng (Availability)", f"{tpm['availability_rate_pct']}%", delta=f"{tpm['failure_count']} lần dừng")
kp2.metric("Thời gian sửa TB (MTTR)", f"{tpm['mttr_minutes']} phút", delta="Target < 12m", delta_color="inverse")
kp3.metric("Thời gian chạy ổn định (MTBF)", f"{tpm['mtbf_minutes']} phút", delta="Target > 25m")
kp4.metric("Sản lượng thất thoát", f"{tpm['total_units_lost']:,} hộp", delta="Milo / Sữa", delta_color="inverse")

pareto_records = factory_tools.get_pareto_downtime_analysis(line_id=filter_id)
if pareto_records:
    df_p = pd.DataFrame(pareto_records)
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Biểu đồ Pareto: Sản lượng Thất thoát theo Mã Lỗi (Lost Units)**")
        st.bar_chart(data=df_p, x="error_code", y="total_lost_units", color="#0078D4")
    with c2:
        st.markdown("**Phân tích Nhóm Trọng điểm (Vital Few 80/20)**")
        st.dataframe(
            df_p[["error_code", "failure_type", "total_lost_units", "lost_share_pct", "pareto_class"]],
            column_config={
                "error_code": "Mã Lỗi",
                "failure_type": "Dạng Sự Cố",
                "total_lost_units": st.column_config.NumberColumn("Sản Lượng Mất", format="%d"),
                "lost_share_pct": st.column_config.NumberColumn("Tỷ Trọng (%)", format="%.1f%%"),
                "pareto_class": "Phân Loại"
            },
            hide_index=True,
            use_container_width=True
        )

st.divider()

# ==============================================================================
# PHẦN 3: KHUNG CHAT COPILOT TƯƠNG TÁC (GEMINI AFC COPILOT)
# ==============================================================================
st.subheader("🧠 Trò chuyện Tương tác cùng Nestlé Packaging Copilot")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        {"role": "assistant", "content": "Xin chào! Tôi là Trợ lý AI Độ tin cậy Thiết bị tại Nhà máy Nestlé Đồng Nai. Tôi có thể hỗ trợ bạn tra cứu MTTR/MTBF, phân tích nguyên nhân sự cố Pareto hoặc kiểm tra an toàn nhiệt LOTO. Bạn cần tôi hỗ trợ điều gì?"}
    ]

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt_user := st.chat_input("Nhập câu hỏi kỹ thuật, ví dụ: 'Phân tích Pareto cho LINE_01' hoặc 'Chỉ số MTTR của ca này?'..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt_user})
    with st.chat_message("user"):
        st.markdown(prompt_user)

    with st.chat_message("assistant"):
        with st.spinner("Copilot đang truy vấn Database và tính toán chỉ số TPM..."):
            agent = PackagingCopilotAgent()
            copilot_reply = agent.chat(prompt_user)
            st.markdown(copilot_reply)
            st.session_state.chat_history.append({"role": "assistant", "content": copilot_reply})