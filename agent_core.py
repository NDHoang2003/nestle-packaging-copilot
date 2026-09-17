import os
import json
from google import genai
from google.genai import types
from dotenv import load_dotenv
from factory_tools import (
    query_downtime_history, 
    search_machine_manual, 
    create_maintenance_work_order,
    close_maintenance_ticket
)

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("Chua tim thay GEMINI_API_KEY trong file .env!")

client = genai.Client(api_key=GEMINI_API_KEY)

TOOL_DISPATCHER = {
    "query_downtime_history": query_downtime_history,
    "search_machine_manual": search_machine_manual,
    "create_maintenance_work_order": create_maintenance_work_order,
    "close_maintenance_ticket": close_maintenance_ticket
}

SYSTEM_INSTRUCTION = """
Bạn là Nestlé Packaging Maintenance Copilot & Diagnostics Agent.

Nhiệm vụ:
1. Khi có sự cố mới: Tra cứu SQL và SOP, xuất phiếu bảo trì ('create_maintenance_work_order').
2. Khi kỹ thuật viên thông báo ĐÃ SỬA XONG hoặc yêu cầu ĐÓNG PHIẾU:
   - Sử dụng tool 'close_maintenance_ticket' để đóng phiếu.
   - Yêu cầu các thông tin: ticket_id, tên kỹ thuật viên, thời gian dừng máy thực tế (phút), nguyên nhân và thao tác đã xử lý.
   - Xác nhận với kỹ thuật viên rằng dữ liệu đã được lưu lại để phục vụ phân tích TPM/Kaizen sau này.
"""

class PackagingCopilotAgent:
    def __init__(self, model_name: str = "gemini-3.6-flash"):
        self.model_name = model_name
        self.tools_list = [
            query_downtime_history, 
            search_machine_manual, 
            create_maintenance_work_order,
            close_maintenance_ticket
        ]
        self.chat = client.chats.create(
            model=self.model_name,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.1,
                tools=self.tools_list
            )
        )

    def execute_reasoning_loop(self, prompt: str, max_iterations: int = 4) -> str:
        response = self.chat.send_message(prompt)

        for iteration in range(max_iterations):
            if not response.function_calls:
                break

            for call in response.function_calls:
                tool_name = call.name
                tool_args = dict(call.args)
                print(f"\n⚙️  [AGENT ACTION]: Gọi tool -> '{tool_name}'")
                print(f"📋 [PARAMS]: {json.dumps(tool_args, ensure_ascii=False)}")

                if tool_name in TOOL_DISPATCHER:
                    result = TOOL_DISPATCHER[tool_name](**tool_args)
                else:
                    result = {"status": "ERROR", "message": f"Tool '{tool_name}' không tồn tại"}

                response = self.chat.send_message(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result}
                    )
                )

        return response.text

def diagnose_and_act(event_description: str) -> str:
    agent = PackagingCopilotAgent()
    return agent.execute_reasoning_loop(event_description)

if __name__ == "__main__":
    print("=== NESTLÉ PACKAGING COPILOT (HỖ TRỢ ĐÓNG PHIẾU VÀ XỬ LÝ) ===")
    agent = PackagingCopilotAgent()
    while True:
        try:
            q = input("\n👤 KỸ THUẬT VIÊN: ").strip()
            if q.lower() in ["exit", "quit"]:
                break
            ans = agent.execute_reasoning_loop(q)
            print(f"\n🤖 [COPILOT]:\n{ans}")
        except KeyboardInterrupt:
            break
