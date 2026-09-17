import sqlite3
import chromadb
import uuid
from typing import Optional, Tuple, Literal
from ingest_sop import ResilientFactoryEmbedder, CHROMA_DATA_PATH, COLLECTION_NAME, GEMINI_API_KEY

DB_PATH = "packaging_factory.db"

# --- TOOL 1: TRUY VẤN SQLITE LỊCH SỬ DỪNG MÁY ---
def query_downtime_history(error_code: str) -> dict:
    error_code = error_code.strip().upper()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*), AVG(duration_minutes), SUM(duration_minutes)
        FROM packaging_downtime_logs
        WHERE UPPER(error_code) = ?
    """, (error_code,))
    count, avg_duration, total_duration = cursor.fetchone()

    if count == 0:
        conn.close()
        return {"status": "NOT_FOUND", "message": f"Chưa có lịch sử dừng máy cho mã lỗi {error_code}"}

    cursor.execute("""
        SELECT timestamp, machine_id, shift, duration_minutes, technician_name, resolution_notes
        FROM packaging_downtime_logs
        WHERE UPPER(error_code) = ?
        ORDER BY timestamp DESC
        LIMIT 3
    """, (error_code,))
    recent_logs = cursor.fetchall()
    conn.close()

    return {
        "status": "SUCCESS",
        "error_code": error_code,
        "total_occurrences": count,
        "avg_downtime_minutes": round(avg_duration, 1) if avg_duration else 0,
        "total_downtime_minutes": total_duration,
        "recent_repair_notes": [
            {"time": r[0], "line": r[1], "shift": r[2], "downtime": r[3], "tech": r[4], "note": r[5]}
            for r in recent_logs
        ]
    }

# --- TOOL 2: TRUY VẤN CHROMADB TÌM QUY TRÌNH SOP ---
def search_machine_manual(query: str, error_code: Optional[str] = None) -> dict:
    embedder = ResilientFactoryEmbedder(api_key=GEMINI_API_KEY)
    client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)
    collection = client.get_collection(name=COLLECTION_NAME, embedding_function=embedder)

    where_filter = {"error_code": error_code.strip().upper()} if error_code else None

    results = collection.query(
        query_texts=[query],
        n_results=1,
        where=where_filter
    )

    if not results['documents'] or not results['documents'][0]:
        return {"status": "NOT_FOUND", "message": "Không tìm thấy SOP phù hợp."}

    return {
        "status": "SUCCESS",
        "matched_error_code": results['metadatas'][0][0].get("error_code"),
        "sop_content": results['documents'][0][0]
    }

# --- TOOL 3: TẠO PHIẾU BẢO TRÌ (SCHEMA KHÓA CHẶT BẰNG LITERAL ENUM) ---
def create_maintenance_work_order(
    machine_id: str, 
    error_code: str, 
    severity: Literal["P1-CRITICAL", "P2-MEDIUM", "P3-LOW"], 
    assigned_technician: str, 
    action_plan: str
) -> dict:
    """
    Tạo Phiếu Lệnh Bảo Trì vào hệ thống.
    severity: BẮT BUỘC chọn 1 trong 3 giá trị: 'P1-CRITICAL', 'P2-MEDIUM', hoặc 'P3-LOW'.
    action_plan: Bắt buộc nêu rõ quy trình an toàn ngắt nguồn LOTO đối với sự cố nhiệt/điện.
    """
    error_code = error_code.strip().upper()
    
    # 1. KIỂM THỬ TRÙNG LẶP (Deduplication Check)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM maintenance_tickets 
        WHERE machine_id = ? AND error_code = ? 
        AND is_approved = 1
        AND created_at >= datetime('now', '-60 minutes')
    """, (machine_id, error_code))
    dup_count = cursor.fetchone()[0]

    if dup_count > 0:
        conn.close()
        return {
            "status": "REJECTED",
            "message": f"Từ chối tạo phiếu: Đã có phiếu bảo trì đang hoạt động cho {machine_id} trong 60 phút qua."
        }

    # 2. KIỂM THỬ AN TOÀN LOTO (Safety Gate)
    high_risk_codes = ["E-401", "E-105"]
    plan_lower = action_plan.lower()
    if error_code in high_risk_codes and not any(kw in plan_lower for kw in ["loto", "lockout", "ngắt nguồn", "e-stop"]):
        conn.close()
        return {
            "status": "REJECTED",
            "message": f"Từ chối tạo phiếu: Sự cố {error_code} vi phạm an toàn vì thiếu quy trình LOTO/ngắt nguồn trong action_plan!"
        }

    # 3. KHI TẤT CẢ ĐỀU HỢP LỆ -> MỚI ĐƯỢC PHÉP INSERT VÀO DATABASE
    ticket_id = f"WO-{uuid.uuid4().hex[:6].upper()}"
    has_loto = any(kw in plan_lower for kw in ["loto", "lockout", "ngắt nguồn", "e-stop"])

    cursor.execute("""
        INSERT INTO maintenance_tickets 
        (ticket_id, machine_id, error_code, severity, safety_loto_required, assigned_technician, action_plan, verification_status, is_approved)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'VERIFIED_PASSED', 1)
    """, (ticket_id, machine_id, error_code, severity, has_loto, assigned_technician, action_plan))
    
    conn.commit()
    conn.close()

    return {
        "status": "SUCCESS",
        "ticket_id": ticket_id,
        "message": f"Phiếu bảo trì {ticket_id} đạt chuẩn an toàn LOTO và đã được phê duyệt ghi nhận vào Database."
    }

# --- TOOL 4: ĐÓNG PHIẾU BẢO TRÌ ---
def close_maintenance_ticket(ticket_id: str, technician_name: str, actual_downtime_minutes: int, root_cause_and_action: str) -> dict:
    ticket_id = ticket_id.strip().upper()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT machine_id, error_code, is_approved FROM maintenance_tickets WHERE ticket_id = ?", (ticket_id,))
    ticket = cursor.fetchone()

    if not ticket:
        conn.close()
        return {"status": "ERROR", "message": f"Không tìm thấy phiếu {ticket_id}"}

    machine_id, error_code, _ = ticket

    cursor.execute("""
        UPDATE maintenance_tickets 
        SET verification_status = 'CLOSED_COMPLETED', action_plan = action_plan || ' | GHI CHU KET THUC: ' || ?
        WHERE ticket_id = ?
    """, (root_cause_and_action, ticket_id))

    cursor.execute("""
        INSERT INTO packaging_downtime_logs 
        (machine_id, error_code, duration_minutes, shift, technician_name, resolution_notes)
        VALUES (?, ?, ?, 'Ca Hien Tai', ?, ?)
    """, (machine_id, error_code, actual_downtime_minutes, technician_name, root_cause_and_action))

    conn.commit()
    conn.close()

    return {
        "status": "SUCCESS",
        "ticket_id": ticket_id,
        "message": f"Đã đóng thành công phiếu {ticket_id} và cập nhật {actual_downtime_minutes} phút vào lịch sử nhà máy."
    }
