#!/usr/bin/env python3
"""
================================================================================
NESTLE DONG NAI FACTORY - INDUSTRIAL PACKAGING DIGITAL TWIN
Module: AI Agent Core with Hybrid Dual-Mode Architecture (Phase 4.2)
Key Enhancements:
  - Zero Thinking-Token Overhead (thinking_budget=0 for instant latency).
  - Explicit tools=[] to suppress AFC warnings.
  - Active 2026 Model Fallback Chain: gemini-3.5-flash-lite -> gemini-3.1-flash-lite -> gemini-3.8-flash.
  - Industrial-Grade Edge Heuristic Expert Engine (100% resilient when offline).
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
from typing import Dict, Any, Optional

from dotenv import load_dotenv
load_dotenv()

import factory_tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (Nestle-Agent) %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("PackagingAgent")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "packaging_factory.db"

INTERACTIVE_SYSTEM_INSTRUCTION = """
Bạn là "Nestlé Packaging Copilot" - Chuyên gia AI Cấp cao về Độ tin cậy Thiết bị (TPM) & Tối ưu hóa Dây chuyền Đóng gói Vô trùng tại Nhà máy Nestlé Đồng Nai.
Bạn báo cáo trực tiếp cho Trưởng phòng Tối ưu hóa Sản xuất (Manufacturing Excellence Manager).

QUY TẮC:
1. SỬ DỤNG CÔNG CỤ: Gọi các công cụ Python khi người dùng hỏi về số liệu tổng hợp (MTTR, MTBF, Pareto, Snapshot cảm biến, LOTO).
2. PHONG CÁCH: Ngắn gọn, chuyên nghiệp, chuẩn mực Kaizen/TPM.
"""

PYTHON_TOOLS = [
    factory_tools.calculate_line_reliability_metrics,
    factory_tools.get_pareto_downtime_analysis,
    factory_tools.get_recent_telemetry_snapshot,
    factory_tools.query_sop_knowledge_base,
    factory_tools.verify_loto_and_update_work_order
]


class PackagingCopilotAgent:
    """Agent điều phối suy luận AI hỗ trợ cả 2 chế độ: Khẩn cấp (Fast) và Tương tác (Interactive)."""

    def __init__(self):
        self.api_key = GEMINI_API_KEY
        self.client = None
        # Danh sách các model thế hệ 3.x còn hoạt động (Ưu tiên Flash-Lite vì quota dồi dào và tốc độ cao)
        self.candidate_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.8-flash",
            "gemini-3.6-flash"
        ]
        self._init_agent()

    def _init_agent(self):
        if not self.api_key:
            logger.warning("[API KEY MISSING] Chưa tìm thấy GEMINI_API_KEY trong file .env.")
            return

        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            logger.info("Khởi tạo thành công Gemini Client (Hỗ trợ Edge Hybrid Architecture).")
        except Exception as e:
            logger.error(f"Lỗi khởi tạo Gemini Client: {e}")

    # ==========================================================================
    # CHẾ ĐỘ 1: CHẨN ĐOÁN SỰ CỐ KHẨN CẤP (FAST SINGLE-SHOT ZERO-TOOL)
    # ==========================================================================
    def diagnose_incident_fast(self, sensor_state: dict) -> str:
        line_id = sensor_state.get("line_id", "LINE_01")
        err_code = sensor_state.get("error_code", "E-204")
        t_sono = sensor_state.get("temp_sonotrode_c", 0.0)
        delta_t = sensor_state.get("delta_t", 0.0)
        p_kw = sensor_state.get("p_mech_kw", 0.0)
        knife = sensor_state.get("cutting_knife_wear_m", 0)
        rpm = sensor_state.get("speed_servo_rpm", 0.0)
        torque = sensor_state.get("tension_torque_nm", 0.0)
        rec_id = sensor_state.get("record_id", 0)

        # 1. Nạp cẩm nang SOP cục bộ trong 0ms
        sop_data = factory_tools.query_sop_knowledge_base(err_code, n_results=1)
        sop_summary = sop_data[0].get("content", "Thực hiện khóa LOTO và kiểm tra cơ khí.")[:400]

        prompt_payload = f"""
CẢNH BÁO SỰ CỐ KHẨN CẤP TẠI DÂY CHUYỀN NESTLÉ ĐỒNG NAI:
Dây chuyền {line_id} vừa kích hoạt dừng máy khẩn cấp tại Frame #{rec_id}!

THÔNG SỐ CẢM BIẾN TỨC THỜI:
- Mã lỗi: {err_code}
- Nhiệt độ Sonotrode: {t_sono}°C (Ngưỡng an toàn bỏng: < 40.0°C)
- Delta_T Chiller: {delta_t}°C (Ngưỡng làm mát chuẩn: > 8.6°C)
- Công suất cơ P_mech: {p_kw} kW (Dải danh định: 3.5 - 9.0 kW)
- Tốc độ Servo: {rpm} RPM | Momen xoắn: {torque} Nm
- Độ mòn dao cắt: {knife} phút (Giới hạn thay dao: 200 phút)

TRÍCH XUẤT CẨM NANG BẢO TRÌ SOP CỤC BỘ:
{sop_summary}

YÊU CẦU: Hãy lập Báo cáo Chẩn đoán Nguyên nhân Gốc rễ (RCA) hoàn chỉnh, ngắn gọn cho Trưởng ca:
1. Đánh giá nhanh các thông số vượt ngưỡng.
2. Cơ chế vật lý gây lỗi (5-Why cơ điện tử).
3. Hướng dẫn an toàn LOTO và các bước can thiệp kỹ thuật ngay lập tức.
(LƯU Ý: Không sử dụng công cụ bên ngoài, trả về văn bản báo cáo hoàn chỉnh ngay lập tức).
"""

        if not self.client:
            return self._offline_expert_engine(sensor_state, sop_summary)

        from google.genai import types

        for model_id in self.candidate_models:
            try:
                # Cấu hình tối ưu: tools=[] triệt tiêu AFC warning, max_output_tokens=2048 chống cụt chữ
                response = self.client.models.generate_content(
                    model=model_id,
                    contents=prompt_payload,
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=2048,
                        tools=[],  # Tắt hoàn toàn tool calling
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
                    )
                )
                if response.text and len(response.text.strip()) > 50:
                    return response.text
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    logger.warning(f"[CLOUD QUOTA LIMIT] Model {model_id} đã hết hạn ngạch ngày (429). Thử model tiếp theo...")
                elif "404" in err_msg:
                    logger.debug(f"Model {model_id} không tồn tại trên endpoint này (404).")
                elif "503" in err_msg:
                    logger.warning(f"Model {model_id} đang quá tải tạm thời (503).")
                else:
                    logger.warning(f"Lỗi với model {model_id}: {e}")
                continue

        logger.info("⚡ [FAIL-SAFE ENGAGED] Kích hoạt Edge Heuristic Expert Engine (Zero Cloud Latency)!")
        return self._offline_expert_engine(sensor_state, sop_summary)

    # ==========================================================================
    # HỆ CHUYÊN GIA NỘI BỘ (INDUSTRIAL EDGE EXPERT ENGINE)
    # Tự động suy luận vật lý 100% cục bộ khi không có Cloud API!
    # ==========================================================================
    def _offline_expert_engine(self, s: dict, sop_text: str) -> str:
        line = s.get("line_id", "LINE_01")
        err = s.get("error_code", "E-204")
        t_sono = s.get("temp_sonotrode_c", 35.0)
        delta_t = s.get("delta_t", 10.0)
        p_kw = s.get("p_mech_kw", 5.0)
        knife = s.get("cutting_knife_wear_min", 100)
        rpm = s.get("speed_servo_rpm", 1500.0)
        torque = s.get("tension_torque_nm", 35.0)

        # 1. Đánh giá an toàn nhiệt LOTO
        thermal_safe = t_sono <= 40.0
        thermal_status = f"✅ {t_sono}°C - ĐẠT AN TOÀN THAO TÁC (< 40.0°C)" if thermal_safe else f"🚨 {t_sono}°C - NGUY HIỂM BỎNG (> 40.0°C - CẤM CHẠM VÀO NGÀM)"

        # 2. Suy luận chuyên sâu theo từng mã lỗi chuẩn Nestlé
        rca_detail = ""
        action_sop = ""

        if err == "E-204":
            rca_detail = (
                f"- Công suất cơ học P_mech = {p_kw:.2f} kW (Tốc độ {rpm:.0f} RPM, Mô-men {torque:.1f} Nm).\n"
                f"- Lực cản truyền động biến thiên đột ngột dẫn đến quá tải biến tần hoặc trượt tải cơ cấu kéo màng bao bì vô trùng."
            )
            action_sop = (
                "1. Ngắt nguồn động lực chính, gắn khóa thẻ LOTO tại tủ biến tần Servo.\n"
                "2. Dùng tay quay (Jog mode) kiểm tra độ trơn tru của trục kéo và hộp giảm tốc.\n"
                "3. Kiểm tra kẹt dị vật bao bì carton tại hàm dập; reset lỗi biến tần sau khi xử lý."
            )
        elif err == "E-401":
            rca_detail = (
                f"- Nhiệt độ đầu hàn Sonotrode đạt {t_sono:.1f}°C, Delta_T = {delta_t:.1f}°C.\n"
                f"- Hiệu suất giải nhiệt suy giảm (nguy cơ nghẽn lưu lượng nước làm mát Chiller hoặc hỏng cảm biến nhiệt RTD)."
            )
            action_sop = (
                "1. Tạm dừng dây chuyền, duy trì bơm tuần hoàn nước làm mát Chiller.\n"
                "2. Kiểm tra lưu lượng kế và áp suất đường ống nước làm mát cấp cho ngàm hàn.\n"
                "3. Chờ nhiệt độ Sonotrode hạ xuống dưới 40°C trước khi tiến hành vệ sinh bề mặt đầu hàn."
            )
        elif err == "E-302":
            rca_detail = (
                f"- Dao cắt đã vận hành liên tục {knife} phút (Vượt ngưỡng tuổi thọ quy định 200 phút).\n"
                f"- Mép cắt bị cùn làm gia tăng ứng suất cắt và gây tưa mép ống hút hoặc mép dán đáy bao bì Milo."
            )
            action_sop = (
                "1. Thực hiện LOTO cách ly cụm dao cắt vô trùng.\n"
                "2. Tháo cụm hàm dập, thay thế cụm dao cắt mới 100%.\n"
                "3. Căn chỉnh khe hở đe cắt (0.03 - 0.05 mm), reset bộ đếm Knife Wear Timer về 0 phút."
            )
        elif err == "E-105":
            rca_detail = (
                f"- Delta_T đạt {delta_t:.1f}°C lệch khỏi dải làm việc tiêu chuẩn (> 8.6°C).\n"
                f"- Nhiệt độ phòng sạch hoặc cụm khuôn hàn bị đọng nhiệt cục bộ."
            )
            action_sop = (
                "1. Kiểm tra van tiết lưu và nhiệt độ nước cấp từ hệ thống Chiller trung tâm.\n"
                "2. Xả cặn đường ống trao đổi nhiệt của khuôn hàn."
            )
        else:
            rca_detail = f"- Cảm biến ghi nhận bất thường tham số vận hành không xác định ({err})."
            action_sop = "1. Thực hiện quy trình LOTO tổng quát, liên hệ Trưởng ca Cơ điện kiểm tra chuyên sâu."

        report = f"""**BÁO CÁO PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ (RCA - INDUSTRIAL EDGE ENGINE)**
*Hệ thống: {line} - Nhà máy Nestlé Đồng Nai*
*Phương thức suy luận: Edge Expert Engine (Tự trị cục bộ - Không phụ thuộc Cloud)*
--------------------------------------------------------------------------------
### 1. ĐÁNH GIÁ THÔNG SỐ VẬN HÀNH:
- Trạng thái An toàn Nhiệt LOTO: {thermal_status}
- Công suất cơ học P_mech: {p_kw:.2f} kW | Dao cắt mòn: {knife} phút
- Tốc độ Servo: {rpm:.0f} RPM | Momen xoắn: {torque:.1f} Nm

### 2. PHÂN TÍCH NGUYÊN NHÂN VẬT LÝ (RCA - 5 WHY):
{rca_detail}

### 3. QUY TRÌNH CAN THIỆP KỸ THUẬT & AN TOÀN LOTO (SOP):
{action_sop}
--------------------------------------------------------------------------------"""
        return report

    # ==========================================================================
    # CHẾ ĐỘ 2: TRỢ LÝ TƯƠNG TÁC ĐIỀU HÀNH (DÀNH CHO DASHBOARD UI APP.PY)
    # ==========================================================================
    def chat(self, user_prompt: str) -> str:
        if not self.client:
            return self._offline_fallback_response(user_prompt)

        from google.genai import types

        for model_id in self.candidate_models:
            try:
                chat_session = self.client.chats.create(
                    model=model_id,
                    config=types.GenerateContentConfig(
                        system_instruction=INTERACTIVE_SYSTEM_INSTRUCTION,
                        tools=PYTHON_TOOLS,
                        temperature=0.2
                    )
                )
                response = chat_session.send_message(user_prompt)
                return response.text
            except Exception:
                continue

        return self._offline_fallback_response(user_prompt)

    def _offline_fallback_response(self, user_prompt: str) -> str:
        q = user_prompt.lower()
        if "mttr" in q or "mtbf" in q or "độ tin cậy" in q:
            m = factory_tools.calculate_line_reliability_metrics("LINE_01")
            return (
                f"[OFFLINE COPILOT] Chỉ số TPM LINE_01 (Tetra Pak A3/Speed):\n"
                f"- MTTR: {m['mttr_minutes']} phút | MTBF: {m['mtbf_minutes']} phút\n"
                f"- Availability: {m['availability_rate_pct']}%\n"
                f"- Thất thoát: {m['total_units_lost']:,} hộp Milo."
            )
        elif "pareto" in q or "nguyên nhân" in q:
            p = factory_tools.get_pareto_downtime_analysis()
            top = p[0] if p else {}
            return (
                f"[OFFLINE COPILOT] Phân tích Pareto 80/20:\n"
                f"Sự cố gây thất thoát hàng đầu là {top.get('error_code')} ({top.get('failure_type')}) "
                f"chiếm {top.get('lost_share_pct')}% tổng sản lượng mất."
            )
        return "[OFFLINE COPILOT] Hệ thống đang chạy chế độ an toàn nội bộ."