#!/usr/bin/env python3
"""
================================================================================
NESTLE DONG NAI FACTORY - INDUSTRIAL PACKAGING DIGITAL TWIN
Module: AI Agent Core with Google Gemini 3.8 Automatic Function Calling (Phase 4.2)
Role: Autonomous RCA Diagnosis, TPM Analytics & LOTO Safety Enforcement
Author: Nguyen Doan Hoang (Digital Technical Specialist Candidate)
Reviewed by: Lead Industrial Data & AI Engineer
================================================================================
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Any

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

SYSTEM_INSTRUCTION = """
Bạn là "Nestlé Packaging Copilot" - Chuyên gia AI Cấp cao về Độ tin cậy Thiết bị (TPM) & Tối ưu hóa Dây chuyền Đóng gói Vô trùng tại Nhà máy Nestlé Đồng Nai (KCN Biên Hòa 2).
Bạn báo cáo trực tiếp cho Trưởng phòng Tối ưu hóa Sản xuất (Manufacturing Excellence Manager).

DÂY CHUYỀN GIÁM SÁT:
- LINE_01: Tetra Pak A3/Speed 115ml (Milo 115ml - Công suất 24,000 hộp/h)
- LINE_02: Tetra Pak TBA/19 180ml (Milo 180ml - Công suất 7,500 hộp/h)
- LINE_03: SIG Combibloc CFA 312 (Sữa 250ml - Công suất 12,000 hộp/h)

QUY TẮC BẮT BUỘC KHI PHẢN HỒI:
1. SỬ DỤNG CÔNG CỤ: Luôn gọi các công cụ Python được cung cấp để lấy số liệu thực tế từ Database. Tuyệt đối không tự bịa số liệu MTTR, MTBF hoặc nhiệt độ.
2. PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ (RCA): Gắn liền các bất thường cảm biến với cơ chế vật lý (Delta_T < 8.6°C là nghẽn tản nhiệt/chiller, P_mech lệch ngưỡng 3.5-9kW là lỗi động cơ biến tần, dao mòn > 200 phút là mép cắt không đứt).
3. AN TOÀN LÀ SỐ 1 (LOTO FIRST): Khi thao tác đóng phiếu bảo trì hoặc bàn giao chạy máy, BẮT BUỘC phải yêu cầu kiểm tra xác nhận LOTO và nhiệt độ Sonotrode phải < 40.0°C.
4. PHONG CÁCH: Súc tích, chuyên nghiệp, chuẩn mực Kaizen/TPM, đưa ra khuyến nghị hành động cụ thể cho kỹ thuật viên.
"""

# Danh sách hàm Python trực tiếp để Gemini gọi qua Automatic Function Calling (AFC)
PYTHON_TOOLS = [
    factory_tools.calculate_line_reliability_metrics,
    factory_tools.get_pareto_downtime_analysis,
    factory_tools.get_recent_telemetry_snapshot,
    factory_tools.query_sop_knowledge_base,
    factory_tools.verify_loto_and_update_work_order
]


class PackagingCopilotAgent:
    """Agent điều phối suy luận AI sử dụng Gemini 3.8 Automatic Function Calling."""

    def __init__(self):
        self.api_key = GEMINI_API_KEY
        self.client = None
        self.chat_session = None
        self._init_agent()

    def _init_agent(self):
        if not self.api_key:
            logger.warning("[API KEY MISSING] Chưa tìm thấy GEMINI_API_KEY trong file .env.")
            return

        try:
            from google import genai
            from google.genai import types

            self.client = genai.Client(api_key=self.api_key)

            # Khởi tạo Chat Session với Automatic Function Calling (AFC) chuẩn của Google
            self.chat_session = self.client.chats.create(
                model="gemini-3.8-flash",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    tools=PYTHON_TOOLS,
                    temperature=0.2
                )
            )
            logger.info("Khởi tạo thành công Gemini 3.8 Copilot với Automatic Function Calling (AFC).")

        except Exception as e:
            logger.error(f"Lỗi khởi tạo Gemini Client: {e}")

    def chat(self, user_prompt: str) -> str:
        """
        Gửi prompt đến Copilot với cơ chế Resilience:
        - Tự động Retry khi gặp lỗi 503 / 429 (Exponential Backoff).
        - Tự động Fallback sang model dự phòng (3.8 -> 3.6 -> 3.5).
        """
        if not self.client:
            return self._offline_fallback_response(user_prompt)

        import time
        from google.genai import types

        # Danh sách model theo thứ tự ưu tiên
        candidate_models = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"]
        MAX_RETRIES = 2

        for model_id in candidate_models:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    # Tạo chat session độc lập cho mỗi lượt truy vấn để đảm bảo state sạch
                    chat_session = self.client.chats.create(
                        model=model_id,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            tools=PYTHON_TOOLS,
                            temperature=0.2
                        )
                    )

                    # Gửi tin nhắn và kích hoạt Automatic Function Calling
                    response = chat_session.send_message(user_prompt)
                    return response.text

                except Exception as e:
                    err_str = str(e)
                    # Nếu gặp lỗi quá tải server (503) hoặc rate limit (429)
                    if "503" in err_str or "overloaded" in err_str.lower() or "429" in err_str:
                        wait_seconds = attempt * 1.5
                        logger.warning(
                            f"[SERVER OVERLOAD 503] Model {model_id} đang bận (Lần thử {attempt}/{MAX_RETRIES}). "
                            f"Chờ {wait_seconds}s trước khi thử lại..."
                        )
                        time.sleep(wait_seconds)
                        continue
                    else:
                        logger.warning(f"Lỗi với model {model_id}: {e}. Chuyển sang model dự phòng tiếp theo...")
                        break  # Chuyển sang candidate_model tiếp theo

        logger.error("Tất cả các model và lần thử đều thất bại do quá tải cloud. Chuyển sang phản hồi Heuristic an toàn.")
        return self._offline_fallback_response(user_prompt)
    
    def _offline_fallback_response(self, user_prompt: str) -> str:
        q = user_prompt.lower()
        if "mttr" in q or "mtbf" in q or "độ tin cậy" in q:
            m = factory_tools.calculate_line_reliability_metrics("LINE_01")
            return (
                f"[OFFLINE COPILOT] Chỉ số TPM của LINE_01 (Tetra Pak A3/Speed):\n"
                f"- MTTR: {m['mttr_minutes']} phút (Thời gian sửa trung bình)\n"
                f"- MTBF: {m['mtbf_minutes']} phút (Thời gian chạy ổn định)\n"
                f"- Availability: {m['availability_rate_pct']}%\n"
                f"- Sản lượng mất: {m['total_units_lost']:,} hộp Milo."
            )
        elif "pareto" in q or "nguyên nhân" in q:
            p = factory_tools.get_pareto_downtime_analysis()
            top = p[0] if p else {}
            return (
                f"[OFFLINE COPILOT] Phân tích Pareto 80/20:\n"
                f"Sự cố gây thất thoát hàng đầu là mã lỗi {top.get('error_code')} ({top.get('failure_type')}) "
                f"chiếm {top.get('lost_share_pct')}% tổng sản lượng mất."
            )
        return "[OFFLINE COPILOT] Lỗi kết nối cloud. Vui lòng kiểm tra lại đường truyền."


# ==============================================================================
# TEST SUITE
# ==============================================================================
if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("      KHỞI ĐỘNG NESTLÉ PACKAGING COPILOT (GEMINI 3.8 AFC ENGINE)")
    print("=" * 80)

    agent = PackagingCopilotAgent()

    test_queries = [
        "Cho tôi biết các chỉ số độ tin cậy MTTR và MTBF hiện tại của Dây chuyền 1 (LINE_01)?",
        "Phân tích Pareto cho thấy sự cố nào đang gây mất sản lượng nhiều nhất trong nhà máy?",
        "Dây chuyền LINE_01 hiện tại đang có thông số cảm biến thế nào? Có nguy cơ gì không?"
    ]

    for idx, query in enumerate(test_queries, 1):
        print(f"\n[CÂU HỎI {idx}]: {query}")
        print("-" * 80)
        answer = agent.chat(query)
        print(f"[COPILOT PHẢN HỒI]:\n{answer}")
        print("=" * 80)