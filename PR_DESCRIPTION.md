
# 🚀 Feature: Advanced Hero Stats, C-Bet Fixes & UI Overhaul

## 📝 Summary
This PR significantly enhances the **Hero Statistics (My Stats)** window and resolves critical bugs in the HUD logic. It introduces accurate C-Bet/3-Bet tracking, "Session Stats" logic for the Game Table Overlay, and a refined "Mini Mode" UI.

## ✨ Key Features

### 1. Accurate Hero Statistics
- **C-Bet Logic Fixed**: Correctly accounts for "Checks" as missed C-Bet opportunities (previously only counted Bets, leading to incorrect 100% stats).
- **Database Schema**: Added `wtsd` (Went to Showdown) and `wsd` (Won Showdown) columns to `my_hand_log`.
- **BB Defense**: Fixed logic conflict that caused Blind Defense stats to disappear.

### 2. HUD Overlay vs Personal Window
- **Game Table Overlay**: Now strictly shows **Session Stats** (hands played since app launch).
- **"My Stats" Window**: Shows **Lifetime Stats** (historical database).
- **Clarification**: This resolves user confusion about why stats might appear as "0" on the table (insufficient session sample) while being present in the database.

### 3. UI Improvements
- **Mini Mode**: Toggle (`_`) to show only compact VPIP/PFR stats.
- **Date Filters**: Filter "My Stats" by Today, Yesterday, or Custom Range.
- **Hand Matrix**: Clickable stats cells show a popup grid of hands (e.g., clicking "RFI" shows 13x13 grid).

## 🐛 Bug Fixes
- **C-Bet Mapping**: Fixed database key mismatch (`cbet_flop_succ` vs `is_cbet`) that prevented stats from saving.
- **Indentation Error**: Fixed startup crash caused by malformed python code in `poker_stats_db.py`.
- **BB vs Limp**: Corrected logic to distinguish Limp-Checks from Bets.

## 🧪 How to Test
1. **Rebuild Database**:
   ```bash
   python main.py --load-all
   ```
   *(Required to verify C-Bet fixes)*

2. **Verify "My Stats"**:
   - Open Personal Window.
   - Check that C-Bet and BB Defense stats are non-zero and realistic.

3. **Verify HUD Overlay**:
   - Play a new session.
   - Confirm stats start at 0 and accumulate as you play.

## 📋 Checklist
- [x] Database Migration (Schema Update)
- [x] Logic Verification (Unit Tests passed)
- [x] UI Responsiveness Tested
- [x] Documentation Updated (`walkthrough.md`)
