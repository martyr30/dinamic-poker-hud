
import sqlite3
import pandas as pd
from poker_stats_db import DB_NAME

print(f"Checking DB: {DB_NAME}")

try:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Check Tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("Tables:", tables)
    
    # 2. Check my_hand_log columns
    print("\n--- my_hand_log columns ---")
    cursor.execute("PRAGMA table_info(my_hand_log)")
    columns = cursor.fetchall()
    found_ev = False
    for col in columns:
        print(col)
        if col[1] == 'ev_adjusted':
            found_ev = True
            
    if not found_ev:
        print("CRITICAL: ev_adjusted column NOT FOUND in my_hand_log")
    
    # 3. Check Row Count
    cursor.execute("SELECT count(*) FROM my_hand_log")
    count = cursor.fetchone()[0]
    print(f"\nTotal rows in my_hand_log: {count}")
    
    # 4. Check Data Sample
    if count > 0:
        cursor.execute("SELECT ev_adjusted FROM my_hand_log LIMIT 10")
        rows = cursor.fetchall()
        print("Sample ev_adjusted:", rows)
        
    # 5. Check Aggregates
    # Assuming standard table exists (e.g. derived from folder name or just check what we have)
    # The user mentioned "main program window all data is zeros".
    # This might mean the poker_stats tables are empty or zeroed.
    
    print(f"\nScanning {len(tables)} tables...")
    for tbl in tables:
        tname = tbl[0]
        # Ignore system tables
        if "sqlite" in tname: continue
        
        print(f"\nChecking table {tname}:")
        cursor.execute(f"SELECT count(*) FROM \"{tname}\"")
        row_count = cursor.fetchone()[0]
        print(f"Row Count: {row_count}")
        
        if row_count > 0:
            cursor.execute(f"SELECT * FROM \"{tname}\" LIMIT 1")
            row = cursor.fetchone()
            print(f"First Row: {row}")
        else:
            print("TABLE IS EMPTY!")
            
    # Check for EV divergence
    print("\n--- Checking for EV Divergence (EV != Net) ---")
    cursor.execute("SELECT count(*) FROM my_hand_log WHERE CAST(ev_adjusted as FLOAT) != CAST(net_profit as FLOAT)")
    div_count = cursor.fetchone()[0]
    print(f"Rows with EV != Net: {div_count}")
    
    if div_count > 0:
        cursor.execute("SELECT player_name, net_profit, ev_adjusted FROM my_hand_log WHERE CAST(ev_adjusted as FLOAT) != CAST(net_profit as FLOAT) LIMIT 5")
        for row in cursor.fetchall():
            print(row)
            
    cursor.execute("SELECT count(*) FROM my_hand_log WHERE ev_adjusted != 0")
    nz_count = cursor.fetchone()[0]
    print(f"Rows with ev_adjusted != 0: {nz_count}")
    
    print("\n--- Extreme Negative EV Hands ---")
    cursor.execute("""
        SELECT hand_id, cards, net_profit, ev_adjusted 
        FROM my_hand_log 
        WHERE ev_adjusted < -1.0
        ORDER BY ev_adjusted ASC 
        LIMIT 10
    """)
    rows = cursor.fetchall()
    for r in rows:
        print(r)
        
    print("\n--- Hands with large Divergence ---")
    cursor.execute("""
        SELECT hand_id, cards, net_profit, ev_adjusted 
        FROM my_hand_log 
        WHERE ABS(ev_adjusted - net_profit) > 5
        LIMIT 10
    """)
    rows = cursor.fetchall()
    for r in rows:
        print(r)
            
except Exception as e:
    print(f"Error: {e}")
finally:
    if conn: conn.close()
