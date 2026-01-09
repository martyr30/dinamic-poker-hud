# Logic Flow & Algorithms

## 1. Hand History Processing Pipeline
This is the core loop of the application, transforming raw text files into actionable HUD stats.

### Input
- **Source:** Text files in `~/Library/Application Support/PokerStars/HandHistory/`.
- **Trigger:** `WatchdogThread` in `poker_monitor.py` detects file modification (size change).

### Process
1.  **Detection:** The watchdog identifies the modified file and reads the new bytes.
2.  **Parsing (`my_pokerkit_parser.py`):**
    - The raw text is fed into `CustomHandHistory.from_pokerstars`.
    - Regex patterns in `CustomPokerStarsParser` extract players, stack sizes, and actions (bets, calls, folds).
    - Returns a structured `HandHistory` object.
3.  **Analysis (`poker_stats_db.py`):**
    - `analyze_hand_for_stats` traverses the actions to determine stats for each player:
        - **VPIP:** Did the player put money in preflop voluntarily?
        - **PFR:** Did the player raise preflop?
        - **3Bet:** Did the player re-raise a preflop raise?
    - `calculate_equity_monte_carlo` (optional/on-demand) simulates thousands of runouts to calculate All-in EV.
4.  **Storage:**
    - `update_stats_in_db` updates the aggregated stats in the SQLite database dynamically.
    - `update_hand_stats_in_db` logs the specific hand details (profit, cards) into `my_hand_log`.

### Output
- **Signal:** `MonitorSignals.stat_updated` is emitted with new stats.
- **UI Update:** `HUDManager` receives the signal and calls `HUDWindow.update_data`.
- **Display:** The `HUDWindow` repaints widgets over the PokerStars window with updated numbers.

## 2. HUD Positioning
To draw over PokerStars, the app needs precise coordinates.
- **MacOS Specifics:** `macos_window_utils.py` uses `Quartz` (CoreGraphics) to query the OS for window bounds.
- **Alignment:** `HUDWindow` creates a transparent overlay that matches the geometry of the target table. Widgets are placed relative to the center of the window, assuming a 6-max layout.

## 3. Equity Calculation (Monte Carlo)
For All-In EV calculations:
1.  Identify Hero's cards and Villain's cards.
2.  Identify the community cards.
3.  Simulate the remaining board cards `N` times (e.g., 1000).
4.  Compare hand strengths using `pokerkit` evaluators.
5.  `EV = (Win % * Pot) - Investment`.
