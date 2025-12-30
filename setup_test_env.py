import os
import shutil
import glob

SOURCE_DIR = "/Users/admin/Library/Application Support/PokerStars/HandHistory/Martyr40/"
DEST_DIR = "test_history"

def setup():
    # 1. Create directory
    if not os.path.exists(DEST_DIR):
        os.makedirs(DEST_DIR)
        print(f"Created {DEST_DIR}")
    
    # 2. Find recent files
    pattern = os.path.join(SOURCE_DIR, "*.txt")
    files = glob.glob(pattern)
    files.sort(key=os.path.getmtime, reverse=True)
    
    if not files:
        print("No HandHistory files found in source!")
        return
        
    # Copy top 2
    to_copy = files[:2]
    for f in to_copy:
        fname = os.path.basename(f)
        dst = os.path.join(DEST_DIR, fname)
        shutil.copy2(f, dst)
        print(f"Copied {fname} to {DEST_DIR}")
        
    print("Test Environment Setup Complete.")

if __name__ == "__main__":
    setup()
