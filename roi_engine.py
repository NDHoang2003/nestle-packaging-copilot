"""
roi_engine.py
-------------
Financial ROI & TPM Cost Avoidance Engine.
Quantifies business and production value saved by Autonomous Predictive Interventions
for Nestle Dong Nai Packaging Lines.

Standards:
- TPM Pillar: Cost Deployment & Autonomous Maintenance Impact
- OEE Availability & Production Loss Monetization
"""

import sqlite3
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List, Optional

DB_PATH = "packaging_factory.db"


@dataclass
class FinancialProfile:
    sku_name: str
    nominal_speed_cph: int                  # Công suất định mức (hộp/giờ)
    unit_retail_price_vnd: float            # Giá bán lẻ thành phẩm (VNĐ/hộp)
    unplanned_downtime_mins: float = 30.0   # Thời gian khắc phục sự cố sập máy đột ngột
    planned_swap_downtime_mins: float = 3.0 # Thời gian thay nhanh cụm dao có chuẩn bị
    scrap_packaging_cost_vnd: float = 7500000.0 # Chi phí hao hụt bao bì vô trùng khi kẹt giấy


# Cấu hình tài chính chuẩn xác cho từng Line của Nestlé Đồng Nai
LINE_FINANCIAL_PROFILES: Dict[str, FinancialProfile] = {
    "LINE_01": FinancialProfile(
        sku_name="Milo UHT 115ml Active-Go",
        nominal_speed_cph=24000,
        unit_retail_price_vnd=8000.0,
        unplanned_downtime_mins=30.0,
        planned_swap_downtime_mins=3.0,
        scrap_packaging_cost_vnd=7500000.0
    ),
    "LINE_02": FinancialProfile(
        sku_name="Milo UHT 180ml Standard Pack",
        nominal_speed_cph=18000,
        unit_retail_price_vnd=11000.0,
        unplanned_downtime_mins=35.0,
        planned_swap_downtime_mins=4.0,
        scrap_packaging_cost_vnd=9000000.0
    ),
    "LINE_03": FinancialProfile(
        sku_name="Nestle Pure Life 250ml Aseptic",
        nominal_speed_cph=15000,
        unit_retail_price_vnd=6000.0,
        unplanned_downtime_mins=25.0,
        planned_swap_downtime_mins=3.0,
        scrap_packaging_cost_vnd=5000000.0
    )
}


@dataclass
class ROICalculationResult:
    machine_id: str
    sku_name: str
    downtime_saved_minutes: float
    units_saved: int
    finished_goods_value_saved_vnd: float
    scrap_material_saved_vnd: float
    total_cost_avoidance_vnd: float
    calculation_timestamp: str


class ROIEngine:
    """
    Bộ tính toán ROI & Giá trị kinh tế công nghiệp.
    Định lượng số phút dừng máy, sản lượng hộp sữa và số tiền bảo toàn được
    mỗi khi Agent phát hiện sớm suy thoái và kích hoạt Limp-Home / Đặt phụ tùng SAP.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_roi_ledger_table()

    def _ensure_roi_ledger_table(self):
        """Khởi tạo bảng sổ cái tài chính fact_financial_roi_ledger nếu chưa có."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fact_financial_roi_ledger (
                    ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    machine_id TEXT NOT NULL,
                    sku_name TEXT NOT NULL,
                    downtime_saved_mins REAL NOT NULL,
                    units_saved INTEGER NOT NULL,
                    cost_avoidance_vnd REAL NOT NULL,
                    trigger_event TEXT NOT NULL,
                    sap_work_order_ref TEXT
                )
            """)
            conn.commit()
            conn.close()
        except Exception:
            pass

    def compute_intervention_roi(
        self, 
        machine_id: str, 
        trigger_event: str = "DEGRADATION_EARLY_CATCH",
        work_order_ref: Optional[str] = None
    ) -> ROICalculationResult:
        """
        Tính toán chính xác giá trị kinh tế bảo toàn cho 1 chu kỳ can thiệp dự báo.
        """
        profile = LINE_FINANCIAL_PROFILES.get(
            machine_id, 
            LINE_FINANCIAL_PROFILES["LINE_01"]
        )

        # 1. Số phút dừng máy được bảo toàn
        downtime_saved_mins = profile.unplanned_downtime_mins - profile.planned_swap_downtime_mins
        
        # 2. Số lượng hộp thành phẩm được cứu (Units Saved)
        boxes_per_minute = profile.nominal_speed_cph / 60.0
        units_saved = int(downtime_saved_mins * boxes_per_minute)

        # 3. Giá trị tiền tệ thành phẩm (VNĐ)
        finished_goods_value = units_saved * profile.unit_retail_price_vnd

        # 4. Giá trị hao hụt bao bì phế liệu được tránh (Scrap Avoidance)
        scrap_saved = profile.scrap_packaging_cost_vnd

        # 5. Tổng giá trị kinh tế bảo toàn (Total Cost Avoidance)
        total_cost_avoidance = finished_goods_value + scrap_saved

        result = ROICalculationResult(
            machine_id=machine_id,
            sku_name=profile.sku_name,
            downtime_saved_minutes=round(downtime_saved_mins, 1),
            units_saved=units_saved,
            finished_goods_value_saved_vnd=finished_goods_value,
            scrap_material_saved_vnd=scrap_saved,
            total_cost_avoidance_vnd=total_cost_avoidance,
            calculation_timestamp=datetime.now().isoformat()
        )

        # Ghi nhận vào Sổ cái tài chính SQLite
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO fact_financial_roi_ledger (
                    machine_id, sku_name, downtime_saved_mins, 
                    units_saved, cost_avoidance_vnd, trigger_event, sap_work_order_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                machine_id, profile.sku_name, downtime_saved_mins,
                units_saved, total_cost_avoidance, trigger_event, work_order_ref
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass

        return result

    def get_factory_cumulative_roi(self) -> Dict[str, Any]:
        """Tổng hợp toàn bộ giá trị kinh tế đã bảo toàn được cho toàn bộ nhà máy."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_interventions,
                    SUM(downtime_saved_mins) as total_downtime_saved_mins,
                    SUM(units_saved) as total_units_saved,
                    SUM(cost_avoidance_vnd) as total_cost_avoidance_vnd
                FROM fact_financial_roi_ledger
            """)
            row = cursor.fetchone()
            conn.close()

            if row and row["total_interventions"] > 0:
                return {
                    "total_interventions": row["total_interventions"],
                    "total_downtime_saved_hours": round((row["total_downtime_saved_mins"] or 0.0) / 60.0, 1),
                    "total_units_saved": int(row["total_units_saved"] or 0),
                    "total_cost_avoidance_vnd": float(row["total_cost_avoidance_vnd"] or 0.0)
                }
        except Exception:
            pass

        return {
            "total_interventions": 0,
            "total_downtime_saved_hours": 0.0,
            "total_units_saved": 0,
            "total_cost_avoidance_vnd": 0.0
        }


# Singleton sẵn sàng sử dụng
roi_engine = ROIEngine()


if __name__ == "__main__":
    print("================================================================================")
    print("💰 KIỂM THỬ ĐỊNH LƯỢNG GIÁ TRỊ KINH TẾ ROI & TPM (NESTLE DONG NAI FACTORY)")
    print("================================================================================")

    engine = ROIEngine()
    
    # Giả lập 1 can thiệp dự báo cho LINE_01 (Tetra Pak Milo 115ml)
    res_line1 = engine.compute_intervention_roi(
        machine_id="LINE_01",
        trigger_event="DEGRADATION_DRIFT_PREVENTION",
        work_order_ref="WO-LINE_01-PREVENTIVE-01"
    )

    print(f"\n📦 Dây chuyền phân tích      : {res_line1.machine_id} ({res_line1.sku_name})")
    print(f"⏱️ Thời gian dừng máy cứu được : {res_line1.downtime_saved_minutes} phút (30p sự cố -> 3p kế hoạch)")
    print(f"🥛 Sản lượng Milo bảo toàn    : {res_line1.units_saved:,} hộp")
    print(f"💵 Giá trị sản phẩm cứu được  : {res_line1.finished_goods_value_saved_vnd:,.0f} VNĐ")
    print(f"📜 Tiết kiệm phế liệu bao bì : {res_line1.scrap_material_saved_vnd:,.0f} VNĐ")
    print(f"🏆 TỔNG CHI PHÍ TRÁNH ĐƯỢC (COST AVOIDANCE): {res_line1.total_cost_avoidance_vnd:,.0f} VNĐ")

    # Giả lập 1 can thiệp cho LINE_02 (Milo 180ml)
    res_line2 = engine.compute_intervention_roi(
        machine_id="LINE_02",
        trigger_event="THERMAL_CHILLER_DEGRADATION",
        work_order_ref="WO-LINE_02-PREVENTIVE-02"
    )

    # Đọc tổng lũy kế toàn nhà máy
    cumulative = engine.get_factory_cumulative_roi()
    print("\n--------------------------------------------------------------------------------")
    print("🏢 TỔNG LŨY KẾ TIẾT KIỆM TOÀN NHÀ MÁY NESTLÉ ĐỒNG NAI:")
    print(f"🎯 Số lần can thiệp tự trị thành công : {cumulative['total_interventions']} lần")
    print(f"⏳ Tổng thời gian dừng máy đã cứu     : {cumulative['total_downtime_saved_hours']} giờ")
    print(f"📦 Tổng sản lượng thành phẩm bảo toàn : {cumulative['total_units_saved']:,} hộp")
    print(f"💎 TỔNG GIÁ TRỊ TÀI CHÍNH BẢO TOÀN     : {cumulative['total_cost_avoidance_vnd']:,.0f} VNĐ")
    print("================================================================================")