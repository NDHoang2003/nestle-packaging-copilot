"""
test_degradation_from_csv.py
----------------------------
Kiểm thử tích hợp DegradationDetector trên dữ liệu chuỗi thời gian đơn máy (Asset-isolated).
Tách riêng dữ liệu của từng Line máy đóng gói (LINE_01) để tránh nhiễm chéo phương sai.
"""

import os
import sys
import pandas as pd
from degradation_engine import DegradationDetector, DegradationState

CSV_PATH = "data/cleaned_telemetry.csv"
if not os.path.exists(CSV_PATH):
    CSV_PATH = "cleaned_telemetry.csv"


def find_column(df: pd.DataFrame, candidates: list) -> str:
    for cand in candidates:
        if cand in df.columns:
            return cand
    for col in df.columns:
        for cand in candidates:
            if cand.lower() in col.lower():
                return col
    return ""


def run_csv_degradation_test():
    if not os.path.exists(CSV_PATH):
        print(f"❌ Không tìm thấy file dữ liệu tại '{CSV_PATH}'!")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH)
    print(f"📂 Đã nạp thành công '{CSV_PATH}': {len(df):,} dòng dữ liệu.")

    # 1. Nhận diện các cột
    col_machine = find_column(df, ["line_id", "machine_id", "Line", "machine"])
    col_wear = find_column(df, ["cutting_knife_wear_min", "tool_wear", "Tool wear"])
    col_torque = find_column(df, ["tension_torque_nm", "torque", "Torque"])
    col_speed = find_column(df, ["rot_speed", "rotational_speed", "Speed"])
    col_proc_temp = find_column(df, ["process_temp", "Process temperature"])
    col_air_temp = find_column(df, ["air_temp", "Air temperature"])
    col_pmech = find_column(df, ["p_mech_kw", "p_mech", "P_mech"])
    col_deltat = find_column(df, ["delta_t", "Delta_T"])
    col_failure = find_column(df, ["is_failure", "Machine failure", "Target", "failure"])

    print(f"🔎 Cấu trúc nhận diện: Line Col: '{col_machine}' | Wear: '{col_wear}' | Torque: '{col_torque}' | Failure: '{col_failure}'")

    # 2. Tìm điểm sự cố và xác định chính xác máy bị sự cố
    fail_rows = df[df[col_failure] == 1]
    if fail_rows.empty:
        print("⚠️ Không tìm thấy dòng có sự cố (is_failure == 1). Sẽ chạy trên LINE_01 mặc định.")
        target_line = "LINE_01"
        target_idx = df.index[-1]
    else:
        first_fail = fail_rows.iloc[0]
        target_idx = first_fail.name
        target_line = str(first_fail[col_machine]) if col_machine else "LINE_01"
        print(f"🎯 Phát hiện sự cố tại Index #{target_idx} trên DÂY CHUYỀN: {target_line}")

    # 3. LỌC RIÊNG DỮ LIỆU CỦA ĐÚNG DÂY CHUYỀN ĐÓ (Tránh nhiễm chéo dữ liệu)
    df_line = df[df[col_machine] == target_line].copy() if col_machine else df.copy()
    
    # Lấy chuỗi dữ liệu dẫn tới sự cố trên line này
    sub_fail_indices = df_line.index[df_line[col_failure] == 1].tolist()
    if sub_fail_indices:
        line_fail_idx = sub_fail_indices[0]
        # Lấy tối đa 35 điểm trước sự cố của máy đó
        line_positions = df_line.index.get_loc(line_fail_idx)
        start_pos = max(0, line_positions - 30)
        end_pos = min(len(df_line), line_positions + 3)
        test_slice = df_line.iloc[start_pos:end_pos].copy()
    else:
        test_slice = df_line.tail(30).copy()

    print(f"\n================================================================================")
    print(f"🔬 KIỂM THỬ CHUỖI SUY THOÁI CHUẨN ĐƠN MÁY (ISOLATED ASSET): {target_line}")
    print(f"   Số lượng frames phân tích: {len(test_slice)} frames liên tục của {target_line}")
    print(f"================================================================================")

    detector = DegradationDetector(window_size=15)
    results = []

    for idx, (orig_idx, row) in enumerate(test_slice.iterrows(), start=1):
        wear_val = float(row[col_wear]) if col_wear else 0.0
        torque_val = float(row[col_torque]) if col_torque else 40.0
        speed_val = float(row[col_speed]) if col_speed else 1500.0
        proc_val = float(row[col_proc_temp]) if col_proc_temp else 310.0
        air_val = float(row[col_air_temp]) if col_air_temp else 300.0
        pmech_val = float(row[col_pmech]) if col_pmech else (2 * 3.14159 * speed_val * torque_val / 60000.0)
        deltat_val = float(row[col_deltat]) if col_deltat else (proc_val - air_val)
        is_fail = int(row[col_failure]) if col_failure else 0

        frame = {
            "air_temp": air_val,
            "process_temp": proc_val,
            "rot_speed": speed_val,
            "torque": torque_val,
            "tool_wear": wear_val,
            "p_mech": pmech_val,
            "delta_t": deltat_val,
        }

        assessment = detector.ingest_frame(target_line, frame)
        results.append(assessment)

        icon = "🟢" if assessment.state == DegradationState.GREEN else ("🟡" if assessment.state == DegradationState.AMBER else "🔴")
        fail_flag = "💥 [TRIP EVENT]" if is_fail == 1 else ""

        print(f"#{orig_idx:03d} | Wear:{wear_val:5.1f}m | T:{torque_val:4.1f}Nm | "
              f"P:{pmech_val:4.2f}kW | {icon} {assessment.state.value:5s} | "
              f"Score:{assessment.degradation_score:5.1f}% {fail_flag}")

        if assessment.drift_reasons:
            for r in assessment.drift_reasons:
                print(f"       ↳ ⚠️ {r}")

    amber_count = sum(1 for a in results if a.state == DegradationState.AMBER)
    red_count = sum(1 for a in results if a.state == DegradationState.RED)
    
    print("\n--------------------------------------------------------------------------------")
    print(f"📊 TỔNG KẾT SUY THOÁI CHO MÁY {target_line}:")
    print(f"- Số frame GREEN (Hoạt động ổn định): {sum(1 for a in results if a.state == DegradationState.GREEN)}")
    print(f"- Số frame AMBER (Cảnh báo sớm / Đặt phụ tùng / Giảm tải): {amber_count}")
    print(f"- Số frame RED   (Khóa liên động / Dừng bảo vệ): {red_count}")
    print("================================================================================\n")


if __name__ == "__main__":
    run_csv_degradation_test()