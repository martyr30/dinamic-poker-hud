
import pywinctl as pwc
import time

try:
    print("Enumerating windows...")
    windows = pwc.getAllWindows()
    count = 0
    for w in windows:
        # Filter for likely candidates
        title = w.title.lower() if w.title else ""
        if "poker" in title or "prymno" in title or w.width > 200:
             print(f"Title: '{w.title}', Rect: {w.box}, Visible: {w.isVisible}")
             count += 1
    print(f"Total relevant windows found: {count}")
    
except Exception as e:
    print(f"Error: {e}")
