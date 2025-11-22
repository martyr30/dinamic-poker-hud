# poker_stats_db.py

import sqlite3
import decimal
import datetime
from typing import Dict, Any, List, Optional
from pokerkit import HandHistory
# Добавляем импорт для генерации имени таблицы
from poker_globals import DB_NAME, ACTION_POSITIONS, ALL_STATS_FIELDS, get_table_name_segment

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
                rfi_succ_bu INTEGER DEFAULT 0
            )
        """)

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
                time_logged DATETIME DEFAULT CURRENT_TIMESTAMP,

                PRIMARY KEY (hand_id, player_name)
            );
        """)
        conn.commit()
    except Exception as e:
        print(f"❌ Ошибка при настройке таблицы '{table_segment}': {e}")
    finally:
        if conn:
            conn.close()

def setup_database():
    """Инициализация базы данных (не создает таблицы, так как они динамические)."""
    pass

def determine_position(player_index_p: int, num_players_in_hand: int) -> Optional[str]:
    """
    Определяет покерную позицию игрока (UTG/MP/CO/BU/SB/BB)
    на основе его индекса в порядке действий (1..N) и общего числа игроков.
    """

    if player_index_p == 1:
        return "sb"
    if player_index_p == 2:
        return "bb"

    num_action_positions = num_players_in_hand - 2
    skipped_positions = len(ACTION_POSITIONS) - num_action_positions
    first_active_position_index = skipped_positions
    action_index = player_index_p - 3
    final_pos_index = first_active_position_index + action_index

    if 0 <= final_pos_index < len(ACTION_POSITIONS):
        return ACTION_POSITIONS[final_pos_index]

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
            'rfi_succ_bu': 0
        }

    # --- Отслеживание префлоп-действий ---
    state = '0rfi' # 0rfi, 0bet, 2bet, 3bet

    # 1. Первый проход: Основные действия и определение 3-бетов
    for action_str in hand_history.actions:
        if action_str.startswith('d db'): # Конец префлопа
            break

        if action_str.startswith('p'):
            parts = action_str.split()
            player_code = parts[0]
            action_type_code = parts[1]
            player_name = player_map.get(player_code)[0]

            if not player_name:
                continue

            key_to_update = 'hands_' + player_map.get(player_code)[1]
            stats_update[player_name][key_to_update] = 1

            # --- RFI ---
            if state == '0rfi' and player_map.get(player_code)[1] in ('utg', 'mp', 'co', 'bu'):
                key_to_update = 'rfi_opp_' + player_map.get(player_code)[1]
                stats_update[player_name][key_to_update] = 1
                if action_type_code != 'f':
                    state = '0bet'
                    key_to_update = 'rfi_succ_' + player_map.get(player_code)[1]
                    stats_update[player_name][key_to_update] = 1

            # --- VPIP/PFR (Ваша логика) ---
            # cc (Call), rbr (Bet/Raise) - это VPIP
            if action_type_code in ('cc', 'cbr'):
                stats_update[player_name]['vpip'] = True
            # rbr (Raise) - это PFR
            if action_type_code in ('cbr'):
                stats_update[player_name]['pfr'] = True
                key_to_update = 'pfr_' + player_map.get(player_code)[1]
                stats_update[player_name][key_to_update] = 1

            # --- 3BET ЛОГИКА ---
            if state in ('0bet', '0rfi'):
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
            'rfi_succ_bu': data['rfi_succ_bu']
        }

    return final_stats

# --- 2.2 ФУНКЦИЯ АНАЛИЗА РАЗДАЧИ ИГРОКА ---
def analyze_player_stats(hand_history: HandHistory, analyze_player_name: str):
    stats_update = {}
    player_map = {}
    all_players = [p for p in hand_history.players]
    analyze_player_code = ""
    # Инициализация всех игроков
    for i, player_name in enumerate(all_players):
        if player_name == analyze_player_name:
            analyze_player_code = f'p{i + 1}'
            player_position = determine_position( i+1, len(all_players) )
            player_map[analyze_player_code] = [player_name, player_position]
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
                'time_logged': datetime.date(year=hand_history.year, month=hand_history.month, day=hand_history.day)
            }

    print("Старт анализа руки")
    print(hand_history.actions)
    # --- Отслеживание префлоп-действий ---
    state = '0rfi' # 0rfi, 0bet, 2bet, 3bet
    first_action = True

    # 1. Первый проход: Основные действия и определение 3-бетов
    for action_str in hand_history.actions:
        parts = action_str.split()
        print(parts)

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
            # --- RFI ---
            if player_code == analyze_player_code and state == '0rfi':
                stats_update[analyze_player_name]['is_rfi'] = 1

            if action_type_code != 'f':
                if state == '0rfi':
                    state = '0bet'

            # --- VPIP/PFR (Ваша логика) ---
            if player_code == analyze_player_code:
                # cc (Call), rbr (Bet/Raise) - это VPIP
                if action_type_code in ('cc', 'cbr'):
                    stats_update[analyze_player_name]['is_vpip'] = 1
                # rbr (Raise) - это PFR
                if action_type_code in ('cbr'):
                    stats_update[analyze_player_name]['is_pfr'] = 1

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
            'time_logged': data['time_logged']
        }
    print(final_stats)
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
                    )
                VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    rfi_succ_bu = rfi_succ_bu + excluded.rfi_succ_bu
            """, (
                    player_name, is_vpip, is_pfr, o3bet, s3bet, of3bet, sf3bet,
                    pfr_utg, pfr_mp, pfr_co, pfr_bu, pfr_sb,
                    hands_utg, hands_mp, hands_co, hands_bu, hands_sb,
                    rfi_opp_utg, rfi_opp_mp, rfi_opp_co, rfi_opp_bu,
                    rfi_succ_utg, rfi_succ_mp, rfi_succ_co, rfi_succ_bu
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
            time_logged = data.get('time_logged', "1990-01-01")

            conn.execute("""
                INSERT OR REPLACE INTO my_hand_log (
                    hand_id, table_part_name, player_name, position, cards,
                    is_rfi, is_pfr, is_vpip, first_action
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                hand_id, table_part_name, player_name, position, cards,
                is_rfi, is_pfr, is_vpip, first_action
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
                   _fold_to_3bet_opportunities, _fold_to_3bet_successes
            FROM {safe_table_name}
            WHERE player_name IN ({placeholders})
        """, player_names)

        results = cursor.fetchall()

        for name, hands, vpip_hands, pfr_hands, o3bet, s3bet, of3bet, sf3bet in results:
            vpip = (vpip_hands / hands * 100) if hands > 0 else 0.0
            pfr = (pfr_hands / hands * 100) if hands > 0 else 0.0

            # РАСЧЕТ НОВЫХ МЕТРИК
            _3bet_percent = (s3bet / o3bet * 100) if o3bet > 0 else 0.0
            f3bet_percent = (sf3bet / of3bet * 100) if of3bet > 0 else 0.0

            stats[name] = {
                'vpip': f"{vpip:.1f}",
                'pfr': f"{pfr:.1f}",
                '3bet': f"{_3bet_percent:.1f}",       # Добавлено
                'f3bet': f"{f3bet_percent:.1f}",      # Добавлено
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

def get_player_extended_stats(player_name: str, table_segment: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """Извлекает расширенную статистику по позициям для конкретного игрока."""
    stats: Dict[str, Dict[str, Any]] = {}
    if not player_name:
        return stats

    safe_table_name = table_segment.replace("'", "").replace(";", "").replace(" ", "")

    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Суммируем статистику по всем сегментам столов (т.к. это личный HUD)
        cursor.execute(f"""
            SELECT
                hands, pfr_hands, vpip_hands,
                hands_utg, pfr_utg,
                hands_mp, pfr_mp,
                hands_co, pfr_co,
                hands_bu, pfr_bu,
                hands_sb, pfr_sb,
                rfi_opp_utg, rfi_succ_utg,
                rfi_opp_mp, rfi_succ_mp,
                rfi_opp_co, rfi_succ_co,
                rfi_opp_bu, rfi_succ_bu
            FROM {safe_table_name}
            WHERE player_name = ?
        """, (player_name,))

        row = cursor.fetchone()
        results = cursor.fetchall()
        if not row or row[0] is None:
            return None

        # Порядок столбцов: total_hands, total_pfr_actions, total_vpip_actions, hands_utg, pfr_utg, ...

        # Вспомогательная функция для расчета PFR %
        def calculate_pfr_percent(actions, hands):
            return round((actions / hands) * 100, 1) if hands > 0 else 0.0

        # 1. Данные по рукам (Hands Data)
        hands_data = {
            "total": row[0] or 0,
            "utg": row[3] or 0,
            "mp": row[5] or 0,
            "co": row[7] or 0,
            "bu": row[9] or 0,
            "sb": row[11] or 0,
        }

        # 2. Данные по PFR (PFR %)
        pfr_data = {
            "total": calculate_pfr_percent(row[1] or 0, row[0] or 0),
            "utg": calculate_pfr_percent(row[4] or 0, row[3] or 0),
            "mp": calculate_pfr_percent(row[6] or 0, row[5] or 0),
            "co": calculate_pfr_percent(row[8] or 0, row[7] or 0),
            "bu": calculate_pfr_percent(row[10] or 0, row[9] or 0),
            "sb": calculate_pfr_percent(row[12] or 0, row[11] or 0),
        }

        # 3. Данные по RFI (RFI %)
        rfi_data = {
            "utg": calculate_pfr_percent(row[14] or 0, row[13] or 0),
            "mp": calculate_pfr_percent(row[16] or 0, row[15] or 0),
            "co": calculate_pfr_percent(row[18] or 0, row[17] or 0),
            "bu": calculate_pfr_percent(row[20] or 0, row[19] or 0),
        }


        # Возвращаем форматированные данные
        stats = {
            "hands": hands_data,
            "pfr": {k: f"{v:.1f}" for k, v in pfr_data.items()}, # Форматируем в строку с 1 знаком
            "rfi": {k: f"{v:.1f}" for k, v in rfi_data.items()}
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
