import os
import shutil
import sqlite3
import pandas as pd
from typing import List

# Patch environment to use Test DB
import poker_globals
TEST_DB = 'test_poker_stats.db'
poker_globals.DB_NAME = TEST_DB

# Import after patching
import poker_stats_db
from poker_monitor import process_file_full_load

TEST_HISTORY_DIR = 'test_history'

def run_full_test():
    print(f"=== RUNNING TEST SUITE on {TEST_DB} ===")
    
    # 1. CLEANUP
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
        print("Removed old test DB.")
        
    # 2. INITIALIZE
    print("Initializing DB...")
    poker_stats_db.setup_database()
    
    # 3. LOAD HISTORY
    files = [os.path.join(TEST_HISTORY_DIR, f) for f in os.listdir(TEST_HISTORY_DIR) if f.endswith('.txt')]
    print(f"Loading {len(files)} hand history files from {TEST_HISTORY_DIR}...")
    
    for f in files:
        try:
            process_file_full_load(f)
            print(f"Processed {os.path.basename(f)}")
        except Exception as e:
            print(f"FAILED to process {f}: {e}")
            
    # 4. VERIFY DATA
    print("\n--- VERIFICATION ---")
    conn = sqlite3.connect(TEST_DB)
    cur = conn.cursor()
    
    # Count Hands
    cur.execute("SELECT COUNT(*) FROM my_hand_log")
    cnt = cur.fetchone()[0]
    print(f"Total Hands: {cnt}")
    
    if cnt == 0:
        print("FAILURE: No hands loaded.")
        conn.close()
        return

    # Check EV NULLs
    cur.execute("SELECT COUNT(*) FROM my_hand_log WHERE ev_adjusted IS NULL")
    nulls = cur.fetchone()[0]
    print(f"NULL EV Count (Non-All-In): {nulls}")
    
    # Check EV Values (All-In)
    cur.execute("SELECT COUNT(*) FROM my_hand_log WHERE ev_adjusted IS NOT NULL")
    evs = cur.fetchone()[0]
    print(f"Calculated EV Count (All-In): {evs}")
    
    # Check for 0.0 EV (Should be 0 if fix works)
    cur.execute("SELECT COUNT(*) FROM my_hand_log WHERE ev_adjusted = 0")
    zeros = cur.fetchone()[0]
    print(f"Zero EV Count (Should be 0): {zeros}")
    
    if zeros > 0:
         print("WARNING: Found 0.0 EV values! (Should be converted to NULL)")

    # Check Divergence
    cur.execute("SELECT hand_id, net_profit, ev_adjusted FROM my_hand_log WHERE ev_adjusted IS NOT NULL AND ABS(ev_adjusted - net_profit) > 0.01")
    rows = cur.fetchall()
    print(f"Found {len(rows)} hands with EV divergence (Luck Factor).")
    for r in rows[:5]:
        print(f"  Hand {r[0]}: Net {r[1]}, EV {r[2]}")
        
    conn.close()
    print("=== TEST COMPLETE ===")

if __name__ == "__main__":
    if not os.path.exists(TEST_HISTORY_DIR):
        print(f"Error: {TEST_HISTORY_DIR} not found. Run setup_test_env.py first.")
    else:
        run_full_test()
