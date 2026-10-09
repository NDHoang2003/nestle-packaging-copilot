#!/usr/bin/env python3
"""
================================================================================
NESTLE DONG NAI FACTORY - INDUSTRIAL PACKAGING DIGITAL TWIN
Module: Manufacturing Analytics Engine & LOTO Guardrails (Phase 3)
Capabilities: MTTR, MTBF, Pareto 80/20, SOP ChromaDB Retrieval, LOTO Safety Gate
Author: Nguyen Doan Hoang (Digital Technical Specialist Candidate)
Reviewed by: Lead Industrial Data & AI Engineer
================================================================================
"""

import os
import sys
import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (Nestle-Tools) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("FactoryTools")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "packaging_factory.db"
SOP_FILE = BASE_DIR / "data" / "SOP_Packaging_Troubleshooting.md"
CHROMA_DIR = BASE_DIR / "chroma_db"


def get_db_connection() -> sqlite3.Connection:
    """Tạo kết nối database an toàn có hỗ trợ Foreign Keys."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database không tồn tại tại {DB_PATH}! Hãy chạy setup_database.py trước.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# ==============================================================================
# TOOL 1: TÍNH TOÁN ĐỘ TIN CẬY THIẾT BỊ (MTTR & MTBF)
# ==============================================================================
def calculate_line_reliability_metrics(line_id: Optional[str] = None, shift_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Tính toán chỉ số TPM độ tin cậy thiết bị: MTTR (phút), MTBF (phút), Tần suất sự cố,
    Tổng downtime và Sản lượng thất thoát theo Dây chuyền và Ca sản xuất.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Xây dựng bộ lọc SQL động
    where_clauses_telemetry = []
    where_clauses_downtime = []
    params = []

    if line_id:
        where_clauses_telemetry.append("line_id = ?")
        where_clauses_downtime.append("line_id = ?")
        params.append(line_id)

    if shift_id:
        where_clauses_telemetry.append("shift_id = ?")
        where_clauses_downtime.append("shift_id = ?")
        params.append(shift_id)

    sql_where_tel = f"WHERE {' AND '.join(where_clauses_telemetry)}" if where_clauses_telemetry else ""
    sql_where_down = f"WHERE {' AND '.join(where_clauses_downtime)}" if where_clauses_downtime else ""

    # 1. Tổng thời gian quan sát (mỗi bản ghi telemetry tương đương 1 phút)
    query_total_time = f"SELECT COUNT(*) AS total_minutes FROM fact_sensor_telemetry {sql_where_tel};"
    cursor.execute(query_total_time, params)
    total_planned_minutes = cursor.fetchone()["total_minutes"] or 0

    # 2. Tổng thời gian dừng máy và số lần sự cố
    query_downtime = f"""
    SELECT 
        COUNT(event_id) AS failure_count,
        COALESCE(SUM(downtime_duration_minutes), 0.0) AS total_downtime_minutes,
        COALESCE(SUM(impact_units_lost), 0) AS total_units_lost
    FROM fact_downtime_events
    {sql_where_down};
    """
    cursor.execute(query_downtime, params)
    row = cursor.fetchone()

    failures = row["failure_count"]
    total_downtime = round(row["total_downtime_minutes"], 2)
    units_lost = row["total_units_lost"]

    conn.close()

    # Tính toán MTTR và MTBF
    operating_time = float(total_planned_minutes)  # Thời gian cảm biến hoạt động thực tế (Run Time)
    actual_planned_time = operating_time + total_downtime  # Tổng thời gian kế hoạch = Run Time + Downtime

    if failures > 0:
        mttr = round(total_downtime / failures, 2)
        mtbf = round(operating_time / failures, 2)
        availability_rate = round((operating_time / actual_planned_time) * 100, 2) if actual_planned_time > 0 else 0.0
    else:
        mttr = 0.0
        mtbf = operating_time
        availability_rate = 100.0

    return {
        "filter_applied": {"line_id": line_id or "ALL", "shift_id": shift_id or "ALL"},
        "planned_production_minutes": round(actual_planned_time, 2),
        "operating_time_minutes": round(operating_time, 2),
        "total_downtime_minutes": total_downtime,
        "failure_count": failures,
        "mttr_minutes": mttr,
        "mtbf_minutes": mtbf,
        "availability_rate_pct": availability_rate,
        "total_units_lost": units_lost
    }

# ==============================================================================
# TOOL 2: PHÂN TÍCH PARETO 80/20 DỪNG MÁY (KAIZEN / TPM)
# ==============================================================================
def get_pareto_downtime_analysis(line_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Phân tích nguyên nhân dừng máy Pareto 80/20 dựa trên sản lượng thất thoát (Impact Units Lost).
    Tự động tính phần trăm tích lũy (Cumulative Percentage) để khoanh vùng nhóm lỗi trọng điểm.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    param = [line_id] if line_id else []
    where_sql = "WHERE e.line_id = ?" if line_id else ""

    query = f"""
    SELECT 
        e.error_code,
        c.failure_type,
        COUNT(e.event_id) AS occurrences,
        ROUND(SUM(e.downtime_duration_minutes), 1) AS total_downtime_min,
        SUM(e.impact_units_lost) AS total_lost_units
    FROM fact_downtime_events e
    JOIN dim_error_catalog c ON e.error_code = c.error_code
    {where_sql}
    GROUP BY e.error_code, c.failure_type
    ORDER BY total_lost_units DESC;
    """
    cursor.execute(query, param)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    total_lost_overall = sum(r["total_lost_units"] for r in rows)
    if total_lost_overall == 0:
        return []

    cumulative_units = 0
    results = []

    for item in rows:
        cumulative_units += item["total_lost_units"]
        cum_pct = round((cumulative_units / total_lost_overall) * 100, 2)
        unit_pct = round((item["total_lost_units"] / total_lost_overall) * 100, 2)

        results.append({
            "error_code": item["error_code"],
            "failure_type": item["failure_type"],
            "occurrences": item["occurrences"],
            "total_downtime_min": item["total_downtime_min"],
            "total_lost_units": item["total_lost_units"],
            "lost_share_pct": unit_pct,
            "cumulative_share_pct": cum_pct,
            "pareto_class": "VITAL_FEW (Top 80%)" if cum_pct <= 85.0 or len(results) == 0 else "USEFUL_MANY"
        })

    return results


# ==============================================================================
# TOOL 3: SNAPSHOT CẢM BIẾN MỚI NHẤT CỦA DÂY CHUYỀN
# ==============================================================================
def get_recent_telemetry_snapshot(line_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Lấy dữ liệu cảm biến gần nhất của một dây chuyền để Copilot chẩn đoán bệnh."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    SELECT 
        record_id, timestamp, shift_id, line_id,
        temp_cleanroom_c, temp_sonotrode_c, speed_servo_rpm,
        tension_torque_nm, cutting_knife_wear_min, delta_t, dt_dt,
        p_mech_kw, heat_strain_index, error_code, alert_severity
    FROM fact_sensor_telemetry
    WHERE line_id = ?
    ORDER BY timestamp DESC
    LIMIT ?;
    """
    cursor.execute(query, (line_id, limit))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ==============================================================================
# TOOL 4: TRA CỨU QUY TRÌNH XỬ LÝ SỰ CỐ (SOP RETRIEVAL)
# ==============================================================================
def query_sop_knowledge_base(query_text: str, n_results: int = 2) -> List[Dict[str, Any]]:
    """
    Tra cứu cẩm nang bảo trì SOP.
    Sử dụng ChromaDB vector database nếu có; cơ chế Fallback đọc file markdown thông minh nếu offline.
    """
    # 1. Thử tra cứu từ ChromaDB
    try:
        import chromadb
        if CHROMA_DIR.exists():
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            collection = client.get_or_create_collection("nestle_packaging_sops")
            if collection.count() > 0:
                results = collection.query(query_texts=[query_text], n_results=n_results)
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                output = []
                for doc, meta in zip(docs, metas):
                    output.append({"content": doc, "metadata": meta, "source": "ChromaDB Vector Store"})
                return output
    except Exception as e:
        logger.warning(f"ChromaDB lookup chưa sẵn sàng ({e}). Kích hoạt Fallback Markdown parser...")

    # 2. Fallback: Tra cứu trực tiếp từ file tài liệu SOP Markdown
    if SOP_FILE.exists():
        with open(SOP_FILE, "r", encoding="utf-8") as f:
            content = f.read()

        # Tách nhỏ nội dung theo tiêu đề đề mục
        sections = content.split("## ")
        matched_sections = []
        q_upper = query_text.upper()

        for sec in sections:
            if not sec.strip():
                continue
            title = sec.split("\n")[0].strip()
            # Tìm kiếm khớp từ khóa mã lỗi hoặc từ vựng
            if any(term in sec.upper() for term in q_upper.split()) or any(code in title for code in ["E-105", "E-401", "E-204", "E-302", "E-999"]):
                matched_sections.append({
                    "title": title,
                    "content": f"## {sec.strip()[:1000]}...",
                    "source": "Local SOP Markdown File"
                })
            if len(matched_sections) >= n_results:
                break

        if matched_sections:
            return matched_sections

    return [{
        "title": "Standard Operating Instruction",
        "content": f"Quy trình xử lý sự cố chung: Ngắt nguồn máy, thực hiện quy trình LOTO, kiểm tra thiết bị, báo Trưởng ca.",
        "source": "Default Plant Protocol"
    }]


# ==============================================================================
# TOOL 5: CHỐT CHẶN AN TOÀN LOTO GUARDRAIL & CẬP NHẬT PHIẾU BẢO TRÌ
# ==============================================================================
def verify_loto_and_update_work_order(
    work_order_id: str,
    current_temp_sonotrode_c: float,
    loto_confirmed: bool,
    resolution_notes: str,
    target_action: str = "CLOSE"
) -> Dict[str, Any]:
    """
    CHỐT CHẶN AN TOÀN LOTO (LOCKOUT / TAGOUT SAFETY GUARDRAIL)
    Quy tắc bắt buộc của Nhà máy Nestlé Đồng Nai:
    1. Bắt buộc Kỹ thuật viên phải xác nhận đã khóa thẻ an toàn LOTO (loto_confirmed == True).
    2. Cấm đóng phiếu bảo trì hoặc khởi động lại máy nếu Nhiệt độ đầu hàn Sonotrode > 40.0°C (Nguy cơ bỏng cấp 2).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM fact_work_orders WHERE work_order_id = ?;", (work_order_id,))
    wo = cursor.fetchone()

    if not wo:
        conn.close()
        return {"status": "REJECTED", "error": f"Không tìm thấy Work Order ID: {work_order_id}"}

    # KIỂM ĐỊNH CHỐT CHẶN AN TOÀN (LOTO SAFETY GATE)
    if not loto_confirmed:
        conn.close()
        logger.error(f"[LOTO VIOLATION] Yêu cầu cập nhật {work_order_id} bị từ chối: Chưa xác nhận cô lập năng lượng!")
        return {
            "status": "SAFETY_BLOCKED",
            "violation": "LOTO_ISOLATION_MISSING",
            "message": "VI PHẠM AN TOÀN: Bắt buộc kỹ thuật viên phải thực hiện cô lập năng lượng (LOTO) và xác nhận cắm khóa thẻ an toàn trước khi thao tác!",
            "required_action": "Thực hiện khóa LOTO trên tủ điện biến tần và van khí nén, sau đó thử lại."
        }

    # KIỂM ĐỊNH NHIỆT ĐỘ AN TOÀN CHỐNG BỎNG (THERMAL HAZARD GATE)
    SAFE_TOUCH_TEMP_THRESHOLD = 40.0
    if target_action.upper() == "CLOSE" and current_temp_sonotrode_c > SAFE_TOUCH_TEMP_THRESHOLD:
        conn.close()
        logger.error(f"[THERMAL HAZARD] Nhiệt độ Sonotrode ({current_temp_sonotrode_c}°C) vượt ngưỡng an toàn (< {SAFE_TOUCH_TEMP_THRESHOLD}°C)!")
        return {
            "status": "SAFETY_BLOCKED",
            "violation": "HIGH_SURFACE_TEMPERATURE",
            "current_temp_c": current_temp_sonotrode_c,
            "safe_limit_c": SAFE_TOUCH_TEMP_THRESHOLD,
            "message": f"VI PHẠM AN TOÀN NHIỆT: Đầu hàn Sonotrode đang ở mức {current_temp_sonotrode_c}°C (> 40.0°C). Nguy cơ bỏng nghiêm trọng! Không được phép đóng phiếu bảo trì để vận hành máy.",
            "required_action": "Bật quạt cưỡng bức hoặc chờ hệ thống chiller làm mát đưa nhiệt độ về dưới 40.0°C."
        }

    # NẾU VƯỢT QUA TOÀN BỘ CHỐT CHẶN AN TOÀN -> TIẾN HÀNH CẬP NHẬT
    new_status = "CLOSED" if target_action.upper() == "CLOSE" else "IN_PROGRESS"
    new_loto = "RESTORED" if target_action.upper() == "CLOSE" else "VERIFIED_LOTO"

    cursor.execute("""
    UPDATE fact_work_orders
    SET order_status = ?,
        loto_status = ?,
        resolution_notes = ?,
        closed_at = CURRENT_TIMESTAMP
    WHERE work_order_id = ?;
    """, (new_status, new_loto, resolution_notes, work_order_id))

    conn.commit()
    conn.close()

    logger.info(f"[LOTO APPROVED] Phiếu {work_order_id} đã được cập nhật thành công ({new_status} / {new_loto}).")
    return {
        "status": "SUCCESS",
        "work_order_id": work_order_id,
        "new_order_status": new_status,
        "new_loto_status": new_loto,
        "message": f"Chốt chặn an toàn phê duyệt! Phiếu {work_order_id} đã được cập nhật thành công."
    }


# ==============================================================================
# HÀM KIỂM THỬ KỸ THUẬT ĐỘC LẬP (SELF-TEST SUITE)
# ==============================================================================
if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("      KIỂM THỬ MANUFACTURING ANALYTICS ENGINE & LOTO GUARDRAIL")
    print("=" * 80)

    # 1. Test MTTR / MTBF cho Dây chuyền 1 (A3/Speed)
    print("\n[TEST 1] CHỈ SỐ ĐỘ TIN CẬY (LINE_01):")
    metrics_line1 = calculate_line_reliability_metrics(line_id="LINE_01")
    for k, v in metrics_line1.items():
        print(f"  - {k:<30}: {v}")

    # 2. Test Phân tích Pareto 80/20
    print("\n[TEST 2] PHÂN TÍCH PARETO 80/20 DỪNG MÁY TOÀN NHÀ MÁY:")
    pareto_res = get_pareto_downtime_analysis()
    for item in pareto_res:
        print(f"  - Mã lỗi {item['error_code']:<6} | Mất: {item['total_lost_units']:>9,} hộp ({item['lost_share_pct']:>5}%) | Tích lũy: {item['cumulative_share_pct']:>5}% | Phân loại: {item['pareto_class']}")

    # 3. Test LOTO Guardrail: Thử nghiệm hành vi vi phạm an toàn nhiệt (> 40°C)
    print("\n[TEST 3A] KIỂM THỬ CHỐT CHẶN AN TOÀN NHIỆT (Cố tình đóng phiếu khi nhiệt độ còn 58°C):")
    blocked_test = verify_loto_and_update_work_order(
        work_order_id="WO-20260301-0001",
        current_temp_sonotrode_c=58.5,
        loto_confirmed=True,
        resolution_notes="Đã kiểm tra xong nhưng đầu hàn còn nóng",
        target_action="CLOSE"
    )
    print(f"  Kết quả: {blocked_test['status']}")
    print(f"  Thông điệp: {blocked_test.get('message')}")

    # 4. Test LOTO Guardrail: Đóng phiếu hợp lệ (Nhiệt độ an toàn 32°C, đã xác nhận LOTO)
    print("\n[TEST 3B] KIỂM THỬ CHỐT CHẶN AN TOÀN HỢP LỆ (Nhiệt độ 32°C, xác nhận LOTO):")
    approved_test = verify_loto_and_update_work_order(
        work_order_id="WO-20260301-0001",
        current_temp_sonotrode_c=32.0,
        loto_confirmed=True,
        resolution_notes="Nhiệt độ hạ an toàn, đã vệ sinh sonotrode và mở khóa bàn giao",
        target_action="CLOSE"
    )
    print(f"  Kết quả: {approved_test['status']}")
    print(f"  Thông điệp: {approved_test.get('message')}")
    print("=" * 80 + "\n")