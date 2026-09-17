import time
import sqlite3
# TÁI SỬ DỤNG HOÀN TOÀN NÃO BỘ TỪ AGENT_CORE (KHÔNG TRÙNG LẶP CODE)
from agent_core import diagnose_and_act

DB_PATH = "packaging_factory.db"
TEMP_THRESHOLD = 145.0  # Ngưỡng an toàn theo quy chuẩn kỹ thuật

def get_latest_telemetry(limit=2):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, timestamp, machine_id, sensor_name, sensor_value 
        FROM machine_telemetry 
        ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def monitor_loop():
    print("=" * 65)
    print("👁️  [TELEMETRY MONITOR WORKER]: Đang giám sát stream cảm biến...")
    print(f"🎯 Ngưỡng cảnh báo: {TEMP_THRESHOLD}°C | Thuật toán lọc: 2 mẫu liên tiếp")
    print("=" * 65)

    last_processed_id = 0
    incident_locked = False # Tránh spam khi sự cố đang diễn ra chưa được reset

    while True:
        rows = get_latest_telemetry(limit=2)
        if len(rows) >= 2:
            latest, previous = rows[0], rows[1]
            latest_id = latest[0]

            if latest_id > last_processed_id:
                val1, val2 = latest[4], previous[4]
                machine_id, sensor_name = latest[2], latest[3]

                # BỘ LỌC CHỐNG FALSE POSITIVE: Phải có 2 mẫu liên tiếp vượt ngưỡng
                if val1 > TEMP_THRESHOLD and val2 > TEMP_THRESHOLD:
                    if not incident_locked:
                        avg_val = round((val1 + val2) / 2, 1)
                        print(f"\n🚨 [SỰ CỐ XÁC THỰC]: {sensor_name} tại {machine_id} = {avg_val}°C!")
                        print("🚀 Đang đánh thức AI Agent từ 'agent_core' để xử lý...")

                        # Gọi não bộ từ agent_core
                        event_msg = f"SỰ CỐ KHẨN CẤP: Dây chuyền {machine_id} có cảm biến {sensor_name} đạt {avg_val}°C (Vượt ngưỡng {TEMP_THRESHOLD}°C liên tiếp). Hãy điều tra SOP, tra cứu SQL và xuất phiếu sửa chữa ngay!"
                        solution = diagnose_and_act(event_msg)

                        print("\n📢 [BÁO CÁO CỨU NGUY VÀ HƯỚNG DẪN XỬ LÝ]:")
                        print(solution)
                        print("\n" + "=" * 65)
                        incident_locked = True
                
                elif val1 > TEMP_THRESHOLD and val2 <= TEMP_THRESHOLD:
                    print(f"🔍 [LỌC NHIỄU]: Phát hiện gai nhiệt {val1}°C (mẫu trước {val2}°C). Bỏ qua (Chống False Positive)!")
                
                else:
                    if incident_locked:
                        print("✅ Dây chuyền đã hạ nhiệt an toàn. Mở lại chế độ giám sát.")
                        incident_locked = False

                last_processed_id = latest_id

        time.sleep(1.5)

if __name__ == "__main__":
    monitor_loop()
