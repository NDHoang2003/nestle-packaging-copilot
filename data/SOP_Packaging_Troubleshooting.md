# STANDARD OPERATING PROCEDURE (SOP) - PACKAGING LINE TROUBLESHOOTING
# Factory: Nestlé Tri Ton / Dong Nai Plant
# Equipment: High-Speed Aseptic Carton Packaging System

---

## 1. MÃ LỖI: E-401 - ULTRASONIC SEALING OVERHEAT (QUÁ NHIỆT MỐI HÀN SIÊU ÂM)
- **Mô tả:** Nhiệt độ tại đầu đe hàn siêu âm dọc của hộp carton vượt ngưỡng 145°C. Hệ thống tự ngắt bảo vệ bao bì.
- **Nguy cơ an toàn:** Bỏng nhiệt, chập cháy điện trở.
- **Quy trình xử lý chuẩn (Standard Procedure):**
  1. **Bước 1 (LOTO):** Thực hiện ngắt nguồn khẩn cấp và gắn thẻ cảnh báo Lockout/Tagout tại tủ điện chính Line 02.
  2. **Bước 2 (Kiểm tra tản nhiệt):** Đợi đầu hàn hạ nhiệt dưới 60°C. Kiểm tra lưu lượng nước làm mát tuần hoàn qua cảm biến Flow Sensor FS-02. Lưu lượng chuẩn: 2.5 - 3.2 L/min.
  3. **Bước 3 (Vệ sinh đầu hàn Sonotrode):** Dùng bàn chải đồng và cồn công nghiệp IPA 99% vệ sinh sạch cặn màng polyethylene bám dính trên mặt tiếp xúc.
  4. **Bước 4 (Hiệu chuẩn):** Dùng súng đo nhiệt hồng ngoại kiểm tra đối chiếu với thông số nhiệt độ hiển thị trên màn hình HMI. Sai lệch cho phép: ±2°C.

---

## 2. MÃ LỖI: E-203 - PACKAGING FILM WEB MISALIGNMENT (LỆCH MÀNG CUỘN)
- **Mô tả:** Cảm biến quang phát hiện mép màng cuộn carton/bao bì lệch quá 2.5mm so với tâm dẫn hướng trong 3 chu kỳ dập liên tiếp.
- **Nguy cơ an toàn:** Kẹt cơ khí, đứt màng, dập hỏng dao cắt.
- **Quy trình xử lý chuẩn (Standard Procedure):**
  1. **Bước 1:** Nhấn nút Dừng Chu Kỳ (Cycle Pause). Không dùng nút dừng khẩn cấp E-Stop nếu không nguy hiểm để tránh lệch bước servo.
  2. **Bước 2:** Mở nắp khoang nạp màng. Kiểm tra lực căng màng (Tension Arm Sensor). Đồng hồ đo lực căng phải nằm trong dải 18 - 22 N.
  3. **Bước 3:** Kiểm tra bụi bột giấy bám trên mắt đọc cảm biến quang OMRON PE-101. Dùng khăn vi sợi (microfiber) khô lau nhẹ.
  4. **Bước 4:** Bấm nút "Manual Jog Web" trên HMI để màng chạy chậm 500mm, quan sát vạch canh lề Laser Guide. Khi vạch xanh nằm giữa chỉ thị thì bấm "Auto Re-align".

---

## 3. MÃ LỖI: E-105 - INFEED SERVO CONVEYOR JAM (KẸT BĂNG TẢI CẤP LIỆU)
- **Mô tả:** Động cơ servo băng tải nạp sản phẩm bị quá dòng (Overcurrent) do kẹt vỏ hộp hoặc dị vật tại khâu chuyển tiếp.
- **Nguy cơ an toàn:** Biến dạng ray trượt, quá tải cháy động cơ servo.
- **Quy trình xử lý chuẩn (Standard Procedure):**
  1. **Bước 1:** Bấm E-Stop lập tức.
  2. **Bước 2:** Mở cửa an toàn interlock khu vực nạp sản phẩm.
  3. **Bước 3:** Quan sát đĩa xích tải và thanh gạt phân làn (Lane Diverter). Dùng găng tay chịu lực lấy vỏ hộp bị móp kẹt ra ngoài.
  4. **Bước 4:** Xoay trục băng tải bằng tay kiểm tra độ trơn tru cơ học. Reset còi báo lỗi trên HMI và chạy thử không tải (Dry Run) 30 giây.
