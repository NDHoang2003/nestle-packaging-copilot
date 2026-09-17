# NESTLÉ PACKAGING BREAKDOWN DIAGNOSTICS & CLOSED-LOOP MAINTENANCE COPILOT

> **Vị trí ứng tuyển:** Digital Technical Specialist - Nestlé Vietnam  
> **Ứng viên:** Nguyễn Doãn Hoàng (Data Analyst / Cử nhân KHMT - ĐH Bách Khoa ĐHQG-HCM)  
> **Kiến trúc:** Event-Driven Autonomous AI Agent with Deterministic Guardrails & Closed-Loop Feedback  
> **Trạng thái:** Hoàn thành Core Engine & Data Pipeline (Sẵn sàng tích hợp Microsoft Power Platform)

---

## 1. TỔNG QUAN BÀI TOÁN NGHIỆP VỤ (BUSINESS CONTEXT)

Tại các nhà máy Nestlé (sản xuất Milo, sữa tiệt trùng hộp giấy, La Vie), dây chuyền đóng gói vô trùng tốc độ cao (Aseptic Packaging - Tetra Pak / SIG Combibloc) khi dừng đột ngột sẽ gây tổn thất lớn về chi phí và sản lượng.

Dự án này giải quyết bài toán vận hành bằng một **Hệ thống AI Tự hành Khép kín (Closed-Loop Autonomous Agent)**:
1. **Perception (Cảm nhận tự động):** Nghe ngóng stream cảm biến nhiệt độ từ PLC dây chuyền.
2. **Anti-False-Positive Filter:** Lọc nhiễu điện cực, chỉ kích hoạt khi thông số vi phạm an toàn liên tục (ngưỡng quá nhiệt mối hàn > 145°C trong 2 mẫu liên tiếp).
3. **Dual-Brain Investigation (RAG + SQL):** Tự động đối chiếu lịch sử dừng máy từ SQLite và quy trình an toàn SOP từ ChromaDB.
4. **Deterministic Verification Guardrails:** Kiểm thử an toàn trước khi ghi nhận (Bắt buộc quy trình ngắt nguồn LOTO, chống spam vé trùng lặp trong 60 phút, khóa cứng mức độ ưu tiên bằng Enum P1-CRITICAL).
5. **Closed-Loop Feedback:** Cho phép Kỹ thuật viên báo cáo nghiệm thu và đóng ticket qua ngôn ngữ tự nhiên. Hệ thống tự động ghi nhận thời gian dừng máy và nguyên nhân thực tế ngược lại Database để làm giàu tri thức cho các ca sau.

---

## 2. SƠ ĐỒ KIẾN TRÚC TOÀN HỆ THỐNG (SYSTEM ARCHITECTURE)

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 1. DÂY CHUYỀN SẢN XUẤT (simulate_line.py)                              │
 │    - Bơm dữ liệu cảm biến: Nhiệt độ đầu hàn Sonotrode (130°C -> 152°C) │
 └──────────────────────────────────┬─────────────────────────────────────┘
                                    │ Stream (1.5s/tick)
                                    ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 2. TELEMETRY MONITOR WORKER (agent_daemon.py)                          │
 │    - Bộ đệm trượt (Sliding Window): Lọc nhiễu chống False Positive      │
 │    - Điều kiện kích hoạt: Nhiệt độ > 145°C trong 2 mẫu liên tiếp       │
 └──────────────────────────────────┬─────────────────────────────────────┘
                                    │ Phát hiện sự cố xác thực
                                    ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 3. AI AGENT REASONING CORE (agent_core.py)                             │
 │    - Não bộ: Google Gemini (gemini-3.6-flash)                          │
 │    - ReAct Loop: Điều phối 4 Tools kỹ thuật                            │
 └──────────────────┬──────────────────────────────────┬──────────────────┘
                    │ Tool 1: query_downtime_history   │ Tool 2: search_machine_manual
                    ▼                                  ▼
 ┌──────────────────────────────────────┐ ┌───────────────────────────────┐
 │ SQLite (packaging_factory.db)        │ │ ChromaDB (./chroma_db/)       │
 │ - Bảng: packaging_downtime_logs      │ │ - Collection: packaging_sops  │
 │ - Tra cứu: Tần suất lỗi, số phút dừng│ │ - Tra cứu ngữ nghĩa: Quy trình│
 │   trung bình, lịch sử thợ trước xử lý│ │   chuẩn LOTO & vệ sinh đầu hàn│
 └──────────────────────────────────────┘ └───────────────────────────────┘
                    │                                  │
                    └──────────────────┬───────────────┘
                                       │ Tổng hợp phương án & tạo Work Order
                                       ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 4. DETERMINISTIC VERIFICATION GUARDRAILS (factory_tools.py)            │
 │    - [Rule 1] Deduplication: Kiểm tra vé trùng lặp đã duyệt trong 60p  │
 │    - [Rule 2] Safety Gate: Bắt buộc từ khóa LOTO/ngắt nguồn nếu lỗi nhiệt│
 │    - [Rule 3] Schema Lock: severity bắt buộc thuộc P1/P2/P3 Enum       │
 │    ==> PASS 100%: Mới INSERT INTO maintenance_tickets (is_approved=1)  │
 └──────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │ 5. CLOSED-LOOP FEEDBACK & KNOWLEDGE REVISION                           │
 │    - Kỹ thuật viên thông báo sửa xong qua Chat (Natural Language)      │
 │    - Agent gọi Tool 4: close_maintenance_ticket                        │
 │    - Cập nhật ticket thành CLOSED_COMPLETED                            │
 │    - Tự động INSERT dòng log mới vào packaging_downtime_logs           │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 3. CẤU TRÚC THƯ MỤC VÀ VAI TRÒ TỪNG MODULE (FILE DIRECTORY)

```text
nestle-packaging-copilot/
├── data/
│   └── SOP_Packaging_Troubleshooting.md   # File SOP Markdown gốc (E-401, E-203, E-105)
├── chroma_db/                             # Vector Database cục bộ lưu trữ embeddings SOP
├── packaging_factory.db                   # Database SQLite chính của nhà máy
├── .env                                   # Chứa GEMINI_API_KEY (Được bảo mật bởi .gitignore)
├── .gitignore                             # Loại trừ .venv, __pycache__, .env
├── requirements.txt                       # Thư viện Python phụ thuộc
│
├── setup_database.py                      # [Setup] Khởi tạo trọn gói 3 bảng SQLite sạch sẽ
├── ingest_sop.py                          # [Setup] Tách đoạn và index SOP vào ChromaDB
│
├── factory_tools.py                       # [Core Engine] 4 Tools công nghiệp & Verification Guardrails
├── agent_core.py                          # [Core Engine] Não bộ AI Agent (Gemini Function Calling)
├── agent_daemon.py                        # [Service] Worker giám sát Telemetry & Lọc False Positive
└── simulate_line.py                       # [Simulator] Giả lập cảm biến PLC phát sinh sự cố
```

---

## 4. CHI TIẾT DỮ LIỆU & SCHEMA DATABASE

Database: `packaging_factory.db` (SQLite 3) gồm 3 bảng nghiệp vụ:
1. **`packaging_downtime_logs`**: Lịch sử các lần dừng máy trong quá khứ (dùng cho phân tích thống kê và tự học).
   - `log_id`, `timestamp`, `machine_id`, `error_code`, `duration_minutes`, `shift`, `technician_name`, `resolution_notes`.
2. **`machine_telemetry`**: Stream cảm biến mô phỏng dòng dữ liệu IoT/SCADA.
   - `id`, `timestamp`, `machine_id`, `sensor_name`, `sensor_value`, `unit`.
3. **`maintenance_tickets`**: Quản lý các phiếu lệnh bảo trì do Agent tự động tạo.
   - `ticket_id`, `created_at`, `machine_id`, `error_code`, `severity`, `safety_loto_required`, `assigned_technician`, `action_plan`, `verification_status`, `is_approved`.

---

## 5. HƯỚNG DẪN CHẠY KIỂM THỬ HỆ THỐNG (HOW TO RUN)

### Bước 1: Kích hoạt môi trường ảo
```bash
cd ~/nestle-packaging-copilot
source .venv/bin/activate
```

### Bước 2: Chạy hệ thống tự hành (Mở 2 Terminal)
- **Terminal 1 (Agent Daemon Worker):**
```bash
python agent_daemon.py
```
- **Terminal 2 (PLC Sensor Simulator):**
```bash
python simulate_line.py
```
- *Quan sát:* Gai nhiệt 146.5°C tại giây 5 bị lọc bỏ. Sự cố 152°C tại giây 10 kích hoạt Agent tự tạo phiếu `WO-XXXXXX` được duyệt an toàn. Nhấn `Ctrl + C` để dừng.

### Bước 3: Đóng Ticket bằng ngôn ngữ tự nhiên
Chạy terminal tương tác:
```bash
python agent_core.py
```
Nhập câu lệnh nghiệm thu:
> *"Tôi là KTV Hoàng, đã xử lý xong phiếu WO-XXXXXX. Nguyên nhân do van nước FS-02 bị kẹt rác, đã tháo súc rửa, dừng máy 25 phút. Hãy đóng ticket lại."*

Kiểm tra bảng lịch sử: `packaging_downtime_logs` sẽ được cộng thêm 1 dòng dữ liệu mới!

---

## 6. TIẾN ĐỘ DỰ ÁN & BƯỚC TIẾP THEO (HANDOFF ROADMAP)

### Đã hoàn thành (Done):
- [x] Thiết kế Dual-Data (SQLite + ChromaDB RAG).
- [x] Triển khai Resilient Embedder (Google GenAI + Local Fallback).
- [x] Xây dựng 4 Industrial Tools với Schema Enum chặt chẽ (P1-CRITICAL, P2-MEDIUM, P3-LOW).
- [x] Thiết lập Verification Guardrails (Deduplication Check, Safety LOTO Enforcement).
- [x] Lọc nhiễu False Positive trên luồng cảm biến.
- [x] Hoàn thiện vòng lặp đóng (Closed-loop feedback & learning).

### Bước tiếp theo cần triển khai (Next Sprint):
- [ ] **Giao diện Người dùng (UI / Microsoft Power Platform):**
  - Vì Nestlé sử dụng hệ sinh thái Microsoft, dự án hướng tới xây dựng giao diện **Microsoft Power Apps** cho Kỹ thuật viên hiện trường.
  - Xây dựng một **FastAPI Backend (`api_server.py`)** cung cấp REST Webhook để Power Apps / Power Automate có thể trigger Agent và hiển thị danh sách Ticket thời gian thực.

---

## 7. DÀNH CHO AI ASSISTANT Ở THREAD TIẾP THEO (PROMPT HANDOFF)

*Nếu bạn là AI tiếp nhận thread mới cho dự án này, hãy đọc kỹ chỉ dẫn sau:*
- Học viên là **Nguyễn Doãn Hoàng** (Data Analyst, cử nhân KHMT ĐH Bách Khoa ĐHQG-HCM), đang chuẩn bị phỏng vấn vị trí **Digital Technical Specialist tại Nestlé**.
- Mã nguồn của hệ thống đã hoàn chỉnh và chạy thông suốt ở tầng Core Engine (`agent_core.py`, `factory_tools.py`, `agent_daemon.py`).
- Không đề xuất viết lại code hay thay đổi kiến trúc cơ bản đã được kiểm chứng.
- Nhiệm vụ tiếp theo là: **Dựng một file `api_server.py` bằng FastAPI đơn giản (kết nối với các hàm trong `agent_core.py` và SQLite) để đóng vai trò Backend Gateway sẵn sàng tích hợp với Microsoft Power Apps / Power Automate.**
