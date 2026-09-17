import sqlite3
import time
import random

DB_PATH = "packaging_factory.db"

def insert_reading(machine_id: str, sensor_name: str, value: float, unit: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO machine_telemetry (machine_id, sensor_name, sensor_value, unit)
        VALUES (?, ?, ?, ?)
    """, (machine_id, sensor_name, round(value, 1), unit))
    conn.commit()
    conn.close()

def run_simulation():
    print("🏭 [PLC SIMULATOR]: Bắt đầu truyền dữ liệu cảm biến nhiệt độ đầu hàn Line 01...")
    print("👉 Nhấn Ctrl+C để dừng mô phỏng.\n")
    
    tick = 0
    while True:
        tick += 1
        
        # Mặc định: Máy chạy bình thường (~130°C)
        temp = random.uniform(129.0, 132.5)
        
        # Giây thứ 5: Giả lập 1 xung nhiễu điện cực 1 tick (Test False Positive)
        if tick == 5:
            temp = 146.5
            print(f"⚠️  [SIMULATOR]: Bơm 1 xung nhiễu đo đạc: {temp}°C (Cần lọc False Positive!)")
            
        # Từ giây thứ 10 trở đi: Bơm sự cố quá nhiệt thật sự (Liền tù tì vượt 145°C)
        elif tick >= 10:
            temp = random.uniform(151.0, 156.0)
            print(f"🔥 [SIMULATOR]: SỰ CỐ QUÁ NHIỆT ĐẦU HÀN ĐANG DIỄN RA: {temp}°C !!")
        else:
            print(f"🟢 [SIMULATOR]: Line 01 hoat dong on dinh: {temp:.1f}°C")

        insert_reading("PKG-LINE-01", "Sonotrode_Sealing_Temp", temp, "°C")
        time.sleep(1.5)

if __name__ == "__main__":
    run_simulation()
