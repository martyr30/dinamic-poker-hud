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
                        state = '0bet'
                        key_to_update = 'rfi_succ_' + player_map.get(player_code)[1]
                        stats_update[player_name][key_to_update] = 1

                # --- PFR ---
                if action_type_code == 'cbr':
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
    player_win = Decimal('0.00')
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
                'time_logged': datetime.date(year=hand_history.year, month=hand_history.month, day=hand_history.day)
            }
            
            # --- ОТЛАДОЧНЫЙ БЛОК ДЛЯ ПОИСКА ОШИБКИ ---
            try:
                # ВАЖНО: Проверяем, что список блайндов существует, прежде чем обращаться к нему
                # if hand_history.blinds_or_straddles and hand_history.blinds_or_straddles[i] != 0:
                #     player_bet = hand_history.blinds_or_straddles[i]
                # Аналогичная проверка для выигрышей
                if hand_history.winnings and i < len(hand_history.winnings) and hand_history.winnings[i] != 0:
                    player_win = hand_history.winnings[i]
            except IndexError:
                # Перевызываем ошибку, чтобы увидеть полный traceback
                raise
    # --- Отслеживание префлоп-действий ---
    state = '0rfi' # 0rfi, 0limp, 1bet, 3bet, 4bet
    first_action = True

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
            # --- RFI ---
            if player_code == analyze_player_code and state == '0rfi':
                stats_update[analyze_player_name]['is_rfi'] = 1

            if action_type_code != 'f':
                if action_type_code == 'cbr':
                    if state == '0rfi':
                        state = '1bet'
                        stats_update[analyze_player_name]['first_raiser_position'] = player_map.get(player_code)[1]
                        if player_map.get(player_code)[1] in ('co', 'bu', 'sb'):
                            stats_update[analyze_player_name]['is_steal_attempt'] = 1
                else:
                    state = '0limp'


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
    bets_this_street = {p_code: Decimal('0.00') for p_code in player_map.keys()}
    remaining_stacks = {f'p{i+1}': stack for i, stack in enumerate(hand_history.starting_stacks)}
    current_street_bet = Decimal('0.00')
    last_bet_by_player = {'player': None, 'amount': Decimal('0.00')}
    last_action_was_fold = False
    
    decimal.getcontext().prec = 10 # Увеличиваем точность для Decimal

    # Инициализируем ставки блайндами
    for i, p_name in enumerate(all_players):
        p_code = f'p{i+1}'
        if hand_history.blinds_or_straddles and i < len(hand_history.blinds_or_straddles):
            blind_amount = hand_history.blinds_or_straddles[i]
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
        if parts[0] == 'd' and parts[1] == 'db':
            bets_this_street = {p_code: Decimal('0.00') for p_code in player_map.keys()}
            current_street_bet = Decimal('0.00')
            last_bet_by_player = {'player': None, 'amount': Decimal('0.00')}
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

    player_bet = total_investment.get(analyze_player_code, Decimal('0.00'))

    # Если последнее действие в истории было фолдом, значит, предыдущая ставка не была принята.
    if last_action_was_fold and last_bet_by_player['player'] == analyze_player_code:
        uncalled_bet = last_bet_by_player['amount']
        player_bet -= uncalled_bet

    stats_update[analyze_player_name]['net_profit'] = player_win - player_bet
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
            'time_logged': data['time_logged']
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
            time_logged = data.get('time_logged', "1990-01-01")

            conn.execute("""
                INSERT OR REPLACE INTO my_hand_log (
                    hand_id, table_part_name, player_name, position, cards,
                    is_rfi, is_pfr, is_vpip, first_action, first_raiser_position,
                    is_steal_attempt, net_profit
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                hand_id, table_part_name, player_name, position, cards,
                is_rfi, is_pfr, is_vpip, first_action, first_raiser_position,
                is_steal_attempt, net_profit
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
