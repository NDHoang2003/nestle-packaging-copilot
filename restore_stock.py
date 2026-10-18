import sqlite3
conn = sqlite3.connect("packaging_factory.db")
conn.execute("UPDATE dim_spare_parts SET stock_quantity = 8 WHERE part_id = 'PART-CUT-TP115'")
conn.execute("UPDATE dim_spare_parts SET stock_quantity = 4 WHERE part_id = 'PART-JAW-TP180'")
conn.execute("UPDATE dim_spare_parts SET stock_quantity = 15 WHERE part_id = 'PART-BELT-SERVO'")
conn.commit()
conn.close()
print("✅ ĐÃ HỒI PHỤC KHO VẬT TƯ SAP ĐẦY ĐỦ!")