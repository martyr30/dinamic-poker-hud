from my_pokerkit_parser import CustomHandHistory
from glob import glob

hh_files = glob('/Users/admin/Library/Application Support/PokerStars/HandHistory/Martyr40/*.txt')
if hh_files:
    file_path = hh_files[0]
    print(f"Testing with {file_path}")
    
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()
    
    for hh in CustomHandHistory.from_pokerstars(content):
        print(f"Blinds: {hh.blinds_or_straddles}")
        print(f"Min Bet: {hh.min_bet}")
        print(f"Ante: {hh.ante}")
        print(f"Small Blind: {hh.small_blind}")
        print(f"Big Blind: {hh.big_blind}")
        break  
