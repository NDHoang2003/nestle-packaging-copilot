#!/usr/bin/env python3
"""
================================================================================
NESTLE DONG NAI FACTORY - INDUSTRIAL PACKAGING DIGITAL TWIN
Module: Industrial API Gateway for Microsoft Power Platform (Phase 5)
Role: Bridges Edge Telemetry, SQLite Star Schema & Gemini AI Copilot 
      with Microsoft Power Apps (Frontline UI) & Power BI (Executive Analytics).
Author: Nguyen Doan Hoang (Digital Technical Specialist Candidate)
Reviewed by: Lead Industrial Data & AI Engineer
================================================================================
"""

import os
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import factory_tools
from agent_core import PackagingCopilotAgent

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "packaging_factory.db"

# Khởi tạo FastAPI App kèm metadata phục vụ Power Apps Custom Connector
app = FastAPI(
    title="Nestlé Đồng Nai - Packaging Digital Twin Edge API",
    description="API Gateway kết nối Dây chuyền Đóng gói Vô trùng với Microsoft Power Apps & Power BI.",
    version="1.0.0"
)

# Kích hoạt CORS để cho phép Power Apps và các ứng dụng web gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi tạo não bộ AI Copilot
copilot_agent = PackagingCopilotAgent()


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


# ==============================================================================
# PYDANTIC SCHEMAS CHO POWER APPS
# ==============================================================================
class LotoVerifyRequest(BaseModel):
    work_order_id: str = Field(..., description="Mã phiếu bảo trì, ví dụ: WO-AUTO-20261016153502")
    current_temp_sonotrode_c: float = Field(..., description="Nhiệt độ đầu hàn Sonotrode hiện tại (°C)")
    loto_confirmed: bool = Field(..., description="Xác nhận đã cô lập nguồn năng lượng và treo thẻ khóa LOTO")
    resolution_notes: str = Field(..., description="Ghi chú kỹ thuật sau khi xử lý sự cố")
    target_action: str = Field("CLOSE", description="Hành động: CLOSE hoặc IN_PROGRESS")


class CopilotChatRequest(BaseModel):
    user_prompt: str = Field(..., description="Câu hỏi hoặc yêu cầu dành cho Copilot")


# ==============================================================================
# ENDPOINTS DÀNH CHO POWER APPS (FRONTLINE INTERFACE)
# ==============================================================================
@app.get("/api/health", tags=["System"])
def health_check():
    """Kiểm tra trạng thái sẵn sàng của Edge Gateway."""
    return {
        "status": "HEALTHY",
        "plant": "Nestle Dong Nai Factory",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


@app.get("/api/telemetry/live", tags=["Power Apps - Frontline"])
def get_live_telemetry():
    """
    Cung cấp nhịp tim cảm biến thời gian thực của các dây chuyền từ bảng đệm.
    Power Apps gọi định kỳ (Timer: mỗi 2s) để cập nhật trạng thái RUNNING / TRIPPED.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT line_id, record_id, last_updated, machine_name, temp_cleanroom_c,
               temp_sonotrode_c, speed_servo_rpm, tension_torque_nm,
               cutting_knife_wear_min, delta_t, dt_dt, p_mech_kw,
               heat_strain_index, error_code, is_failure, alert_severity,
               interlock_latched, machine_state, active_work_order_id
        FROM realtime_edge_buffer;
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"count": len(rows), "records": rows}


@app.get("/api/work-orders/open", tags=["Power Apps - Frontline"])
def get_open_work_orders():
    """
    Lấy danh sách các Phiếu bảo trì đang mở (OPEN) để hiển thị lên Power Apps Gallery
    cho Kỹ thuật viên tiếp nhận xử lý.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT w.work_order_id, w.event_id, w.line_id, w.error_code, w.created_at,
               w.priority, w.loto_status, w.technician_assigned, w.resolution_notes, w.order_status,
               d.impact_units_lost, d.downtime_duration_minutes
        FROM fact_work_orders w
        LEFT JOIN fact_downtime_events d ON w.event_id = d.event_id
        WHERE w.order_status = 'OPEN'
        ORDER BY w.created_at DESC;
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"count": len(rows), "work_orders": rows}


@app.post("/api/loto/verify-and-update", tags=["Power Apps - Frontline"])
def verify_loto_gate(payload: LotoVerifyRequest):
    """
    CHỐT CHẶN AN TOÀN LOTO:
    Kỹ thuật viên submit form từ Power Apps. Hệ thống kiểm định điều kiện:
    1. Đã bấm xác nhận khóa thẻ an toàn (loto_confirmed == True).
    2. Nhiệt độ Sonotrode phải < 40.0°C (Chống bỏng cấp 2).
    Nếu vi phạm -> Trả về cảnh báo SAFETY_BLOCKED và cấm đóng phiếu!
    """
    result = factory_tools.verify_loto_and_update_work_order(
        work_order_id=payload.work_order_id,
        current_temp_sonotrode_c=payload.current_temp_sonotrode_c,
        loto_confirmed=payload.loto_confirmed,
        resolution_notes=payload.resolution_notes,
        target_action=payload.target_action
    )
    if result.get("status") == "REJECTED":
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@app.post("/api/copilot/chat", tags=["Power Apps - Frontline"])
def chat_with_copilot(payload: CopilotChatRequest):
    """
    Khung chat tương tác với Nestlé Packaging Copilot:
    Kỹ thuật viên hoặc Quản lý hỏi đáp trực tiếp từ giao diện Power Apps.
    """
    response_text = copilot_agent.chat(payload.user_prompt)
    return {
        "user_prompt": payload.user_prompt,
        "copilot_response": response_text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


# ==============================================================================
# ENDPOINTS DÀNH CHO POWER BI (ANALYTICS & OEE)
# ==============================================================================
@app.get("/api/analytics/tpm-kpis", tags=["Power BI - Analytics"])
def get_tpm_kpis(line_id: Optional[str] = Query(None, description="Lọc theo mã Line")):
    """Cung cấp số liệu MTTR, MTBF, Availability cho Power BI Card Visuals."""
    return factory_tools.calculate_line_reliability_metrics(line_id=line_id)


@app.get("/api/analytics/pareto-loss", tags=["Power BI - Analytics"])
def get_pareto_loss_data(line_id: Optional[str] = Query(None, description="Lọc theo mã Line")):
    """Cung cấp dữ liệu bảng phân tích Pareto 80/20 sản lượng mất cho Power BI Chart."""
    return factory_tools.get_pareto_downtime_analysis(line_id=line_id)


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 80)
    print("  KHỞI ĐỘNG FASTAPI INDUSTRIAL EDGE GATEWAY CHO MICROSOFT POWER PLATFORM")
    print("  Swagger UI: http://127.0.0.1:8000/docs")
    print("  OpenAPI JSON (dùng tạo Custom Connector): http://127.0.0.1:8000/openapi.json")
    print("=" * 80 + "\n")
    uvicorn.run("api_gateway:app", host="0.0.0.0", port=8000, reload=True)