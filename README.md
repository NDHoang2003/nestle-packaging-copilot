# 🏭 Nestlé Packaging Digital Twin & AI Copilot
### Autonomous Predictive Maintenance & Closed-Loop Intervention System
**Target Deployment:** Nestlé Dong Nai Factory (Bien Hoa 2 Industrial Zone)  
**Candidate:** Nguyen Doan Hoang (Computer Science, HCMC University of Technology - VNU-HCM)  
**Reporting Line:** Manufacturing Excellence Manager (TPM / OEE / Lean / EHS)

---

## 📌 Executive Summary
In high-speed aseptic beverage packaging lines (Tetra Pak A3/Speed running at **24,000 packs/hour** for Milo UHT 115ml), unplanned downtime due to mechanical cutting knife fractures causes catastrophic losses: paper jamming, product spillage, sterile chamber contamination, and an average of **30 minutes** of unplanned downtime (**12,000 lost packs**).

This project upgrades the factory from a **Reactive (Post-failure RCA)** model to an **Autonomous Predictive Intervention Ecosystem**:
1. **Physics-Informed Degradation Engine:** Detects knife wear rate, torque variance chatter, and mechanical power drift across a 15-frame sliding window, opening a **15–20 minute early warning window (AMBER)**.
2. **Autonomous Limp-Home Mode & PLC Handshake:** Automatically sends speed derating commands via Modbus/OPC UA Holding Registers (from 24,000 down to 18,000 cph), cutting wear rates by 80% to safely bridge the shift handover.
3. **Automated SAP PM Spare Parts Reservation:** Instantly checks warehouse inventory in `dim_spare_parts` and issues a digital requisition slip for replacement cartridge `#SAP-MAT-991024` at **Rack B2-Slot 04**.
4. **EHS LOTO Thermal Gate Enforcement:** Blocks machine restart until ultrasonic sonotrode temperature cools to **$T \le 40.0^\circ\text{C}$**.
5. **Direct Financial ROI Monetization:** Quantifies **27 minutes saved**, **10,800 Milo packs rescued**, and **93,900,000 VNĐ cost avoidance** per incident.

---

## 🏛️ System Architecture

+-----------------------------------------------------------------------+
|           PHYSICAL PACKAGING ASSET / SCADA TELEMETRY (1 HZ)           |
|      (Tetra Pak A3/Speed: Speed, Knife Wear, Torque, Temperature)     |
+-----------------------------------------------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                   degradation_engine.py (TRU COT 1)                   |
|         Physics-Informed Sliding Window (OLS Slope dy/dt)             |
|   [GREEN: 24k cph]  --->  [AMBER: Parameter Drift]  --->  [RED: Trip] |
+-----------------------------------------------------------------------+
                                    |
                     +--------------+--------------+
                     | (State == AMBER)            | (State == RED)
                     v                             v
+-----------------------------------+     +-----------------------------+
|     industrial_bridge.py          |     |    factory_tools.py         |
|  - PLC Holding Register #40001    |     |  - Safety Interlock Latch   |
|  - Limp-Home Derate: 18,000 cph   |     |  - LOTO Thermal Gate        |
|  - 2-Way Handshake ACK            |     |    (T_sonotrode <= 40.0 C)  |
+-----------------------------------+     +-----------------------------+
                     |
                     v
+-----------------------------------+
|        factory_tools.py           |
|  - Auto-reserve SAP Spare Part    |
|  - Material #SAP-MAT-991024       |
|  - Rack B2 - Slot 04 (Warehouse 1)|
+-----------------------------------+
                     |
                     v
+-----------------------------------------------------------------------+
|                      roi_engine.py (TRU COT 3)                        |
|               Financial ROI & Cost Avoidance Ledger                   |
|       Downtime Saved: 27 mins | Units Saved: 10,800 Milo Packs        |
|              Total Cost Avoidance: 93,900,000 VND / incident          |
+-----------------------------------------------------------------------+

---

## 📂 Project Repository Structure

| File | Role / Responsibility |
| :--- | :--- |
| `simulate_line.py` | Stochastic Physical Asset Simulator (Dynamic Digital Twin responsive to PLC speed & knife swap). |
| `degradation_engine.py` | Physics-Informed Sliding Window Degradation Detector (OLS Slope & Rolling Variance). |
| `industrial_bridge.py` | Industrial PLC Supervisory Bridge (Holding Registers 40001–40005 & 2-way Handshake). |
| `factory_tools.py` | Autonomous Business Toolset (PLC Speed Derate, SAP Spare Parts Reservation, LOTO Thermal Gate). |
| `roi_engine.py` | TPM Cost Deployment & Financial ROI Ledger (Monetizing downtime savings into VNĐ). |
| `agent_daemon.py` | 24/7 Autonomous Background Consumer Daemon (Orchestrating the closed loop). |
| `app.py` | Industrial Operations HMI Console designed strictly for Shift Maintenance Technicians. |
| `inspect_db.py` | Database Inspector tool to audit all Fact and Dimension tables in `packaging_factory.db`. |
| `export_powerbi_data.py` | Star Schema data exporter generating clean CSVs for Power BI Executive Dashboards. |

---

## 📊 Industrial Value Proposition (TPM & Financial ROI)

| Metric | Without AI Copilot (AS-IS Baseline) | With Autonomous Copilot (TO-BE) | Impact / Net Improvement |
| :--- | :--- | :--- | :--- |
| **Downtime Mode** | Unplanned Catastrophic Crash | Planned Quick-Swap (Cassette) | **Eliminated emergency line freeze** |
| **Downtime Duration** | 30.0 minutes | 3.0 minutes | **-27.0 minutes (-90% MTTR)** |
| **Product Loss** | 12,000 packs lost | 1,200 packs lost | **+10,800 Milo packs saved** |
| **Packaging Scrap** | ~60m shredded sterile paper | 0m clean web cut | **7,500,000 VNĐ scrap avoided** |
| **Total Cost Avoidance** | 0 VNĐ | **93,900,000 VNĐ / cycle** | **Direct bottom-line P&L protection** |

---

## 🚀 Quickstart Guide

### 1. Environment Setup
git clone https://github.com/NDHoang2003/nestle-packaging-copilot.git
cd nestle-packaging-copilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

### 2. Verify Database & Spare Parts Catalog
python setup_spare_parts.py
python inspect_db.py

### 3. Launch Technician HMI Console
streamlit run app.py

### 4. Export Datasets for Power BI Reporting
python export_powerbi_data.py