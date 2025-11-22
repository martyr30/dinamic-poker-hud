# poker_globals.py

from typing import Dict, Any, Tuple, List
import os
import decimal

# --- КОНСТАНТЫ ---
DB_NAME = 'poker_stats.db'
# Теперь это просто заглушка, имя стола будет определяться динамически.
TARGET_WINDOW_TITLE_PART = "poker table"
# Директория для мониторинга (устанавливается при запуске)
TARGET_HISTORY_DIR = '/Users/admin/Library/Application Support/PokerStars/HandHistory/Martyr40/'
# Словарь для отслеживания размера файла (для инкрементального парсинга)
FILE_SIZES: Dict[str, int] = {}

MY_PLAYER_NAME = "Martyr40"
# Структура для передачи данных: (file_path, list_of_player_names, table_title_part, table_segment)
StatUpdateData = Tuple[str, List[str], str, str]

ACTION_POSITIONS = ["utg", "mp", "co", "bu"]

ALL_STATS_FIELDS = [
    'pfr_utg', 'pfr_mp', 'pfr_co', 'pfr_bu', 'pfr_sb',
    'hands_utg', 'hands_mp', 'hands_co', 'hands_bu', 'hands_sb'
]

def get_table_name_segment(min_bet: decimal.Decimal, seat_count: int) -> str:
    """
    Генерирует уникальное имя таблицы для БД на основе лимита и количества мест.
    Пример: 'NL2_9MAX' (для $0.02)
    """
    # Преобразуем лимит в целое число центов (0.02 -> 2)
    limit_cents = int(min_bet * 100)

    limit_str = f"{limit_cents}"

    # Формат: 'NL' (No Limit) + Лимит + '_' + Количество мест + 'MAX'
    table_segment = f"NL{limit_str}_{seat_count}MAX"
    return table_segment
