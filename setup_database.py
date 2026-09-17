import sqlite3
import os

DB_PATH = "packaging_factory.db"

def init_database():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"[*] Đã xóa database cũ để làm mới: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Bảng lịch sử sự cố nhà máy (Downtime Logs)
    cursor.execute("""
    CREATE TABLE packaging_downtime_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        machine_id TEXT NOT NULL,
        error_code TEXT NOT NULL,
        duration_minutes INTEGER NOT NULL,
        shift TEXT NOT NULL,
        technician_name TEXT NOT NULL,
        resolution_notes TEXT NOT NULL
    );
    """)

    # 2. Bảng stream cảm biến SCADA/IoT (Time-series Telemetry)
    cursor.execute("""
    CREATE TABLE machine_telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        machine_id TEXT NOT NULL,
        sensor_name TEXT NOT NULL,
        sensor_value REAL NOT NULL,
        unit TEXT NOT NULL
    );
    """)

    # 3. Bảng quản lý phiếu bảo trì (Closed-Loop Maintenance Tickets)
    cursor.execute("""
    CREATE TABLE maintenance_tickets (
        ticket_id TEXT PRIMARY KEY,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        machine_id TEXT NOT NULL,
        error_code TEXT NOT NULL,
        severity TEXT NOT NULL,
        safety_loto_required BOOLEAN NOT NULL,
        assigned_technician TEXT NOT NULL,
        action_plan TEXT NOT NULL,
        verification_status TEXT NOT NULL,
        is_approved BOOLEAN DEFAULT 0
    );
    """)

    # Nạp sẵn dữ liệu lịch sử ban đầu
    sample_logs = [
        ("2026-03-01 07:45:00", "PKG-LINE-01", "E-401", 45, "Ca 1 (Sang)", "Nguyen Van A", "Nuoc lam mat bi nghen can hoa chat, da suc rua cam bien"),
        ("2026-03-02 14:15:00", "PKG-LINE-01", "E-203", 20, "Ca 2 (Chieu)", "Tran Thi B", "Cam bien quang PE-101 bam bui bot giay, da ve sinh"),
        ("2026-03-05 22:30:00", "PKG-LINE-02", "E-401", 60, "Ca 3 (Dem)", "Le Van C", "Sonotrode bi bam can mang nhua, tay bang con IPA va khoi dong lai"),
        ("2026-03-07 09:10:00", "PKG-LINE-01", "E-105", 15, "Ca 1 (Sang)", "Nguyen Van A", "Ket 2 vo hop Milo 180ml o khau chuyen huong, da go keo"),
        ("2026-03-08 19:40:00", "PKG-LINE-02", "E-401", 50, "Ca 2 (Chieu)", "Tran Thi B", "Loi bom lam mat FS-02 hoat dong yeu, da bao tri bom"),
        ("2026-03-10 03:20:00", "PKG-LINE-02", "E-203", 35, "Ca 3 (Dem)", "Le Van C", "Cuon mang bi lech luc thay cuon moi, can chinh luc cang len 20N"),
        ("2026-03-11 11:05:00", "PKG-LINE-01", "E-401", 40, "Ca 1 (Sang)", "Nguyen Van A", "Qua nhiet sonotrode nhe, cho nguoi va lau mat tiep xuc"),
        ("2026-03-12 16:50:00", "PKG-LINE-02", "E-105", 25, "Ca 2 (Chieu)", "Tran Thi B", "Vo hop bi rach ket tai thanh gat, da lay di vat")
    ]

    cursor.executemany("""
    INSERT INTO packaging_downtime_logs 
    (timestamp, machine_id, error_code, duration_minutes, shift, technician_name, resolution_notes)
    VALUES (?, ?, ?, ?, ?, ?, ?);
    """, sample_logs)

    conn.commit()
    print("[+] Khởi tạo thành công toàn bộ Database với 3 bảng tiêu chuẩn!")
    conn.close()

if __name__ == "__main__":
    init_database()
