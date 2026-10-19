# QA SPEC — Knife-Wear Unit Contract & Simulator Persistence

**Repository:** `NDHoang2003/nestle-packaging-copilot`

**Branch đề xuất:** `fix/knife-wear-unit-contract-qa`

**Mục tiêu:** Đảm bảo dữ liệu độ mòn dao cắt giữa AI4I historical dataset, simulator, SQLite database và HMI sử dụng đúng đơn vị, đúng schema và không gây lỗi runtime.

## 1. Data Contract

| Field | Unit | Source | Expected value |
|---|---|---|---|
| `cutting_knife_wear_min` | Minutes | AI4I 2020 historical dataset / ETL | Có giá trị với historical rows; NULL với simulator rows |
| `cutting_knife_wear_m` | Metres | `simulate_line.py` | NULL với historical rows; có giá trị với simulator rows |

Rules:
- Không ghi giá trị mét vào cột phút hoặc ngược lại.
- Không tự suy diễn công thức chuyển đổi giữa hai đơn vị.
- NULL có nghĩa là dữ liệu không áp dụng hoặc không được cung cấp, không phải giá trị 0.
- AI4I là public benchmark dataset, không phải telemetry trực tiếp từ nhà máy Nestlé.
- Ngưỡng mòn dao trong simulator là quy ước của mô hình demo, chưa được xác nhận là thông số kỹ thuật thực tế.

## 2. Acceptance Criteria

### `setup_database.py`
- Tạo cả hai cột `cutting_knife_wear_min` và `cutting_knife_wear_m`.
- Cho phép NULL để phân biệt nguồn dữ liệu.
- Historical rows giữ giá trị phút và để cột mét là NULL.
- Sử dụng explicit column list khi INSERT dữ liệu ETL.
- Giữ nguyên các bảng, indexes, foreign keys và các trường hiện có không liên quan đến thay đổi này.
- Lưu ý: chạy script có thể DROP và tạo lại các bảng, vì vậy chỉ sử dụng database demo hoặc bản sao có thể xóa.

### `simulate_line.py`
- Runtime frame sử dụng `cutting_knife_wear_m`.
- Khi ghi SQLite, cột `cutting_knife_wear_m` nhận giá trị mét; cột `cutting_knife_wear_min` nhận NULL.
- Tên cột INSERT phải khớp schema thực tế.
- Một lần `step()` thành công phải ghi đúng một telemetry row.
- Khi INSERT thất bại, lỗi phải được thông báo; không để lại bản ghi ghi dở hoặc trả về kết quả thành công giả.
- Giữ nguyên các frame fields mà HMI đang sử dụng, trừ khi có thay đổi contract được kiểm thử riêng.

### `app.py`
- Detector nhận `tool_wear` từ `frame["cutting_knife_wear_m"]`.
- HMI metric và progress bar hiển thị độ mòn bằng mét.
- Cảnh báo dao cắt sử dụng đúng key `cutting_knife_wear_m` và đơn vị `m`.
- Không còn truy cập `cutting_knife_wear_min` trên simulator frame.

## 3. QA Test Cases

**QA-WEAR-01 — Schema**
- Chạy database setup.
- Kiểm tra `PRAGMA table_info(fact_sensor_telemetry)`.
- Expected: cả hai cột wear tồn tại và hỗ trợ NULL.

**QA-WEAR-02 — Historical Data**
- Truy vấn historical rows sau ETL.
- Expected: cột phút có giá trị; cột mét là NULL.

**QA-WEAR-03 — Simulator Persistence**
- Chạy một simulator step trên bản sao database.
- Expected: số telemetry rows tăng đúng 1.

**QA-WEAR-04 — Wear Value Integrity**
- Đọc bản ghi vừa được simulator ghi.
- Expected: `cutting_knife_wear_min IS NULL`; `cutting_knife_wear_m` khớp giá trị frame trong sai số số học cho phép.

**QA-WEAR-05 — Required Fields**
- Kiểm tra các trường telemetry bắt buộc.
- Expected: các trường được điền đúng và tên cột khớp schema.

**QA-WEAR-06 — Database Integrity**
- Chạy `PRAGMA foreign_key_check` và `PRAGMA integrity_check`.
- Expected: không có lỗi foreign key; integrity result là `ok`.

**QA-WEAR-07 — Negative Persistence**
- Tạo trigger gây lỗi INSERT trên database tạm.
- Chạy simulator step.
- Expected: lỗi được thông báo và số bản ghi không tăng.

**QA-WEAR-08 — HMI Runtime**
- Khởi chạy Streamlit và chạy simulator.
- Expected: không có `KeyError`; wear metric và progress bar hiển thị bằng mét.

**QA-WEAR-09 — Wear Alert**
- Kích hoạt đường xử lý cảnh báo wear.
- Expected: cảnh báo dùng đúng key và hiển thị đơn vị `m`.

**QA-WEAR-10 — Source Database Safety**
- Tính SHA-256 database gốc trước và sau smoke test.
- Expected: hash không thay đổi vì các test phải chạy trên bản sao tạm.

## 4. Suggested Test Commands

Chạy từ repository root sau khi implementation đã được cập nhật:

```bash
python -m py_compile setup_database.py simulate_line.py app.py
python setup_database.py
python test_telemetry_persistance.py --db packaging_factory.db
streamlit run app.py
```

Lưu ý:
- `setup_database.py` có thể xóa và tạo lại các bảng demo.
- Persistence test phải dùng bản sao database, không ghi vào database nguồn.
- Kiểm tra test script hiện tại có thể cần cập nhật để dùng key `cutting_knife_wear_m`.
- Ghi nhận output thực tế. Không đánh dấu PASS chỉ dựa trên việc đọc code hoặc compile thành công.

## 5. Out of Scope
- Chuyển đổi phút thành mét.
- Xác nhận ngưỡng simulator với dữ liệu kỹ thuật thực tế.
- Khẳng định có tích hợp live PLC, SAP hoặc telemetry nhà máy.
- Sửa các luồng downtime/work order hoặc agent không liên quan đến contract này.

## 6. QA Reporting Format

Với mỗi test, ghi:
- Test ID
- Command hoặc thao tác UI
- Result: PASS / FAIL / BLOCKED
- Actual output hoặc hành vi quan sát được
- Evidence: log, SQL result hoặc screenshot
- Defect reference nếu thất bại

Chỉ đóng QA khi các test bắt buộc đã được chạy trên implementation cụ thể và có evidence.
