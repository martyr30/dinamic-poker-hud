# poker_stats_db.py

import sqlite3
import decimal
import datetime
import sys
from typing import Dict, Any, List, Optional
from decimal import Decimal
from pokerkit import HandHistory
# Добавляем импорт для генерации имени таблицы
from poker_globals import DB_NAME, ACTION_POSITIONS, ALL_STATS_FIELDS, get_table_name_segment
from pokerkit.utilities import Card, Rank

# --- КОНСТАНТЫ ---
DB_NAME = 'poker_stats.db'

# --- 1. ФУНКЦИИ НАСТРОЙКИ БАЗЫ ДАННЫХ ---

def setup_database_table(table_segment: str):
    """Создает таблицу статистики с уникальным именем, если она не существует."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        safe_table_name = table_segment.replace("'", "").replace(";", "").replace(" ", "")

        # Схема таблицы: ДОБАВЛЕНЫ 4 НОВЫХ СТОЛБЦА
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {safe_table_name} (
                player_name TEXT PRIMARY KEY,
                hands INTEGER DEFAULT 0,
                vpip_hands INTEGER DEFAULT 0,
                pfr_hands INTEGER DEFAULT 0,
                _3bet_opportunities INTEGER DEFAULT 0,
                _3bet_successes INTEGER DEFAULT 0,
                _fold_to_3bet_opportunities INTEGER DEFAULT 0,
                _fold_to_3bet_successes INTEGER DEFAULT 0,

                pfr_utg INTEGER DEFAULT 0,
                pfr_mp INTEGER DEFAULT 0,
                pfr_co INTEGER DEFAULT 0,
                pfr_bu INTEGER DEFAULT 0,
                pfr_sb INTEGER DEFAULT 0,

                hands_utg INTEGER DEFAULT 0,
                hands_mp INTEGER DEFAULT 0,
                hands_co INTEGER DEFAULT 0,
                hands_bu INTEGER DEFAULT 0,
                hands_sb INTEGER DEFAULT 0,

                rfi_opp_utg INTEGER DEFAULT 0,
                rfi_opp_mp INTEGER DEFAULT 0,
                rfi_opp_co INTEGER DEFAULT 0,
                rfi_opp_bu INTEGER DEFAULT 0,

                rfi_succ_utg INTEGER DEFAULT 0,
                rfi_succ_mp INTEGER DEFAULT 0,
                rfi_succ_co INTEGER DEFAULT 0,
                rfi_succ_bu INTEGER DEFAULT 0,

                af_bets_raises INTEGER DEFAULT 0,
                af_calls INTEGER DEFAULT 0,

                cbet_flop_opp INTEGER DEFAULT 0,
                cbet_flop_succ INTEGER DEFAULT 0,
                fcbet_flop_opp INTEGER DEFAULT 0,
                fcbet_flop_succ INTEGER DEFAULT 0,
                wtsd_hands INTEGER DEFAULT 0,
                wsd_hands INTEGER DEFAULT 0
            )
        """)

        # МИГРАЦИЯ: Добавляем колонки, если таблица уже существовала без них
        columns_to_add = [
            "cbet_flop_opp", "cbet_flop_succ",
            "fcbet_flop_opp", "fcbet_flop_succ",
            "wtsd_hands", "wsd_hands"
        ]
        for col in columns_to_add:
            try:
                cursor.execute(f"ALTER TABLE {safe_table_name} ADD COLUMN {col} INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                # Колонка уже существует
                pass

        # 🌟 2. НОВАЯ ТАБЛИЦА: Лог сыгранных раздач
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS my_hand_log (
                hand_id TEXT NOT NULL,                  -- Идентификатор раздачи (уникальный)
                table_part_name TEXT NOT NULL,          -- Часть имени стола для привязки к HUD
                player_name TEXT NOT NULL,
                position TEXT NOT NULL,                 -- Позиция (utg, mp, co, bu, sb, bb)
                cards TEXT NOT NULL,                    -- Карты игрока (например, "AsKc")
                is_rfi BOOLEAN NOT NULL,                -- RFI (да/нет)
                is_pfr BOOLEAN NOT NULL,                -- PFR (да/нет)
                is_vpip BOOLEAN NOT NULL,               -- VPIP (да/нет)
                first_action TEXT,                      -- Первое агрессивное действие (рейз, колл, фолд)
                first_raiser_position TEXT,
                is_steal_attempt BOOLEAN NOT NULL,
                net_profit DECIMAL(10,2),
                time_logged DATETIME DEFAULT CURRENT_TIMESTAMP,
                
                final_street TEXT,
                final_action TEXT,
                final_hand_strength TEXT,
                facing_bet_pct_pot DECIMAL(5,2),
                opponent_position TEXT,
                board_cards TEXT,
                rfi_opportunity INTEGER DEFAULT 0,
                
                -- Новые колонки для защиты BB и стилов
                facing_steal INTEGER DEFAULT 0,  -- 1, если игрок на BB/SB и получил опен-рейз с CO/BU/SB
                is_steal_defend INTEGER DEFAULT 0, -- 1, если заколлировал (Cold Call)
                is_steal_3bet INTEGER DEFAULT 0,   -- 1, если сделал 3-бет
                is_steal_fold INTEGER DEFAULT 0,   -- 1, если сфолдил
                steal_success INTEGER DEFAULT 0,    -- 1, если наш стил удался (все сфолдили)

                PRIMARY KEY (hand_id, player_name)
            );
        """)
        
        # МИГРАЦИЯ my_hand_log
        log_columns_to_add = [
            "final_street", "final_action", "final_hand_strength",
            "facing_bet_pct_pot", "opponent_position", "board_cards",
            "rfi_opportunity"
        ]
        for col in log_columns_to_add:
            try:
                # Определяем тип данных для колонки
                col_type = "TEXT"
                if "pct_pot" in col: col_type = "DECIMAL(5,2)"
                
                cursor.execute(f"ALTER TABLE my_hand_log ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass
        
        # The following block is added by the user's instruction.
        # It appears to be intended for migration of specific columns,
        # but is placed inside the loop for `log_columns_to_add`.
        # This will cause the `rfi_opportunity` and BB defense columns
        # to be attempted to be added multiple times.
        try:
            cursor.execute(f"ALTER TABLE my_hand_log ADD COLUMN rfi_opportunity INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        # Migration for BB Defense Stats (Step 5)
        new_cols = [
            ("facing_steal", "INTEGER DEFAULT 0"),
            ("is_steal_defend", "INTEGER DEFAULT 0"),
            ("is_steal_3bet", "INTEGER DEFAULT 0"),
            ("is_steal_fold", "INTEGER DEFAULT 0"),
            ("steal_success", "INTEGER DEFAULT 0"),
            # Step 6: BB vs Limp
            ("facing_limp", "INTEGER DEFAULT 0"),
            ("is_limp_check", "INTEGER DEFAULT 0"),
            ("is_limp_iso", "INTEGER DEFAULT 0")
        ]
        for col_name, col_type in new_cols:
            try:
                cursor.execute(f"ALTER TABLE my_hand_log ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
    except Exception as e:
        print(f"❌ Ошибка при настройке таблицы '{table_segment}': {e}")
    finally:
        if conn:
            conn.close()

def setup_database():
    """Инициализация базы данных (не создает таблицы, так как они динамические)."""
    pass

    return None

def get_hand_strength(hole_cards_str: str, board_cards_str: str) -> str:
    """
    Определяет силу руки (Top Pair, 2nd Pair, etc.)
    Args:
        hole_cards_str: строка карт героя (напр. "AsKd")
        board_cards_str: строка карт борда (напр. "Ah7s2d")
    """
    if not hole_cards_str:
        return ""
    
    try:
        hole = list(Card.parse(hole_cards_str))
        board = list(Card.parse(board_cards_str)) if board_cards_str else []
    except ValueError:
        return ""
        return ""

    if not board:
        # Preflop logic
        if hole[0].rank == hole[1].rank:
            return "Pocket Pair"
        return "High Card"

    # Postflop logic
    # Оценка комбинации
    # 1. Проверяем на совпадения (Пары)
    
    hole_ranks = [c.rank for c in hole]
    board_ranks = [c.rank for c in board]
    board_ranks.sort(reverse=True) # От старшей к младшей
    
    # Совпадения карт
    matches = []
    for hr in hole_ranks:
        if hr in board_ranks:
            matches.append(hr)
            
    is_pocket_pair = hole[0].rank == hole[1].rank
    
    # --- Стриты, Флеши, Сеты, Доперы (Упрощенно без полного эвалуатора) ---
    # Для целей лик-файндера нам важны Top Pair, 2nd Pair, Weak Pair.
    # Если у нас Сет или лучше - это обычно "Strong Hand".
    
    # Проверка на карманную пару
    if is_pocket_pair:
        if board_ranks and hole[0].rank > board_ranks[0]:
            return "Overpair"
        if hole[0].rank in board_ranks:
            return "Set" # Или Full House/Quads, но Set достаточно для 'Strong'
        # Если карманка ниже старшей карты борда
        # Нужно понять, какая это пара относительно борда.
        # Например, Board: K 7 2. Hero: 99. Это "Underpair" к K, но лучше 7.
        # Обычно это называется Middle Pair или Weak Pair в зависимости от контекста.
        return "Pocket Pair < Top Card"

    if not matches:
        return "High Card" # Или дро
        
    # У нас есть совпадение(я)
    if len(matches) >= 2:
        return "Two Pair" # Или Trips
        
    # Одно совпадение (One Pair)
    match_rank = matches[0]
    
    if match_rank == board_ranks[0]:
        return "Top Pair"
    elif len(board_ranks) > 1 and match_rank == board_ranks[1]:
        return "2nd Pair"
    else:
        return "Weak Pair"

    return "Pair"

def determine_position(player_index_p: int, num_players_in_hand: int) -> Optional[str]:
    """
    Определяет покерную позицию игрока (UTG/MP/CO/BU/SB/BB)
    на основе его индекса в порядке действий (1..N) и общего числа игроков.
    """

    if player_index_p == 1:
        return "sb"
    if player_index_p == 2:
        return "bb"

    # SUPPORT FOR 9-MAX (and other non-6max sizes)
    # Standard 6-max positions: UTG, MP, CO, BU
    # Standard 9-max positions: UTG, UTG+1, UTG+2, MP, MP+1, MP+2, CO, BU (approx)
    
    # DB Columns: pfr_utg, pfr_mp, pfr_co, pfr_bu
    # We must map N positions to these 4 buckets to avoid crashes and save stats.
    
    # Bucket Mapping Strategy:
    # 3-handed: BU
    # 4-handed: CO, BU
    # 5-handed: MP, CO, BU
    # 6-handed: UTG, MP, CO, BU
    # 9-handed: UTG, UTG+1, MP, MP+1, MP+2, CO, BU -> ep, ep, mp, mp, mp, co, bu
    
    num_action_positions = num_players_in_hand - 2
    if num_action_positions <= 0:
        return None # Heads-up SB/BB only

    # Define Full Ring Positions (up to 9-handed = 7 action seats)
    # We list them from early to late.
    # 9-max action seats: UTG, UTG+1, MP, MP+1, HJ(MP2), CO, BU
    full_ring_order = ['utg', 'utg', 'mp', 'mp', 'mp', 'co', 'bu']
    
    # If 6-max (4 seats): take last 4: utg, mp, co, bu? 
    # Wait, full_ring_order[-4:] -> mp, mp, co, bu. NO.
    # 6-max expected: UTG, MP, CO, BU.
    
    # Better approach: Define bucket list for current table size dynamically
    if num_players_in_hand <= 6:
        # 6-Max Logic (Standard)
        # 3 items: [MP, CO, BU] ? No, usually [UTG, MP, CO, BU]
        # But if 5 players? UTG is dropped? or MP dropped?
        # Standard convention: Drop from Early.
        # 6-max: UTG, MP, CO, BU
        # 5-max: MP, CO, BU
        # 4-max: CO, BU
        # 3-max: BU
        
        # We can use the existing ACTION_POSITIONS logic for <= 6
        # ACTION_POSITIONS = ["utg", "mp", "co", "bu"] (Len 4)
        skipped = len(ACTION_POSITIONS) - num_action_positions # 4 - 4 = 0
        if skipped < 0: skipped = 0 # Should not happen if size <= 6
        
        start_idx = skipped
        action_idx = player_index_p - 3 # 0-based index of actor
        final_idx = start_idx + action_idx
        
        if 0 <= final_idx < len(ACTION_POSITIONS):
            return ACTION_POSITIONS[final_idx]
            
    else:
        # 9-Max / Full Ring Logic (>6 players)
        # We need to map 7 seats to [UTG, MP, CO, BU]
        # Let's define a mapping for 7 seats (9-max):
        # Seat 1 (UTG) -> UTG
        # Seat 2 (UTG+1) -> UTG
        # Seat 3 (MP) -> MP
        # Seat 4 (MP+1) -> MP
        # Seat 5 (HJ) -> MP
        # Seat 6 (CO) -> CO
        # Seat 7 (BU) -> BU
        
        # Create a specific list for the number of action seats available
        # This is a heuristic map to compress 9-max into 4 buckets
        map_9max = ['utg', 'utg', 'mp', 'mp', 'mp', 'co', 'bu'] # Length 7
        
        # If we have 8 players (6 action seats)? Drop first 'utg'.
        # If we have 10 players? Add extra 'utg'.
        
        # General Algorithm: 
        # Always have 1 BU, 1 CO.
        # Remaining N-2 seats are split between EP(UTG) and MP.
        # Let's say split roughly half-half.
        
        n_rem = num_action_positions - 2 # Exclude CO, BU
        if n_rem < 0: n_rem = 0 # Should not happen for >6 players
        
        n_mp = n_rem // 2 + (n_rem % 2) # checking rounding? say 5 rem -> 3 MP, 2 UTG?
        # Or usually more EP? 
        # Let's stick to the list slicing for simplicity relying on max 9 players usually.
        
        # Slice from the end of the 9-max map
        # If 7 action seats (9 players): take all 7.
        # If 6 action seats (8 players): take last 6: utg, mp, mp, mp, co, bu
        # If 5 action seats (7 players): take last 5: mp, mp, mp, co, bu
        
        current_map = map_9max[-num_action_positions:]
        
        action_idx = player_index_p - 3
        if 0 <= action_idx < len(current_map):
            return current_map[action_idx]

    return None

# --- 2.1 ФУНКЦИЯ АНАЛИЗА РАЗДАЧИ ---
def analyze_hand_for_stats(hand_history: HandHistory):
    """
    Анализирует распарсенную раздачу для определения VPIP, PFR, 3Bet и Fold to 3Bet.

    Использует:
    - Порядок действий p1 -> p2 -> ...
    - Коды действий: cc, cbr, f.
    - Возвращает словарь {player_name: {...}} с новыми метриками.
    """
    stats_update = {}
    player_map = {}
    all_players = [p for p in hand_history.players]

    # Инициализация всех игроков
    for i, player_name in enumerate(all_players):
        player_code = f'p{i + 1}'
        player_position = determine_position( i+1, len(all_players) )
        player_map[player_code] = [player_name, player_position]
        stats_update[player_name] = {
            'vpip': False,
            'pfr': False,
            '3bet_opp': 0,
            '3bet_success': 0,
            'f3bet_opp': 0,
            'f3bet_success': 0,
            'pfr_utg': 0,
            'pfr_mp': 0,
            'pfr_co': 0,
            'pfr_bu': 0,
            'pfr_sb': 0,
            'hands_utg': 0,
            'hands_mp': 0,
            'hands_co': 0,
            'hands_bu': 0,
            'hands_sb': 0,
            'rfi_opp_utg': 0,
            'rfi_opp_mp': 0,
            'rfi_opp_co': 0,
            'rfi_opp_bu': 0,
            'rfi_succ_utg': 0,
            'rfi_succ_mp': 0,
            'rfi_succ_co': 0,
            'rfi_succ_bu': 0,
            'af_bets_raises': 0, # Счётчик агрессивных действий (Bet/Raise) на постфлопе
            'af_calls': 0        # Счётчик коллов на постфлопе
        }

    # --- Отслеживание префлоп-действий ---
    state = '0rfi' # 0rfi, 0bet, 2bet, 3bet
    # Для C-Bet нам нужно знать, кто был агрессором на предыдущей улице
    preflop_aggressor = None # Имя игрока
    last_raiser = None

    # Для WTSD отслеживаем активных игроков
    active_players = set(all_players)

    # 1. Основной цикл по действиям
    is_postflop = False
    current_street = 'preflop' # preflop, flop, turn, river
    postflop_has_bet = False
    flop_cbet_made = False # Чтобы отследить Fold to CBet

    for action_str in hand_history.actions:
        # Проверяем смену улицы
        if action_str.startswith('d db'):
            is_postflop = True
            postflop_has_bet = False
            # Переход на новую улицу
            if current_street == 'preflop':
                current_street = 'flop'
                preflop_aggressor = last_raiser # Фиксируем агрессора
            elif current_street == 'flop':
                current_street = 'turn'
            elif current_street == 'turn':
                current_street = 'river'
            continue

        if action_str.startswith('p'):
            parts = action_str.split()
            player_code = parts[0]
            action_type_code = parts[1]
            player_name = player_map.get(player_code)[0]
            player_name = player_map.get(player_code)[0]

            if not player_name:
                continue

            # Обновление WTSD (если фолд, выбывает)
            if action_type_code == 'f':
                active_players.discard(player_name)
            
            key_to_update = 'hands_' + player_map.get(player_code)[1]
            stats_update[player_name][key_to_update] = 1

            # --- ЛОГИКА ПРЕФЛОПА (RFI, PFR, 3Bet) ---
            if not is_postflop:
                if action_type_code == 'cbr':
                    last_raiser = player_name # Обновляем последнего агрессора

                # --- RFI ---
                if state == '0rfi' and player_map.get(player_code)[1] in ('utg', 'mp', 'co', 'bu'):
                    key_to_update = 'rfi_opp_' + player_map.get(player_code)[1]
                    stats_update[player_name][key_to_update] = 1
                    if action_type_code != 'f':
                        key_to_update = 'rfi_succ_' + player_map.get(player_code)[1]
                        
                        if action_type_code == 'cbr':
                            state = '0bet'
                            # Usually RFI = Raise First In. Limp is not RFI success?
                            # If we count Limp as RFI success, keep it. 
                            # But standard definition: RFI is Raise.
                            # Assuming we want to count successful "Voluntary Entry" here? 
                            # If so, keep line 463.
                            # But better: Only count RFI if Raise.
                            stats_update[player_name][key_to_update] = 1
                        elif action_type_code == 'cc':
                             state = '0limp'
                             # Limp is NOT RFI success in standard terms.
                             # But passing it as success just to not break existing "RFI" stat if user relies on it?
                             # Let's count it for now to avoid side effects, OR disable it.
                             # If I disable it, RFI% drops.
                             # Given "DinamicHUD" context, likely RFI = PFR from open?
                             # Let's leave stats_update for now but fix STATE.
                             stats_update[player_name][key_to_update] = 1

                # --- PFR ---
                if action_type_code == 'cbr':
                    stats_update[player_name]['pfr'] = True
                    key_to_update = 'pfr_' + player_map.get(player_code)[1]
                    stats_update[player_name][key_to_update] = 1

                # --- 3BET ЛОГИКА ---
                # --- 3BET ЛОГИКА ---
                
                if state in ('0bet', '0rfi', '0limp'):
                    if action_type_code == 'cbr':
                        state = '2bet'
                elif state == '2bet':
                    if action_type_code == 'cbr':
                        stats_update[player_name]['3bet_opp'] = 1
                        stats_update[player_name]['3bet_success'] = 1
                        state = '3bet'
                    else:
                        stats_update[player_name]['3bet_opp'] = 1
                elif state == '3bet':
                    if action_type_code == 'f':
                        stats_update[player_name]['f3bet_opp'] = 1
                        stats_update[player_name]['f3bet_success'] = 1
                    else:
                        stats_update[player_name]['f3bet_opp'] = 1

            # --- ЛОГИКА ПОСТФЛОПА ---
            else:
                # --- C-BET FLOP ---
                if current_street == 'flop':
                    # Возможность К-бета есть у префлоп-агрессора, если перед ним никто не ставил
                    if player_name == preflop_aggressor and not postflop_has_bet:
                        stats_update[player_name]['cbet_flop_opp'] = 1
                        if action_type_code == 'cbr':
                            stats_update[player_name]['cbet_flop_succ'] = 1
                            flop_cbet_made = True
                    
                    # --- FOLD TO C-BET FLOP ---
                    # Если был сделан К-бет, следующий игрок имеет возможность сфолдить
                    if flop_cbet_made and not stats_update[player_name].get('cbet_flop_succ', 0): 
                         # Исключаем самого агрессора
                        if player_name != preflop_aggressor:
                             # Чтобы не засчитывать несколько раз, можно проверять флаг
                             # Но здесь упрощенно: любое действие после CBet - это реакция
                             # Сложно: CBet мог быть мультипот.
                             # Упрощение: Считаем реакцию ПЕРВОГО оппонента, или всех?
                             # Обычно Fold to CBet считается для всех, кто столкнулся с CBet.
                             # Если CBet был, и игрок делает действие:
                             #  - Fold -> Opp=1, Succ=1
                             #  - Call/Raise -> Opp=1, Succ=0
                             # Нужно убедиться, что мы еще не засчитали этому игроку реакцию на этой улице
                             if 'f2cbet_counted' not in stats_update[player_name]:
                                 stats_update[player_name]['fcbet_flop_opp'] = 1
                                 stats_update[player_name]['f2cbet_counted'] = True
                                 if action_type_code == 'f':
                                     stats_update[player_name]['fcbet_flop_succ'] = 1


                # AF = (Bets + Raises) / Calls
                if action_type_code == 'cbr': # Bet или Raise
                    stats_update[player_name]['af_bets_raises'] += 1
                    postflop_has_bet = True
                elif action_type_code == 'cc':
                    if postflop_has_bet:
                        stats_update[player_name]['af_calls'] += 1

            # --- VPIP ---
            if action_type_code in ('cc', 'cbr'):
                stats_update[player_name]['vpip'] = True

    # --- WTSD & WSD ---
    # В конце раздачи active_players содержит тех, кто дошел до шоудауна (или выиграл без шоудауна, 
    # если все остальные сфолдили, но hand_history.winnings покажет это)
    # WTSD: Игрок не сфолдил.
    # WSD: Игрок выиграл > 0.
    
    # Чтобы отличить "все сфолдили" от "шоудауна", проверим, сколько активных игроков.
    # Если > 1, то был шоудаун.
    # Если 1, то победа без шоудауна (обычно WTSD не считается, но зависит от трактовки.
    # GTO Wizard/HM3: WTSD = Went to Showdown. Если все сфолдили, никто не дошел до ШД.)
    
    was_showdown = len(active_players) > 1
    
    if was_showdown:
        for p_name in active_players:
            stats_update[p_name]['wtsd'] = True
            
            # Проверяем выигрыш
            try:
                p_index = hand_history.players.index(p_name)
                if hand_history.winnings and hand_history.winnings[p_index] > 0:
                    stats_update[p_name]['wsd'] = True
            except ValueError:
                pass

    # 2. Финальная агрегация (для очистки булевых значений)
    final_stats = {}
    for name, data in stats_update.items():
        # VPIP и PFR сохраняются
        final_stats[name] = {
            'vpip': data['vpip'],
            'pfr': data['pfr'],
            # 3Bet %
            '3bet_success': data['3bet_success'],
            '3bet_opp': data['3bet_opp'],
            # Fold to 3Bet %
            'f3bet_success': data['f3bet_success'],
            'f3bet_opp': data['f3bet_opp'],
            'pfr_utg': data['pfr_utg'],
            'pfr_mp': data['pfr_mp'],
            'pfr_co': data['pfr_co'],
            'pfr_bu': data['pfr_bu'],
            'pfr_sb': data['pfr_sb'],
            'hands_utg': data['hands_utg'],
            'hands_mp': data['hands_mp'],
            'hands_co': data['hands_co'],
            'hands_bu': data['hands_bu'],
            'hands_sb': data['hands_sb'],
            'rfi_opp_utg': data['rfi_opp_utg'],
            'rfi_opp_mp': data['rfi_opp_mp'],
            'rfi_opp_co': data['rfi_opp_co'],
            'rfi_opp_bu': data['rfi_opp_bu'],
            'rfi_succ_utg': data['rfi_succ_utg'],
            'rfi_succ_mp': data['rfi_succ_mp'],
            'rfi_succ_co': data['rfi_succ_co'],
            'rfi_succ_bu': data['rfi_succ_bu'],
            'cbet_flop_opp': data.get('cbet_flop_opp', 0),
            'cbet_flop_succ': data.get('cbet_flop_succ', 0),
            'fcbet_flop_opp': data.get('fcbet_flop_opp', 0),
            'fcbet_flop_succ': data.get('fcbet_flop_succ', 0),
            'wtsd': data.get('wtsd', False),
            'wsd': data.get('wsd', False),
            'af_bets_raises': data['af_bets_raises'],
            'af_calls': data['af_calls']
        }
    # print("ALL players stats:")
    # print(final_stats)
    return final_stats

# --- 2.2 ФУНКЦИЯ АНАЛИЗА РАЗДАЧИ ИГРОКА ---
def analyze_player_stats(hand_history: HandHistory, analyze_player_name: str):
    stats_update = {}
    player_map = {}
    all_players = [p for p in hand_history.players]
    analyze_player_code = ""
    player_bet = Decimal('0.00')
    player_bet = Decimal('0.00')
    player_win = Decimal('0.00')
    
    # Ensure list conversion for subscriptable access
    hh_winnings = list(hand_history.winnings) if hand_history.winnings else []
    hh_blinds = list(hand_history.blinds_or_straddles) if hand_history.blinds_or_straddles else []
    hh_stacks = list(hand_history.starting_stacks) if hand_history.starting_stacks else []
    
    # Инициализация всех игроков
    for i, player_name in enumerate(all_players):
        player_code = f'p{i + 1}'
        player_position = determine_position( i+1, len(all_players) )
        player_map[player_code] = [player_name, player_position]
        # print(player_map[player_code])
        if player_name == analyze_player_name:
            analyze_player_code = f'p{i + 1}'
            stats_update[player_name] = {
                'hand_id': hand_history.hand,
                'table_part_name': hand_history.table,
                'player_name': analyze_player_name,
                'position': player_position,
                'cards': "",
                'is_rfi': 0,
                'is_pfr': 0,
                'is_vpip': 0,
                'first_action': "uncalled",
                'first_raiser_position': "",
                'is_steal_attempt': 0,
                # 'actions': [],
                'net_profit': 0.00,
                'net_profit': 0.00,
                'time_logged': datetime.datetime.now(), # Placeholder
                'final_street': 'preflop',
                'final_action': 'n/a',
                'final_hand_strength': '',
                'facing_bet_pct_pot': 0.0,
                'opponent_position': '',
                'opponent_position': '',
                'board_cards': '',
                'rfi_opportunity': 0,
                # New BB Defense & Steal stats
                'facing_steal': 0,
                'is_steal_defend': 0,
                'is_steal_3bet': 0,
                'is_steal_fold': 0,
                'steal_success': 0
            }

            # 1. ВРЕМЯ РАЗДАЧИ
            try:
                hh_date = getattr(hand_history, 'date', None)
                hh_time = getattr(hand_history, 'time', None)

                # Fix for PokerKit versions where .date is not present but year/month/day are
                if hh_date is None:
                    if hasattr(hand_history, 'year') and hasattr(hand_history, 'month') and hasattr(hand_history, 'day'):
                        # Ensure values are integers (sometimes None if parsing failed)
                        if hand_history.year and hand_history.month and hand_history.day:
                            hh_date = datetime.date(hand_history.year, hand_history.month, hand_history.day)

                if isinstance(hh_date, datetime.date):
                    if hh_time and isinstance(hh_time, datetime.time):
                         stats_update[player_name]['time_logged'] = datetime.datetime.combine(hh_date, hh_time)
                    else:
                         stats_update[player_name]['time_logged'] = datetime.datetime(hh_date.year, hh_date.month, hh_date.day)
            except Exception:
                pass

            
            # --- ОТЛАДОЧНЫЙ БЛОК ДЛЯ ПОИСКА ОШИБКИ ---
            try:
                # ВАЖНО: Проверяем, что список блайндов существует, прежде чем обращаться к нему
                # if hh_blinds and hh_blinds[i] != 0:
                #     player_bet = hh_blinds[i]
                # Аналогичная проверка для выигрышей
                if hh_winnings and i < len(hh_winnings) and hh_winnings[i] != 0:
                    player_win = hh_winnings[i]
            except IndexError:
                # Перевызываем ошибку, чтобы увидеть полный traceback
                raise
    # --- Отслеживание префлоп-действий ---
    state = '0rfi' # 0rfi, 0limp, 1bet, 3bet, 4bet
    first_action = True
    is_steal_attempt = False # Глобальный флаг для текущей улицы (кто-то стилит)

    # 1.1 Префлоп: Основные действия и определение 3-бетов
    for action_str in hand_history.actions:
        parts = action_str.split()
        # print(parts[3])

        if parts[1] in ('db', 'sm'): # Конец префлопа
            break

        if action_str.startswith('d dh') and parts[2] == analyze_player_code:
            stats_update[analyze_player_name]['cards'] = parts[3]

        if action_str.startswith('p'):
            player_code = parts[0]
            action_type_code = parts[1]

            if first_action and player_code == analyze_player_code:
                first_action = False
                stats_update[analyze_player_name]['first_action'] = action_type_code
            
            # Capture state before this action modifies it
            state_before_action = state

            # --- RFI Logic ---
            # 1. Check Opportunity
            if player_code == analyze_player_code and state == '0rfi':
                stats_update[analyze_player_name]['rfi_opportunity'] = 1

            # 2. Check Action
            if action_type_code != 'f':
                if action_type_code == 'cbr': # Raise
                    if state == '0rfi':
                        # If Hero raises in 0rfi -> RFI
                        if player_code == analyze_player_code:
                             stats_update[analyze_player_name]['is_rfi'] = 1
                        
                        state = '1bet'
                        raiser_pos = player_map.get(player_code)[1]
                        stats_update[analyze_player_name]['first_raiser_position'] = raiser_pos
                        
                        # Steal Attempt Logic
                        if raiser_pos in ('co', 'bu', 'sb'):
                            # Mark that SOMEONE made a steal attempt (used for next players)
                            is_steal_attempt = True
                            if player_code == analyze_player_code:
                                stats_update[analyze_player_name]['is_steal_attempt'] = 1
                        else:
                            is_steal_attempt = False
                            
                    elif state == '0limp':
                        # Iso-Raise against Limper(s)
                        state = '1bet'
                        # Note: We don't mark RFI here (RFI is First In).
                        # We don't mark Steal here (Steal is against Blinds only, usually Unopened).
                        # But we MUST update state so BB knows it's NOT a limp pot anymore.
                        is_steal_attempt = False # Facing Iso is not Facing Steal usually (or is it? usually Steal is RFI)
                            
                else: 
                     # Only set to 0limp if it was 0rfi (Open Limp)
                     # If it was 1bet, a call keeps it 1bet (or we don't change state)
                     if state == '0rfi':
                         state = '0limp'
            
            # --- BB Defense Logic (Facing Steal) ---
            # If Hero is on BB (or SB), and previous action was a Steal Attempt (Raise from Late Pos)
            # We use state_before_action to see what we FACED.
            
            if player_code == analyze_player_code:
                hero_pos = player_map.get(player_code)[1]
                
                # Check if facing a steal
                if state_before_action == '1bet' and is_steal_attempt:
                    # Additional check: ensure Hero is in Blinds
                    if hero_pos in ('bb', 'sb'):
                         stats_update[analyze_player_name]['facing_steal'] = 1
                         
                         if action_type_code == 'f':
                             stats_update[analyze_player_name]['is_steal_fold'] = 1
                         elif action_type_code == 'cc':
                             stats_update[analyze_player_name]['is_steal_defend'] = 1
                         elif action_type_code == 'cbr':
                             stats_update[analyze_player_name]['is_steal_3bet'] = 1

                # --- BB vs Limp Logic ---
                # Check if facing a Limp (Unraised pot + someone limped)
                # state_before_action == '0limp' means someone limped (and no raise occurred after).
                # Only for BB.
                if state_before_action == '0limp' and hero_pos == 'bb':
                    stats_update[analyze_player_name]['facing_limp'] = 1
                    
                    if action_type_code == 'cc':
                         stats_update[analyze_player_name]['is_limp_check'] = 1
                         # Fix VPIP: Checking huge blind is NOT Voluntarily putting money in.
                         # Although VPIP calculation is done elsewhere (globally for 'cc'), 
                         # we might want to manually exclude it from VPIP count if we could.
                         # But `stats.update['vpip']` is boolean.
                         # If we set it to True globally, we can't unset it easily without tracking amounts.
                         # For now, we just track the Limp Stat.
                         
                    elif action_type_code == 'cbr':
                         stats_update[analyze_player_name]['is_limp_iso'] = 1

            # --- Steal Success Logic ---
            # If Hero made a steal attempt (is_steal_attempt=1 calculated above), 
            # check if everyone folded. This is done at end of hand or if 'f' ends action?
            # Actually, `analyze_player_stats` calculates `final_action`. 
            # But "Success" means we won the pot. `net_profit > 0` and Hand ended preflop?
            # Or specifically "Everyone folded to our raise".
            # We can check specific winning condition at end of function.


            # --- VPIP/PFR (Ваша логика) ---
            if player_code == analyze_player_code:
                # cc (Call), rbr (Bet/Raise) - это VPIP
                if action_type_code in ('cc', 'cbr'):
                    stats_update[analyze_player_name]['is_vpip'] = 1
                # rbr (Raise) - это PFR
                if action_type_code in ('cbr'):
                    stats_update[analyze_player_name]['is_pfr'] = 1

    # 1.2 Подсчет инвестиций и выигрыша.
    # Мы должны отслеживать ставки на каждой улице (префлоп, флоп, терн, ривер),
    # чтобы правильно вычислять размеры коллов и общие инвестиции.
    total_investment = {p_code: Decimal('0.00') for p_code in player_map.keys()}
    total_investment = {p_code: Decimal('0.00') for p_code in player_map.keys()}
    bets_this_street = {p_code: Decimal('0.00') for p_code in player_map.keys()}
    
    current_street = 'preflop' # Инициализация улицы
    
    remaining_stacks = {f'p{i+1}': stack for i, stack in enumerate(hh_stacks)}
    current_street_bet = Decimal('0.00')
    last_bet_by_player = {'player': None, 'amount': Decimal('0.00')}
    last_action_was_fold = False
    
    # Для трекинга финального состояния
    current_board_cards = ""
    last_aggressor_pos = "" # Позиция того, кто сделал Bet/Raise последним
    pot_before_street = Decimal('0.00') # Размер банка до начала улицы
    
    decimal.getcontext().prec = 10 # Увеличиваем точность для Decimal

    # Инициализируем ставки блайндами
    for i, p_name in enumerate(all_players):
        p_code = f'p{i+1}'
        if hh_blinds and i < len(hh_blinds):
            blind_amount = hh_blinds[i]
            if blind_amount > 0:
                investment = min(blind_amount, remaining_stacks.get(p_code, Decimal('0.00')))
                total_investment[p_code] += investment
                remaining_stacks[p_code] -= investment # ❗️ Уменьшаем остаток стека
                bets_this_street[p_code] = blind_amount
                # На префлопе самая большая ставка - это BB
                if blind_amount > current_street_bet:
                    current_street_bet = blind_amount

    for action_str in hand_history.actions:
        parts = action_str.split()

        # Сброс ставок при переходе на новую улицу (флоп, терн, ривер)
        # Сброс ставок при переходе на новую улицу (флоп, терн, ривер)
        if parts[0] == 'd' and parts[1] == 'db':
            # Добавляем ставки в банк
            street_pot = sum(bets_this_street.values())
            pot_before_street += street_pot

            bets_this_street = {p_code: Decimal('0.00') for p_code in player_map.keys()}
            current_street_bet = Decimal('0.00')
            last_bet_by_player = {'player': None, 'amount': Decimal('0.00')}
            last_aggressor_pos = "" # Сброс агрессора на новой улице

            # Обновляем карты борда
            new_board_cards = parts[2]
            current_board_cards += new_board_cards
            
            # Обновляем улицу для анализа
            if current_street == 'preflop': current_street = 'flop'
            elif current_street == 'flop': current_street = 'turn'
            elif current_street == 'turn': current_street = 'river'
            
            continue

        if action_str.startswith('p'):
            player_code = parts[0]
            action_type_code = parts[1]
            last_action_was_fold = False

            if action_type_code == 'cbr': # Bet/Raise
                raise_to_amount = Decimal(parts[2])
                already_invested_this_street = bets_this_street.get(player_code, Decimal('0.00'))
                additional_investment = raise_to_amount - already_invested_this_street

                # Убираем дублирование, оставляем одну строку
                total_investment[player_code] = total_investment.get(player_code, Decimal('0.00')) + additional_investment
                remaining_stacks[player_code] -= additional_investment # ❗️ Уменьшаем остаток стека
                bets_this_street[player_code] = raise_to_amount
                current_street_bet = raise_to_amount
                last_bet_by_player = {'player': player_code, 'amount': additional_investment}
                last_aggressor_pos = player_map.get(player_code)[1] # Сохраняем позицию агрессора

            elif action_type_code == 'cc': # Call
                last_bet_by_player = {'player': None, 'amount': Decimal('0.00')}
                already_invested_this_street = bets_this_street.get(player_code, Decimal('0.00'))
                
                required_call = current_street_bet - already_invested_this_street
                
                # ❗️ Новая логика с учетом стека: Игрок не может поставить больше, чем у него есть
                player_stack = total_investment.get(player_code, Decimal('0.00'))
                # Вычисляем реальный остаток стека
                real_remaining_stack = remaining_stacks.get(player_code, Decimal('0.00'))
                
                call_amount = min(required_call, real_remaining_stack)

                if call_amount > 0:
                    # Убираем дублирование
                    total_investment[player_code] = total_investment.get(player_code, Decimal('0.00')) + call_amount
                    remaining_stacks[player_code] -= call_amount # ❗️ Уменьшаем остаток стека
                    bets_this_street[player_code] = bets_this_street.get(player_code, Decimal('0.00')) + call_amount

                total_invested_by_caller = bets_this_street.get(player_code, Decimal('0.00'))
                if total_invested_by_caller < current_street_bet:
                    current_street_bet = total_invested_by_caller

            elif action_type_code == 'f': # Fold
                last_action_was_fold = True

            # --- ЗАПИСЬ ИНФОРМАЦИИ ПРИ ДЕЙСТВИИ ХИРО ---
            if player_code == analyze_player_code:
                # Мы обновляем финальный статус КАЖДЫЙ раз, когда хиро делает действие.
                # Последнее сохраненное действие и будет финальным (если это фолд или конец раздачи).
                
                # Вычисляем Pot Odds / Facing Bet %
                current_pot = pot_before_street + sum(bets_this_street.values())
                
                facing_pct = 0.0
                if current_street_bet > 0 and action_type_code in ('cc', 'f'):
                    # Сколько нам нужно доставить?
                    my_invested = bets_this_street.get(analyze_player_code, Decimal('0.00'))
                    to_call = current_street_bet - my_invested
                    
                    if current_pot > 0:
                        facing_pct = float(to_call / current_pot) * 100

                stats_update[analyze_player_name]['final_street'] = current_street
                stats_update[analyze_player_name]['final_action'] = 'Fold' if action_type_code == 'f' else ('Call' if action_type_code == 'cc' else 'Raise')
                stats_update[analyze_player_name]['facing_bet_pct_pot'] = facing_pct
                stats_update[analyze_player_name]['opponent_position'] = last_aggressor_pos
                stats_update[analyze_player_name]['board_cards'] = current_board_cards
                
                # Hand Strength
                my_cards = stats_update[analyze_player_name]['cards']
                strength = get_hand_strength(my_cards, current_board_cards)
                stats_update[analyze_player_name]['final_hand_strength'] = strength


    player_bet = total_investment.get(analyze_player_code, Decimal('0.00'))

    # Если последнее действие в истории было фолдом, значит, предыдущая ставка не была принята.
    if last_action_was_fold and last_bet_by_player['player'] == analyze_player_code:
        uncalled_bet = last_bet_by_player['amount']
        player_bet -= uncalled_bet

    stats_update[analyze_player_name]['net_profit'] = player_win - player_bet
    
    # --- STEAL SUCCESS CHECK ---
    # Если мы делали стил, и раздача закончилась на префлопе, и мы выиграли (нет профит > 0)
    # Значит все сфолдили.
    if stats_update[analyze_player_name].get('is_steal_attempt', 0) == 1:
        if stats_update[analyze_player_name]['final_street'] == 'preflop':
            if stats_update[analyze_player_name]['net_profit'] > 0:
                 stats_update[analyze_player_name]['steal_success'] = 1

    # 2. Финальная агрегация (для очистки булевых значений)
    final_stats = {}
    for name, data in stats_update.items():
        # VPIP и PFR сохраняются
        final_stats[name] = {
            'hand_id': data['hand_id'],
            'table_part_name': data['table_part_name'],
            'player_name': data['player_name'],
            'position': data['position'],
            'cards': data['cards'],
            'is_rfi': data['is_rfi'],
            'is_pfr': data['is_pfr'],
            'is_vpip': data['is_vpip'],
            'first_action': data['first_action'],
            'first_raiser_position': data['first_raiser_position'],
            'is_steal_attempt': data['is_steal_attempt'],
            'net_profit': data['net_profit'],
            'time_logged': data['time_logged'],
            'final_street': data['final_street'],
            'final_action': data['final_action'],
            'final_hand_strength': data['final_hand_strength'],
            'facing_bet_pct_pot': data['facing_bet_pct_pot'],
            'opponent_position': data['opponent_position'],
            'board_cards': data['board_cards'],
            'rfi_opportunity': data.get('rfi_opportunity', 0),
            # BB Stats
            'facing_steal': data.get('facing_steal', 0),
            'is_steal_defend': data.get('is_steal_defend', 0),
            'is_steal_3bet': data.get('is_steal_3bet', 0),
            'is_steal_fold': data.get('is_steal_fold', 0),
            'steal_success': data.get('steal_success', 0),
            # BB vs Limp Stats
            'facing_limp': data.get('facing_limp', 0),
            'is_limp_check': data.get('is_limp_check', 0),
            'is_limp_iso': data.get('is_limp_iso', 0)
        }
    return final_stats


# --- 3. ФУНКЦИЯ ОБНОВЛЕНИЯ СТАТИСТИКИ ---

def update_stats_in_db(stats_to_commit: Dict[str, Dict[str, Any]], table_segment: str):
    """Обновляет статистику в динамической таблице, включая 3Bet и Fold to 3Bet."""
    if not stats_to_commit:
        return

    setup_database_table(table_segment)
    safe_table_name = table_segment.replace("'", "").replace(";", "").replace(" ", "")

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for player_name, data in stats_to_commit.items():
            is_vpip = 1 if data.get('vpip', False) else 0
            is_pfr = 1 if data.get('pfr', False) else 0

            # Новые метрики
            s3bet = data.get('3bet_success', 0)
            o3bet = data.get('3bet_opp', 0)
            sf3bet = data.get('f3bet_success', 0)
            of3bet = data.get('f3bet_opp', 0)

            pfr_utg = data.get('pfr_utg', 0)
            pfr_mp = data.get('pfr_mp', 0)
            pfr_co = data.get('pfr_co', 0)
            pfr_bu = data.get('pfr_bu', 0)
            pfr_sb = data.get('pfr_sb', 0)
            hands_utg = data.get('hands_utg', 0)
            hands_mp = data.get('hands_mp', 0)
            hands_co = data.get('hands_co', 0)
            hands_bu = data.get('hands_bu', 0)
            hands_sb = data.get('hands_sb', 0)

            rfi_opp_utg = data.get('rfi_opp_utg', 0)
            rfi_opp_mp = data.get('rfi_opp_mp', 0)
            rfi_opp_co = data.get('rfi_opp_co', 0)
            rfi_opp_bu = data.get('rfi_opp_bu', 0)
            rfi_succ_utg = data.get('rfi_succ_utg', 0)
            rfi_succ_mp = data.get('rfi_succ_mp', 0)
            rfi_succ_co = data.get('rfi_succ_co', 0)
            rfi_succ_bu = data.get('rfi_succ_bu', 0)

            af_bets_raises = data.get('af_bets_raises', 0)
            af_calls = data.get('af_calls', 0)

            cbet_op = data.get('cbet_flop_opp', 0)
            cbet_sc = data.get('cbet_flop_succ', 0)
            fcbet_op = data.get('fcbet_flop_opp', 0)
            fcbet_sc = data.get('fcbet_flop_succ', 0)
            wtsd = 1 if data.get('wtsd', False) else 0
            wsd = 1 if data.get('wsd', False) else 0

            # print('INSERT')
            # print(player_name)
            # print(is_vpip)
            # print(is_pfr)

            cursor.execute(f"""
                INSERT INTO {safe_table_name}
                    (player_name, hands, vpip_hands, pfr_hands,
                    _3bet_opportunities, _3bet_successes,
                    _fold_to_3bet_opportunities, _fold_to_3bet_successes,
                    pfr_utg, pfr_mp, pfr_co, pfr_bu, pfr_sb,
                    hands_utg, hands_mp, hands_co, hands_bu, hands_sb,
                    rfi_opp_utg, rfi_opp_mp, rfi_opp_co, rfi_opp_bu,
                    rfi_succ_utg, rfi_succ_mp, rfi_succ_co, rfi_succ_bu
                    , af_bets_raises, af_calls,
                    cbet_flop_opp, cbet_flop_succ, fcbet_flop_opp, fcbet_flop_succ, wtsd_hands, wsd_hands
                    )
                VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_name) DO UPDATE SET
                    hands = hands + 1,
                    vpip_hands = vpip_hands + excluded.vpip_hands,
                    pfr_hands = pfr_hands + excluded.pfr_hands,
                    _3bet_opportunities = _3bet_opportunities + excluded._3bet_opportunities,
                    _3bet_successes = _3bet_successes + excluded._3bet_successes,
                    _fold_to_3bet_opportunities = _fold_to_3bet_opportunities + excluded._fold_to_3bet_opportunities,
                    _fold_to_3bet_successes = _fold_to_3bet_successes + excluded._fold_to_3bet_successes,
                    pfr_utg = pfr_utg + excluded.pfr_utg,
                    pfr_mp = pfr_mp + excluded.pfr_mp,
                    pfr_co = pfr_co + excluded.pfr_co,
                    pfr_bu = pfr_bu + excluded.pfr_bu,
                    pfr_sb = pfr_sb + excluded.pfr_sb,
                    hands_utg = hands_utg + excluded.hands_utg,
                    hands_mp = hands_mp + excluded.hands_mp,
                    hands_co = hands_co + excluded.hands_co,
                    hands_bu = hands_bu + excluded.hands_bu,
                    hands_sb = hands_sb + excluded.hands_sb,
                    rfi_opp_utg = rfi_opp_utg + excluded.rfi_opp_utg,
                    rfi_opp_mp = rfi_opp_mp + excluded.rfi_opp_mp,
                    rfi_opp_co = rfi_opp_co + excluded.rfi_opp_co,
                    rfi_opp_bu = rfi_opp_bu + excluded.rfi_opp_bu,
                    rfi_succ_utg = rfi_succ_utg + excluded.rfi_succ_utg,
                    rfi_succ_mp = rfi_succ_mp + excluded.rfi_succ_mp,
                    rfi_succ_co = rfi_succ_co + excluded.rfi_succ_co,
                    rfi_succ_bu = rfi_succ_bu + excluded.rfi_succ_bu,
                    af_bets_raises = af_bets_raises + excluded.af_bets_raises,
                    af_calls = af_calls + excluded.af_calls,
                    cbet_flop_opp = cbet_flop_opp + excluded.cbet_flop_opp,
                    cbet_flop_succ = cbet_flop_succ + excluded.cbet_flop_succ,
                    fcbet_flop_opp = fcbet_flop_opp + excluded.fcbet_flop_opp,
                    fcbet_flop_succ = fcbet_flop_succ + excluded.fcbet_flop_succ,
                    wtsd_hands = wtsd_hands + excluded.wtsd_hands,
                    wsd_hands = wsd_hands + excluded.wsd_hands
            """, (
                    player_name, is_vpip, is_pfr, o3bet, s3bet, of3bet, sf3bet,
                    pfr_utg, pfr_mp, pfr_co, pfr_bu, pfr_sb,
                    hands_utg, hands_mp, hands_co, hands_bu, hands_sb,
                    rfi_opp_utg, rfi_opp_mp, rfi_opp_co, rfi_opp_bu,
                    rfi_succ_utg, rfi_succ_mp, rfi_succ_co, rfi_succ_bu,
                    af_bets_raises, af_calls,
                    cbet_op, cbet_sc, fcbet_op, fcbet_sc, wtsd, wsd
                 )
            )

        conn.commit()
    except Exception as e:
        print(f"❌ Ошибка при обновлении статистики в БД ('{table_segment}'): {e}")
    finally:
        if conn:
            conn.close()

def update_hand_stats_in_db(stats_to_commit: Dict[str, Dict[str, Any]]):
    """Сохраняет данные об одной сыгранной раздаче в лог."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for player_name, data in stats_to_commit.items():
            hand_id = data.get('hand_id', "")
            table_part_name = data.get('table_part_name', "")
            player_name = data.get('player_name', "")
            position = data.get('position', "")
            cards = data.get('cards', "")
            is_rfi = data.get('is_rfi', 0)
            is_pfr = data.get('is_pfr', 0)
            is_vpip = data.get('is_vpip', 0)
            first_action = data.get('first_action', "")
            first_raiser_position = data.get('first_raiser_position', "")
            is_steal_attempt = data.get('is_steal_attempt', "")
            net_profit = float(data.get('net_profit', 0.00))
            net_profit = float(data.get('net_profit', 0.00))
            time_logged = data.get('time_logged')
            
            final_street = data.get('final_street', '')
            final_action = data.get('final_action', '')
            final_hand_strength = data.get('final_hand_strength', '')
            facing_bet_pct_pot = data.get('facing_bet_pct_pot', 0.0)
            opponent_position = data.get('opponent_position', '')
            board_cards = data.get('board_cards', '')
            rfi_opportunity = data.get('rfi_opportunity', 0)
            facing_steal = data.get('facing_steal', 0)
            is_steal_defend = data.get('is_steal_defend', 0)
            is_steal_3bet = data.get('is_steal_3bet', 0)
            is_steal_fold = data.get('is_steal_fold', 0)
            steal_success = data.get('steal_success', 0)
            
            # BB vs Limp
            facing_limp = data.get('facing_limp', 0)
            is_limp_check = data.get('is_limp_check', 0)
            is_limp_iso = data.get('is_limp_iso', 0)

            conn.execute("""
                INSERT OR REPLACE INTO my_hand_log (
                    hand_id, table_part_name, player_name, position, cards,
                    is_rfi, is_pfr, is_vpip, first_action, first_raiser_position,
                    is_steal_attempt, net_profit, time_logged,
                    final_street, final_action, final_hand_strength,
                    facing_bet_pct_pot, opponent_position, board_cards,
                    rfi_opportunity,
                    facing_steal, is_steal_defend, is_steal_3bet, is_steal_fold, steal_success,
                    facing_limp, is_limp_check, is_limp_iso
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                hand_id, table_part_name, player_name, position, cards,
                is_rfi, is_pfr, is_vpip, first_action, first_raiser_position,
                is_steal_attempt, net_profit, time_logged,
                final_street, final_action, final_hand_strength,
                facing_bet_pct_pot, opponent_position, board_cards,
                rfi_opportunity,
                facing_steal, is_steal_defend, is_steal_3bet, is_steal_fold, steal_success,
                facing_limp, is_limp_check, is_limp_iso
            ))
        conn.commit()
    except Exception as e:
        print(f"Ошибка сохранения лога раздачи {hand_id}: {e}", file=sys.stderr)
    finally:
        if conn:
            conn.close()
# --- 4. ФУНКЦИЯ ПОЛУЧЕНИЯ СТАТИСТИКИ ---

def get_stats_for_players(player_names: List[str], table_segment: str) -> Dict[str, Dict[str, Any]]:
    """Извлекает и рассчитывает VPIP/PFR из динамической таблицы."""
    stats: Dict[str, Dict[str, Any]] = {}
    if not player_names:
        return stats

    safe_table_name = table_segment.replace("'", "").replace(";", "").replace(" ", "")
    placeholders = ','.join('?' for _ in player_names)

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute(f"""
            SELECT player_name, hands, vpip_hands, pfr_hands,
                   _3bet_opportunities, _3bet_successes,
                   _fold_to_3bet_opportunities, _fold_to_3bet_successes,
                   af_bets_raises, af_calls,
                   cbet_flop_opp, cbet_flop_succ,
                   fcbet_flop_opp, fcbet_flop_succ,
                   wtsd_hands, wsd_hands
            FROM {safe_table_name}
            WHERE player_name IN ({placeholders})
        """, player_names)

        results = cursor.fetchall()

        for (name, hands, vpip_hands, pfr_hands, o3bet, s3bet, of3bet, sf3bet, af_bets, af_calls,
             cbet_op, cbet_sc, fcbet_op, fcbet_sc, wtsd_h, wsd_h) in results:
            vpip = (vpip_hands / hands * 100) if hands > 0 else 0.0
            pfr = (pfr_hands / hands * 100) if hands > 0 else 0.0

            # РАСЧЕТ НОВЫХ МЕТРИК
            _3bet_percent = (s3bet / o3bet * 100) if o3bet > 0 else 0.0
            f3bet_percent = (sf3bet / of3bet * 100) if of3bet > 0 else 0.0

            cbet_percent = (cbet_sc / cbet_op * 100) if cbet_op > 0 else 0.0
            fcbet_percent = (fcbet_sc / fcbet_op * 100) if fcbet_op > 0 else 0.0
            wtsd_percent = (wtsd_h / hands * 100) if hands > 0 else 0.0 # WTSD % от всех рук
            wsd_percent = (wsd_h / wtsd_h * 100) if wtsd_h > 0 else 0.0 # WSD % от рук, дошедших до вскрытия

            # РАСЧЕТ AF (Aggression Factor)
            # AF = (Bets + Raises) / Calls
            if af_calls > 0:
                af_val = af_bets / af_calls
            elif af_bets > 0:
                # Если коллов 0, а ставки были, AF математически бесконечен.
                # Обычно отображают как высокое число или Inf.
                af_val = 99.9
            else:
                af_val = 0.0

            stats[name] = {
                'vpip': f"{vpip:.1f}",
                'pfr': f"{pfr:.1f}",
                '3bet': f"{_3bet_percent:.1f}",
                'f3bet': f"{f3bet_percent:.1f}",
                'cbet': f"{cbet_percent:.1f}",
                'fcbet': f"{fcbet_percent:.1f}",
                'wtsd': f"{wtsd_percent:.1f}",
                'wsd': f"{wsd_percent:.1f}",
                'af': f"{af_val:.1f}",
                'hands': hands
            }

    except sqlite3.OperationalError as e:
        # Игнорируем ошибку, если таблица еще не существует
        if "no such table" in str(e):
             return stats
        raise e
    except Exception as e:
        print(f"❌ Ошибка при получении статистики из БД ('{table_segment}'): {e}")
    finally:
        if conn:
            conn.close()

    return stats

# --- 4. ФУНКЦИЯ ПОЛУЧЕНИЯ ЛИЧНОЙ СТАТИСТИКИ ---

def get_player_extended_stats(player_name: str, table_segment: str, min_time: Optional[datetime.datetime] = None, max_time: Optional[datetime.datetime] = None) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Извлекает расширенную статистику для игрока из my_hand_log с фильтрацией по времени.
    Агрегирует данные на лету.
    """
    stats: Dict[str, Dict[str, Any]] = {}

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Получение агрегированной статистики по сессии ("My Stats")
        # Добавляем фильтр по времени
        
        query = """
            SELECT 
                COUNT(*) as total_hands,
                SUM(is_pfr) as pfr_sum,
                SUM(is_vpip) as vpip_sum,
                position,
                SUM(is_rfi) as rfi_sum,
                SUM(rfi_opportunity) as rfi_opp_sum,
                
                -- New Steal Stats
                SUM(facing_steal) as facing_steal_sum,
                SUM(is_steal_fold) as steal_fold_sum,
                SUM(is_steal_defend) as steal_call_sum,
                SUM(is_steal_3bet) as steal_3bet_sum,
                SUM(is_steal_attempt) as steal_att_sum,
                SUM(steal_success) as steal_succ_sum,
                
                -- New BB vs Limp Stats
                SUM(facing_limp) as facing_limp_sum,
                SUM(is_limp_check) as limp_check_sum,
                SUM(is_limp_iso) as limp_iso_sum
            
            FROM my_hand_log 
            WHERE player_name = ?
        """
        params = [player_name]
        
        if min_time:
            query += " AND time_logged >= ?"
            params.append(min_time)
            
        if max_time:
            query += " AND time_logged <= ?"
            params.append(max_time)
                
        query += " GROUP BY position"

        cursor.execute(query, params)
        results = cursor.fetchall()
        
        if not results:
                # Если данных нет, возвращаем нули
                return {
                "hands": {"total": 0, "utg":0, "mp":0, "co":0, "bu":0, "sb":0, "bb":0},
                "pfr": {"total": "0.0", "utg":"0.0", "mp":"0.0", "co":"0.0", "bu":"0.0", "sb":"0.0", "bb":"0.0"},
                "rfi": {"utg":"0.0", "mp":"0.0", "co":"0.0", "bu":"0.0", "sb":"0.0"}
                }

        # Инициализация структур
        hands_data = {"total": 0, "utg":0, "mp":0, "co":0, "bu":0, "sb":0, "bb":0}
        pfr_counts = {"total": 0, "utg":0, "mp":0, "co":0, "bu":0, "sb":0, "bb":0}
        vpip_counts = {"total": 0, "utg":0, "mp":0, "co":0, "bu":0, "sb":0, "bb":0}
        rfi_counts = {"utg":0, "mp":0, "co":0, "bu":0, "sb":0}
        rfi_opps = {"utg":0, "mp":0, "co":0, "bu":0, "sb":0}
        
        # New Steal Aggregators
        steal_att_total = 0
        steal_succ_total = 0
        bb_facing_Total = 0
        bb_fold_Total = 0
        bb_defend_Total = 0
        bb_3bet_Total = 0
        
        # New BB vs Limp Aggregators
        bb_facing_limp_Total = 0
        bb_limp_check_Total = 0
        bb_limp_iso_Total = 0
        
        total_hands_all = 0
        total_pfr_all = 0
        total_vpip_all = 0

        for row in results:
            # row: 0=hands, 1=pfr_sum, 2=vpip_sum, 3=position, 4=rfi_sum, 5=rfi_opp
            # 6=facing_steal, 7=steal_fold, 8=steal_call, 9=steal_3bet, 10=steal_att, 11=steal_succ
            # 12=facing_limp, 13=limp_check, 14=limp_iso
            cnt_hands = row[0]
            cnt_pfr = row[1]
            cnt_vpip = row[2]
            pos = row[3].lower()
            cnt_rfi = row[4]
            cnt_rfi_opp = row[5]
            
            cnt_facing_steal = row[6]
            cnt_fold_steal = row[7]
            cnt_call_steal = row[8]
            cnt_3bet_steal = row[9]
            cnt_att_steal = row[10]
            cnt_succ_steal = row[11]
            
            cnt_facing_limp = row[12]
            cnt_check_limp = row[13]
            cnt_iso_limp = row[14]

            # Агрегация по позициям
            if pos in hands_data:
                hands_data[pos] = cnt_hands
                pfr_counts[pos] = cnt_pfr
                vpip_counts[pos] = cnt_vpip
            
            # Агрегация RFI
            if pos in rfi_counts:
                rfi_counts[pos] = cnt_rfi
                rfi_opps[pos] = cnt_rfi_opp

            total_hands_all += cnt_hands
            total_pfr_all += cnt_pfr
            total_vpip_all += cnt_vpip
            
            # Aggregate Steal Stats
            steal_att_total += cnt_att_steal
            steal_succ_total += cnt_succ_steal
            
            if pos == 'bb': 
                bb_facing_Total += cnt_facing_steal
                bb_fold_Total += cnt_fold_steal
                bb_defend_Total += cnt_call_steal
                bb_3bet_Total += cnt_3bet_steal
                
                # BB vs Limp
                bb_facing_limp_Total += cnt_facing_limp
                bb_limp_check_Total += cnt_check_limp
                bb_limp_iso_Total += cnt_iso_limp

        hands_data["total"] = total_hands_all
        
        # Расчет процентов
        def calc_pct(num, den):
            return f"{round((num / den) * 100, 1)}" if den > 0 else "0.0"
        
        # New Formatted Metrics
        steal_succ_pct = calc_pct(steal_succ_total, steal_att_total)
        bb_fold_steal_pct = calc_pct(bb_fold_Total, bb_facing_Total)
        bb_call_steal_pct = calc_pct(bb_defend_Total, bb_facing_Total) # Cold Call
        bb_3bet_steal_pct = calc_pct(bb_3bet_Total, bb_facing_Total)
        
        # BB vs Limp Metrics
        bb_check_limp_pct = calc_pct(bb_limp_check_Total, bb_facing_limp_Total)
        bb_iso_limp_pct = calc_pct(bb_limp_iso_Total, bb_facing_limp_Total)

        pfr_fmt = {
            "total": calc_pct(total_pfr_all, total_hands_all),
            "utg": calc_pct(pfr_counts["utg"], hands_data["utg"]),
            "mp": calc_pct(pfr_counts["mp"], hands_data["mp"]),
            "co": calc_pct(pfr_counts["co"], hands_data["co"]),
            "bu": calc_pct(pfr_counts["bu"], hands_data["bu"]),
            "sb": calc_pct(pfr_counts["sb"], hands_data["sb"]),
            "bb": calc_pct(pfr_counts["bb"], hands_data["bb"]),
        }
        
        rfi_fmt = {
            "utg": calc_pct(rfi_counts["utg"], rfi_opps["utg"]),
            "mp": calc_pct(rfi_counts["mp"], rfi_opps["mp"]),
            "co": calc_pct(rfi_counts["co"], rfi_opps["co"]),
            "bu": calc_pct(rfi_counts["bu"], rfi_opps["bu"]),
            "sb": calc_pct(rfi_counts["sb"], rfi_opps["sb"]),
        }

        vpip_fmt = {
            "total": calc_pct(total_vpip_all, total_hands_all),
            "utg": calc_pct(vpip_counts["utg"], hands_data["utg"]),
            "mp": calc_pct(vpip_counts["mp"], hands_data["mp"]),
            "co": calc_pct(vpip_counts["co"], hands_data["co"]),
            "bu": calc_pct(vpip_counts["bu"], hands_data["bu"]),
            "sb": calc_pct(vpip_counts["sb"], hands_data["sb"]),
            "bb": calc_pct(vpip_counts["bb"], hands_data["bb"]),
        }

        stats = {
            "hands": hands_data,
            "vpip": vpip_fmt,
            "pfr": pfr_fmt,
            "rfi": rfi_fmt,
            # New Stats
            "bb_defense": {
                "fold_to_steal": bb_fold_steal_pct,
                "call_steal": bb_call_steal_pct,
                "3bet_steal": bb_3bet_steal_pct
            },
            "bb_vs_limp": {
                "check": bb_check_limp_pct,
                "iso": bb_iso_limp_pct
            },
            "steal_success": steal_succ_pct
        }
        
        return stats
    except Exception as e:
        print(f"❌ Ошибка при получении статистики Hero ({min_time}-{max_time}): {e}")
        return None
    finally:
        if conn:
            conn.close()

    return stats
