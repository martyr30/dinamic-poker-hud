import sys
import os
sys.path.append(os.getcwd())  # Ensure current dir is in path
import poker_stats_db
from my_pokerkit_parser import CustomHandHistory
from glob import glob

print(f"Module File: {poker_stats_db.__file__}")

files = glob('/Users/admin/Library/Application Support/PokerStars/HandHistory/Martyr40/*.txt')
if not files:
    print("No files found!")
    sys.exit(1)

file_path = files[0]
print(f"Testing on {file_path}")

with open(file_path, 'r', encoding='utf-8-sig') as f:
    content = f.read()

for hh in CustomHandHistory.from_pokerstars(content):
    print(f"HH Min Bet: {getattr(hh, 'min_bet', 'MISSING')}")
    # Call analyze
    stats = poker_stats_db.analyze_player_stats(hh, 'Martyr40')
    print(f"Stats keys: {list(stats.keys())}")
    p_stats = stats.get('Martyr40')
    if p_stats:
        print(f"P_Stats keys: {list(p_stats.keys())}")
        print(f"Extracted BB Size: {p_stats.get('bb_size')}")
    else:
        print("Hero stats not found in result.")
    break
