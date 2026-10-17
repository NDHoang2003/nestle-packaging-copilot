"""
agent_daemon.py
---------------
Autonomous Closed-Loop Industrial Daemon for Nestle Dong Nai Packaging Lines.
Orchestrates Degradation Engine, PLC Holding Registers, SAP PM Inventory, and ROI Ledger.

Standards:
- ISO 13374 Condition Monitoring / Diagnostics
- ISA-TR88 PackML / Modbus TCP Supervisory Handshake
- TPM Cost Deployment & Financial Cost Avoidance Tracking
"""

import os
import sys
import time
import sqlite3
from datetime import datetime
from typing import Dict, Any, Optional

from degradation_engine import DegradationDetector, DegradationState, DegradationAssessment
from factory_tools import (
    execute_line_derate,
    reserve_sap_spare_part,
    trigger_safety_interlock,
    create_autonomous_work_order,
    check_loto_thermal_gate,
    get_db_connection,
    get_table_columns
)
from roi_engine import roi_engine

DB_PATH = "packaging_factory.db"


class AutonomousPackagingDaemon:
    """
    Tiến trình điều phối tự trị khép kín (Autonomous Closed-Loop Orchestrator).
    Giám sát liên tục các dây chuyền đóng gói Tetra Pak & SIG Combibloc.
    """

    def __init__(self, db_path: str = DB_PATH, window_size: int = 15):
        self.db_path = db_path
        self.detector = DegradationDetector(window_size=window_size)
        # Bộ theo dõi trạng thái can thiệp để tránh trigger lặp lại liên tục
        self._machine_active_intervention: Dict[str, bool] = {}
        self._last_processed_id: int = 0

    def _sync_last_telemetry_id(self):
        """Đồng bộ ID telemetry cuối cùng trong DB để chỉ quét các bản ghi mới."""
        try:
            conn = get_db_connection(self.db_path)
            cursor = conn.cursor()
            cols = get_table_columns(cursor, "fact_sensor_telemetry")
            col_id = "telemetry_id" if "telemetry_id" in cols else ("id" if "id" in cols else None)
            if col_id:
                cursor.execute(f"SELECT MAX({col_id}) FROM fact_sensor_telemetry")
                max_id = cursor.fetchone()[0]
                self._last_processed_id = max_id or 0
            conn.close()
        except Exception:
            self._last_processed_id = 0

    def process_telemetry_frame(self, frame: Dict[str, Any]) -> Optional[DegradationAssessment]:
        """
        Xử lý 1 frame dữ liệu cảm biến và thực thi chu trình can thiệp tự trị.
        """
        machine_id = str(frame.get("line_id") or frame.get("machine_id") or "LINE_01")
        
        # 1. Bơm frame vào Degradation Detector
        assessment = self.detector.ingest_frame(machine_id, frame)
        
        # 2. Xử lý Trạng thái AMBER: Can thiệp dự báo tự trị (Predictive Intervention)
        if assessment.state == DegradationState.AMBER:
            if not self._machine_active_intervention.get(machine_id, False):
                print(f"\n================================================================================")
                print(f"🚨 [CẢNH BÁO SỚM AMBER PHÁT HIỆN]: Dây chuyền {machine_id}")
                print(f"📊 Điểm suy thoái: {assessment.degradation_score}% | Cửa sổ phân tích: {assessment.buffer_len} frames")
                for r in assessment.drift_reasons:
                    print(f"   ↳ ⚠️ {r}")

                # BƯỚC 2.1: Bắt tay PLC hạ tốc độ chạy cầm chừng (Limp-Home Derate: 24k -> 18k cph)
                derate_res = execute_line_derate(
                    machine_id=machine_id,
                    target_speed_cph=18000,
                    reason=f"Degradation Drift Detected: {assessment.drift_reasons[0]}"
                )
                print(f"⚡ [PLC HANDSHAKE]: Đã hạ tốc độ {machine_id} -> 18,000 cph (Giảm 25% ứng suất cơ nhiệt)")

                # BƯỚC 2.2: Tự động trừ kho và xuất phiếu lĩnh dao cắt mới SAP PM
                failure_mode = "CUTTER_WEAR" if "dao" in assessment.drift_reasons[0].lower() else "MECHANICAL_DRIFT"
                sap_res = reserve_sap_spare_part(machine_id=machine_id, failure_mode=failure_mode)
                slip = sap_res.get("requisition_slip", {})
                print(f"📦 [SAP PM KHO VẬT TƯ]: Đã xuất phiếu {slip.get('requisition_id')}")
                print(f"   ↳ Vật tư: {slip.get('part_name')} ({slip.get('sap_material_code')})")
                print(f"   ↳ Vị trí: {slip.get('shelf_location')} | Tồn kho sau trừ: {slip.get('remaining_warehouse_stock')} bộ")

                # BƯỚC 2.3: Tạo Phiếu công tác số hóa (Preventive Work Order)
                wo_res = create_autonomous_work_order(
                    machine_id=machine_id,
                    error_code="WARN-DRIFT-PREV",
                    summary=(
                        f"Bảo trì dự phòng: Dao mòn {assessment.metrics.get('curr_tool_wear', 0)}m. "
                        f"Đã chuẩn bị sẵn phụ tùng {slip.get('sap_material_code')} tại {slip.get('shelf_location')}."
                    ),
                    priority="HIGH",
                    assigned_to="Kỹ thuật viên Trực ca (Biên Hòa 2)"
                )
                print(f"📝 [WORK ORDER SỐ HÓA]: Đã tạo phiếu bảo trì {wo_res['work_order_id']}")

                # BƯỚC 2.4: Định lượng Giá trị Kinh tế & Hiệu quả TPM (ROI Ledger)
                roi_res = roi_engine.compute_intervention_roi(
                    machine_id=machine_id,
                    trigger_event="AUTONOMOUS_AMBER_DERATE_INTERVENTION",
                    work_order_ref=wo_res['work_order_id']
                )
                print(f"💰 [FINANCIAL ROI METRIC]:")
                print(f"   ↳ Thời gian dừng máy cứu được : {roi_res.downtime_saved_minutes} phút")
                print(f"   ↳ Sản lượng Milo bảo toàn     : {roi_res.units_saved:,} hộp")
                print(f"   ↳ TỔNG CHI PHÍ TRÁNH ĐƯỢC      : {roi_res.total_cost_avoidance_vnd:,.0f} VNĐ")
                print(f"================================================================================\n")

                self._machine_active_intervention[machine_id] = True

        # 3. Xử lý Trạng thái RED: Dừng bảo vệ khẩn cấp (Safety Interlock Latch)
        elif assessment.state == DegradationState.RED:
            print(f"\n💥💥💥 [SAFETY INTERLOCK TRIP]: DÂY CHUYỀN {machine_id} ĐÃ BỊ KHÓA AN TOÀN!")
            print(f"Lý do: {assessment.drift_reasons}")
            trigger_safety_interlock(
                machine_id=machine_id,
                reason=f"Degradation Critical Trip: {', '.join(assessment.drift_reasons)}"
            )
            # Kiểm tra ngay cổng an toàn nhiệt
            thermal = check_loto_thermal_gate(machine_id)
            print(f"🔒 [EHS LOTO GATE]: Nhiệt độ hiện tại: {thermal['current_temperature_celsius']}°C | Trạng thái: {thermal['status']}")

        # 4. Trạng thái GREEN: Reset trạng thái can thiệp khi máy đã ổn định trở lại
        elif assessment.state == DegradationState.GREEN:
            if self._machine_active_intervention.get(machine_id, False):
                self._machine_active_intervention[machine_id] = False

        return assessment

    def run_stream_replay(self, csv_path: str = "data/cleaned_telemetry.csv", target_line: str = "LINE_01", delay_sec: float = 0.2):
        import pandas as pd
        if not os.path.exists(csv_path):
            csv_path = "cleaned_telemetry.csv"

        df = pd.read_csv(csv_path)
        df_line = df[df["line_id"] == target_line].copy() if "line_id" in df.columns else df.copy()

        test_slice = df_line.head(26)

        print(f"🚀 BẮT ĐẦU CHẠY AUTONOMOUS DAEMON TRÊN LUỒNG DỮ LIỆU {target_line} ({len(test_slice)} frames)...")
        time.sleep(1.0)

        for idx, (_, row) in enumerate(test_slice.iterrows(), start=1):
            frame = {
                "line_id": target_line,
                "air_temp": float(row.get("ambient_temp_c", 25.0)),
                "process_temp": float(row.get("ultrasonic_temp_c", 36.0)),
                "rot_speed": float(row.get("rot_speed_rpm", 1500.0)),
                "torque": float(row.get("tension_torque_nm", 40.0)),
                "tool_wear": float(row.get("cutting_knife_wear_min", 0.0)),
                "p_mech": float(row.get("p_mech_kw", 6.0)),
                "delta_t": float(row.get("delta_t", 10.5)),
            }
            assessment = self.process_telemetry_frame(frame)
            
            icon = "🟢" if assessment.state == DegradationState.GREEN else ("🟡" if assessment.state == DegradationState.AMBER else "🔴")
            print(f"[{idx:02d}/26] Telemetry -> Wear: {frame['tool_wear']:5.1f}m | T: {frame['torque']:4.1f}Nm | {icon} State: {assessment.state.value:5s} | Score: {assessment.degradation_score:5.1f}%")
            
            # NẾU GẶP RED: CỖ MÁY NGẮT ĐIỆN VẬT LÝ, DỪNG TIẾN TRÌNH NGAY LẬP TỨC
            if assessment.state == DegradationState.RED:
                print("\n🛑 [EMERGENCY HARD STOP]: CƠ CHẾ INTERLOCK ĐÃ NGẮT HOÀN TOÀN DÂY CHUYỀN!")
                print(f"   ↳ Cắt nguồn biến tần servo | Xả khí nén xi-lanh kẹp dao")
                print(f"   ↳ Chuyển sang chế độ bảo trì an toàn EHS LOTO.")
                print(f"   ↳ Dừng nhận tín hiệu cảm biến cho đến khi hoàn tất thay thế linh kiện.")
                break

            time.sleep(delay_sec)

        print("\n🏁 KẾT THÚC VÒNG ĐỜI GIÁM SÁT DÂY CHUYỀN!")

if __name__ == "__main__":
    print("================================================================================")
    print("🏭 NESTLE VIETNAM - AUTONOMOUS PACKAGING COPILOT DAEMON (CLOSED-LOOP)")
    print("================================================================================")
    daemon = AutonomousPackagingDaemon(window_size=15)
    daemon.run_stream_replay(target_line="LINE_01", delay_sec=0.15)