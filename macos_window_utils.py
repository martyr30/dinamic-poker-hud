import subprocess
import sys

def get_window_geometry_macos(partial_title, app_name="PokerStars"):
    """
    Returns (x, y, w, h) for the first window of app_name containing partial_title.
    Uses AppleScript via osascript.
    Returns None if not found or error.
    """
    script = f'''
    tell application "System Events"
        try
            tell process "{app_name}"
                try
                    set matches to (every window whose name contains "{partial_title}")
                on error
                    return "ERROR_FINDING_WINDOWS"
                end try
                
                if matches is {{}} then return "WINDOW_NOT_FOUND"
                
                set targetWindow to item 1 of matches
                set p to position of targetWindow
                set s to size of targetWindow
                
                -- Output as List X,Y,W,H
                return {{item 1 of p, item 2 of p, item 1 of s, item 2 of s}}
            end tell
        on error
            return "PROCESS_NOT_FOUND"
        end try
    end tell
    '''
    
    try:
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        output = result.stdout.strip()
        # print(f"DEBUG AppleScript RAW: '{output}'") # Commented out for production
        
        if result.returncode != 0:
            print(f"AppleScript Error: {result.stderr}")
            return None
            
        if output in ["PROCESS_NOT_FOUND", "WINDOW_NOT_FOUND", "ERROR_FINDING", ""]:
            return None
            
        parts = output.split(',')
        if len(parts) == 4:
            return tuple(map(int, parts))
            
    except Exception as e:
        print(f"Exception in get_window_geometry_macos: {e}")
        return None

    except Exception as e:
        print(f"Exception in get_window_geometry_macos: {e}")
        return None

    return None

class MacOSWindowAdapter:
    """
    Adapter that mimics pywinctl Window interface using AppleScript (osascript).
    """
    def __init__(self, title_part, app_name="PokerStars"):
        self.title_part = title_part
        self.app_name = app_name
        self._rect = (0, 0, 0, 0) # Cache
        self.update_geometry()

    def update_geometry(self):
        """Fetches fresh geometry from macOS."""
        geo = get_window_geometry_macos(self.title_part, self.app_name)
        
        # --- SMART FALLBACK FOR TESTING ---
        if not geo and self.app_name == "PokerStars":
             # Try Finder once
             # print(f"DEBUG: Checking Finder for '{self.title_part}'...")
             geo_finder = get_window_geometry_macos(self.title_part, app_name="Finder")
             if geo_finder:
                 print(f"HUD: Switch to Offline Testing Mode (Finder window '{self.title_part}')")
                 self.app_name = "Finder" 
                 geo = geo_finder
        # ----------------------------------

        if geo:
            self._rect = geo
        else:
            # Window lost: Reset to zero so main.py logic detects it (pos < 5)
            self._rect = (0, 0, 0, 0)
        return geo

    @property
    def topleft(self):
        self.update_geometry()
        return (self._rect[0], self._rect[1])

    @property
    def width(self):
        self.update_geometry()
        return self._rect[2]

    @property
    def height(self):
        self.update_geometry()
        return self._rect[3]
    
    @property
    def size(self):
        return (self._rect[2], self._rect[3])
    
    @property
    def left(self):
        self.update_geometry()
        return self._rect[0]

    @property
    def top(self):
        self.update_geometry()
        return self._rect[1]

    def exists(self):
        # Check if we can still fetch geometry
        return self.update_geometry() is not None

if __name__ == "__main__":
    # Test
    print("Testing Salli II...")
    geo = get_window_geometry_macos("Salli II")
    print(f"Geometry: {geo}")
    
    # Adapter Test
    print("Testing Adapter...")
    adapter = MacOSWindowAdapter("Salli II")
    if adapter.exists():
        print(f"Adapter Found! Pos: {adapter.topleft}, Size: {adapter.size}")
    else:
        print("Adapter not found.")
