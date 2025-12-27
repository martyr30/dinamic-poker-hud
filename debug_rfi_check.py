import sqlite3
from poker_globals import DB_NAME, MY_PLAYER_NAME

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

print(f"Checking stats for {MY_PLAYER_NAME}...")

# Check VPIP/RFI raw sums
cursor.execute("""
    SELECT 
        COUNT(*) as total_hands,
        SUM(rfi_opportunity) as rfi_opps,
        SUM(is_rfi) as rfi_hits,
        SUM(is_vpip) as vpip_hits,
        SUM(is_pfr) as pfr_hits
    FROM my_hand_log 
    WHERE player_name = ?
""", (MY_PLAYER_NAME,))

row = cursor.fetchone()
print(f"Total Hands: {row[0]}")
print(f"RFI Opps: {row[1]}")
print(f"RFI Hits: {row[2]}")
print(f"VPIP Hits: {row[3]}")
print(f"PFR Hits: {row[4]}")

# Check breakdown by position
cursor.execute("""
    SELECT 
        position,
        COUNT(*),
        SUM(rfi_opportunity),
        SUM(is_rfi)
    FROM my_hand_log 
    WHERE player_name = ?
    GROUP BY position
""", (MY_PLAYER_NAME,))

print("\nBy Position:")
for r in cursor.fetchall():
    print(f"{r[0]}: Hands={r[1]}, RFI_Opp={r[2]}, RFI_Hit={r[3]}")

conn.close()
