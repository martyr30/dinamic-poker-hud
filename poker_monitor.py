# poker_monitor.py

import os
import time
import datetime
from typing import Optional, Dict, List
from PySide6.QtCore import QThread, Signal, QObject
from pokerkit import HandHistory
from poker_globals import FILE_SIZES, MY_PLAYER_NAME, ACTION_POSITIONS, StatUpdateData, get_table_name_segment
from poker_stats_db import (
    analyze_hand_for_stats,
    update_stats_in_db,
    analyze_player_stats,
    update_hand_stats_in_db
)
# --- КЛАСС СИГНАЛОВ ---

class MonitorSignals(QObject):
    """Сигналы, используемые для передачи обновлений из фонового потока в GUI."""
    # Сигнал для отправки обновленных данных HUD: (file_path, list_of_players, table_name, table_segment)
    stat_updated = Signal(object)


# --- ФУНКЦИИ ПАРСИНГА И АНАЛИЗА ---
def is_tournament_file(filename: str) -> bool:
    """
    Проверяет, является ли файл турнирным, основываясь на формате имени.
    Формат: HH<Дата> <Идентификатор> <Название>...
    Турнирный идентификатор - второе слово, содержащее буквы и цифры (T, S, F...)
    Пример: HH20251018 T3938561237 No Limit Hold'em ...
    """
    parts = filename.split(' ')
    if len(parts) > 1:
        identifier = parts[1]
        # Проверяем, что идентификатор содержит и буквы, и цифры, и не является 'No' (как в No Limit)
        if any(c.isalpha() for c in identifier) and any(c.isdigit() for c in identifier) and identifier.lower() != 'no':
             return True
    return False

def extract_table_name(file_path: str) -> Optional[str]:
    """
    Извлекает имя стола (например, 'Mensa II') из имени файла.
    """
    base_name = os.path.basename(file_path)
    name_no_ext = os.path.splitext(base_name)[0]

    first_space_index = name_no_ext.find(' ')
    if first_space_index == -1:
        return None

    separator_index = name_no_ext.find(' - ')

    if separator_index == -1:
        table_name = name_no_ext[first_space_index + 1:].strip()
    else:
        table_name = name_no_ext[first_space_index + 1:separator_index].strip()

    if table_name:
        return table_name

    return None


def process_file_update(file_path: str, filter_segment: Optional[str] = None, filter_date: Optional[str] = None) -> Optional[StatUpdateData]:
    """
    Парсит новую раздачу, ОБНОВЛЯЕТ БД и возвращает 4 значения.
    """

    filename = os.path.basename(file_path)

    # 1. ПРОВЕРКА НА ТУРНИРНЫЙ ФАЙЛ
    if is_tournament_file(filename):
        # Игнорируем турнирные файлы, но обновляем их размер, чтобы больше не читать
        current_size = os.path.getsize(file_path)
        FILE_SIZES[file_path] = current_size
        return None

    current_size = os.path.getsize(file_path)
    previous_size = FILE_SIZES.get(file_path, 0)

    if current_size <= previous_size:
        FILE_SIZES[file_path] = current_size
        return None

    table_title_part = extract_table_name(file_path)
    if not table_title_part:
        FILE_SIZES[file_path] = current_size
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            f.seek(previous_size)
            new_content = f.read()

        if not new_content.strip():
            FILE_SIZES[file_path] = current_size
            return None

        hhs_iterator = HandHistory.from_pokerstars(new_content, error_status=True)
        hhs_list = list(hhs_iterator)

        if not hhs_list:
            FILE_SIZES[file_path] = current_size
            return None


        # 1. Определение сегмента стола
        first_hh = hhs_list[0]
        min_bet = first_hh.min_bet
        seat_count = first_hh.seat_count
        table_segment = get_table_name_segment(min_bet, seat_count)
        date_segment = datetime.date(year=first_hh.year, month=first_hh.month, day=first_hh.day)

        print(f"📊 Сегмент стола: {table_segment}")

        if filter_segment and filter_segment != table_segment:
            print(f"   [LOAD] Пропуск {filename} -> Сегмент: {table_segment}")
            return

        if filter_date:
            filter_dt = datetime.datetime.strptime(filter_date, "%Y-%m-%d").date()
            if date_segment < filter_dt:
                print(f"   [LOAD] Пропуск {date_segment} -> Ранее: {filter_dt}")
                return

        last_players_committed = set() # Хранит игроков последней обработанной раздачи

        # 2. Обработка и запись в БД
        for i, hh in enumerate(hhs_list): # Используем enumerate для отслеживания последней раздачи
            stats_to_commit = analyze_hand_for_stats(hh)
            update_stats_in_db(stats_to_commit, table_segment)
            player_stats_to_commit = analyze_player_stats(hh, MY_PLAYER_NAME)
            update_hand_stats_in_db(player_stats_to_commit)
            # --- ИСПРАВЛЕНИЕ ОШИБКИ: Используем надежные ключи (имена-строки) ---
            current_hand_players = set(stats_to_commit.keys())

            # Если это последняя раздача в списке, сохраняем ее игроков
            if i == len(hhs_list) - 1:
                 last_players_committed = current_hand_players
            # --------------------------------------------------------------------


        FILE_SIZES[file_path] = current_size

        print(f"✅ Успешно обработана раздача. Обновление HUD для: {os.path.basename(file_path)}")

        # 3. ВОЗВРАЩАЕМ 4 ЗНАЧЕНИЯ (игроки только из последней раздачи)
        return (file_path, list(last_players_committed), table_title_part, table_segment)

    except Exception as e:
        print(f"❌ Критическая ошибка парсинга в {os.path.basename(file_path)}: {e}")
        # Печатаем сегмент стола, даже если произошла ошибка
        if 'table_segment' in locals():
            print(f"📊 Сегмент стола: {table_segment}")
        return None

def process_file_full_load(file_path: str, filter_segment: Optional[str] = None, filter_date: Optional[str] = None):
    """
    Обрабатывает ВЕСЬ файл целиком для режима полной загрузки.
    НЕ отправляет сигнал в HUD, только обновляет БД.
    """
    filename = os.path.basename(file_path)
    if is_tournament_file(filename):
        return

    table_title_part = extract_table_name(file_path)
    if not table_title_part:
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            full_content = f.read()

        if not full_content.strip():
            return

        hhs_iterator = HandHistory.from_pokerstars(full_content, error_status=True)
        hhs_list = list(hhs_iterator)

        if not hhs_list:
            return

        # Определение сегмента стола
        first_hh = hhs_list[0]
        min_bet = first_hh.min_bet
        seat_count = first_hh.seat_count
        table_segment = get_table_name_segment(min_bet, seat_count)
        date_segment = datetime.date(year=first_hh.year, month=first_hh.month, day=first_hh.day)

        # print(f"   [LOAD] Анализ {filename} -> Сегмент: {table_segment}")

        if filter_segment and filter_segment != table_segment:
            # print(f"   [LOAD] Пропуск {filename} -> Сегмент: {table_segment}")
            return

        if filter_date:
            filter_dt = datetime.datetime.strptime(filter_date, "%Y-%m-%d").date()
            if date_segment < filter_dt:
                # print(f"   [LOAD] Пропуск {date_segment} -> Ранее: {filter_dt}")
                return

        # Обработка и запись в БД
        for hh in hhs_list:
            stats_to_commit = analyze_hand_for_stats(hh)
            update_stats_in_db(stats_to_commit, table_segment)
            player_stats_to_commit = analyze_player_stats(hh, MY_PLAYER_NAME)
            # print(player_stats_to_commit)
            update_hand_stats_in_db(player_stats_to_commit)
        # Устанавливаем размер, чтобы монитор не читал его заново
        FILE_SIZES[file_path] = os.path.getsize(file_path)

    except Exception as e:
        print(f"❌ Ошибка полной загрузки в {filename}: {e}")

# --- ПОТОК МОНИТОРИНГА ---

class WatchdogThread(QThread):
    """Поток для мониторинга директории с файлами истории раздач."""
    def __init__(self, directory: str, signals: MonitorSignals, filter_segment: Optional[str] = None, filter_date: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.directory = directory
        self.signals = signals
        self._running = True
        self.filter_segment = filter_segment
        self.filter_date = filter_date

    def stop(self):
        self._running = False
        if self.isRunning():
             self.wait()

    def run(self):
        while self._running:
            try:
                for item in os.listdir(self.directory):
                    full_path = os.path.join(self.directory, item)

                    if os.path.isfile(full_path) and full_path.endswith('.txt'):
                        update_data = process_file_update(full_path, self.filter_segment, self.filter_date)

                        if update_data:
                            self.signals.stat_updated.emit(update_data)

            except Exception as e:
                print(f"❌ Ошибка в потоке мониторинга: {e}")

            self.msleep(500)
