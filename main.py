import sys
import os
import signal
import argparse
import warnings

# Suppress warnings about 'time_zone_abbreviation' from pokerkit
warnings.filterwarnings("ignore", message="The field 'time_zone_abbreviation' is an unexpected field")

from typing import Dict, Any, Optional, List
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Slot, QObject, Signal, QCoreApplication, QRect
from PySide6.QtGui import QFont
if sys.platform != 'darwin':
    import pywinctl as pwc
else:
    pwc = None

# Импорт модулей проекта (предполагается, что они доступны)
from poker_globals import MY_PLAYER_NAME, TARGET_HISTORY_DIR, FILE_SIZES, StatUpdateData
from poker_monitor import WatchdogThread, MonitorSignals, process_file_full_load, is_tournament_file
from poker_stats_db import setup_database, get_stats_for_players, get_player_extended_stats, remove_database_files
from personal_stats_hud import PersonalStatsWindow
from datetime import datetime
# Import Custom MacOS Adapter to bypass pywinctl issues
from macos_window_utils import MacOSWindowAdapter
SESSION_START_TIME = datetime.now()

# --- КЛАСС HUD ОКНА ---

class HUDWindow(QWidget):
    """Отдельное окно HUD, привязанное к одному столу."""
    closed_table_detected = Signal(str)

    def __init__(self, file_path: str, target_title_part: str):
        super().__init__()

        self.setWindowTitle(f"HUD Tracker - {target_title_part}")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowDoesNotAcceptFocus |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # ВАЖНО: Делаем окно прозрачным для событий мыши, чтобы можно было кликать по столу сквозь HUD
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        # Убираем общий фон окна, теперь фон будет только у плашек игроков
        self.setStyleSheet("background-color: transparent;")

        # Используем абсолютное позиционирование (без Layout)
        # self.main_layout = QVBoxLayout(self) 

        self.status_label = QLabel(f"Ожидание окна: {target_title_part}...")
        font = QFont("Arial", 14, QFont.Weight.Bold)
        self.status_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.status_label.setStyleSheet("background-color: rgba(0, 0, 0, 100); color: white; padding: 5px; border-radius: 5px;")
        self.status_label.setParent(self) # Привязываем к окну
        self.status_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.status_label.move(10, 10)
        self.status_label.show()

        # --- Хранилище ---
        self.target_window = None
        # Смещения теперь 0, так как мы перекрываем окно целиком
        self.tracking_offset_x = 0
        self.tracking_offset_y = 0

        # Идентификаторы стола
        self.file_path = file_path
        self.active_table_name: str = target_title_part
        self.active_table_segment: Optional[str] = None
        self.current_table_players: Dict[str, int] = {} # Имя -> Номер места
        
        # Виджеты для игроков (храним ссылки на QLabel)
        self.player_widgets: Dict[str, QLabel] = {}

        self.hide()

        # Таймер для регулярного позиционирования
        self.pos_timer = QTimer(self)
        self.pos_timer.timeout.connect(self.update_hud_position)
        if sys.platform == 'darwin':
            self.pos_timer.start(500) # 500ms for macOS (osascript is slow)
        else:
            self.pos_timer.start(20) # 20ms for Windows/Linux

        # Таймер для задержки удаления (5 секунд)
        self.deletion_timer = QTimer(self)
        self.deletion_timer.setInterval(5000)
        self.deletion_timer.setSingleShot(True)
        self.deletion_timer.timeout.connect(self.finalize_deletion)

    # --- Методы управления ---

    def is_target_window_still_active(self, window_obj) -> bool:
        """Проверяет, существует ли объект окна pywinctl в списке активных окон по его ID."""
        if isinstance(window_obj, MacOSWindowAdapter):
            return window_obj.exists()

        if not window_obj:
            return False

        try:
            active_windows = pwc.getAllWindows()
            return window_obj.id in [w.id for w in active_windows]
        except Exception:
            return False

    def finalize_deletion(self):
        """Осуществляет окончательное удаление, если окно не найдено после таймаута."""
        # Проверяем в последний раз, что окно действительно не найдено
        if self.target_window is None and not self.find_target_window():
            print(f"HUD: Удаление окна {self.active_table_name} по тайм-ауту.")
            self.pos_timer.stop()
            self.closed_table_detected.emit(self.file_path)
            self.deleteLater()
        else:
            # Если окно найдено в последний момент, отменяем удаление
            self.deletion_timer.stop()
            if not self.isVisible():
                self.show()
                self.raise_()

    def find_target_window(self):
        """Находит целевое окно по имени стола."""
        # --- MACOS FIX ---
        if sys.platform == 'darwin':
            adapter = MacOSWindowAdapter(self.active_table_name)
            if adapter.exists():
                self.target_window = adapter
                # Ensure we have fresh geometry
                self.target_window.refresh()
                self.rect = QRect(adapter.left, adapter.top, adapter.width, adapter.height)
                # print(f"HUD FOUND (macOS): {self.active_table_name} -> {self.rect}")
                return True
            print("-" * 64)
            # Use AppleScript to list windows for debug
            # We simply print that we are on macOS
            print(" (macOS: pywinctl disabled. Check permissions or macos_window_utils logs)")
            print("-" * 64)
            return False
        # -----------------

        target_part = self.active_table_name

        try:
            windows = pwc.getAllWindows()
        except Exception:
            return False
        except Exception as e:
            print(f"HUD: Ошибка получения списка окон: {e}")
            return False


        candidates = []

        for win in windows:
            if target_part.lower() in win.title.lower():
                try:
                    app_name = win.ownerName
                except Exception:
                    app_name = "N/A"
                if 'terminal' in app_name.lower() or 'python' in app_name.lower() or 'pycharm' in app_name.lower() or 'code' in app_name.lower():
                    continue

                # *** ЗАЩИТА №1: Игнорировать окна, найденные в (0,0), ЕСЛИ они выглядят странно ***
                # Но для Mac (0,0) может быть валидным.
                # Поэтому пока используем мягкую проверку.
                try:
                    # Если окно явно за экраном (очень большие отрицательные координаты)
                    if win.left < -100 or win.top < -100:
                        continue
                except Exception:
                    continue # Окно нестабильно

                candidates.append(win)
        
        if not candidates:
            # Выводим отладку только если мы искали конкретный стол и не нашли
            if self.active_table_name:
                print(f"HUD DEBUG: Не найдено окно для '{self.active_table_name}'. Видимые окна:")
                for w in windows:
                     if w.title:
                        print(f"  - '{w.title}' | Owner: {w.ownerName}")
                print("----------------------------------------------------------------")
            self.target_window = None
            return False
        
        # Если найдено несколько кандидатов, выбираем первый (или можно добавить более сложную логику)
        self.target_window = candidates[0]
        return True

    def _get_player_color(self, vpip: float, pfr: float, hands: int) -> str:
        """
        Возвращает код цвета на основе VPIP/PFR.
        Принудительно устанавливает белый цвет, если рук меньше 100.
        """

        # 0. ⚪ Белый (Недостаточно данных)
        if hands < 100:
            return "white"

        # 1. 🟢 Зеленый (Лузово-Пассивный / Фиш)
        is_green = (vpip >= 30.0 and pfr < 15.0) or (vpip - pfr >= 15.0)
        if is_green: return "#4CAF50"

        # 2. 🔴 Красный (Лузово-Агрессивный / LAG/Маньяк)
        if vpip >= 28.0 and pfr >= 23.0: return "#F44336"

        # 3. 🟡 Желтый/Оранжевый (Нит)
        if vpip <= 15.0 and pfr <= 10.0: return "#FFC107"

        # 4. 🔵 Синий/Голубой (Сбалансированный / TAG)
        pfr_vpip_ratio = pfr / vpip if vpip > 0 else 0.0
        is_blue = (
            vpip >= 18.0 and vpip <= 27.0 and
            pfr >= 15.0 and
            pfr_vpip_ratio >= 0.75
        )
        if is_blue: return "#2196F3"

        # 5. ⚪ Белый/Серый (Дефолт / Неопределенный)
        return "white"

    def _clear_player_widgets(self):
        for widget in self.player_widgets.values():
            widget.deleteLater()
        self.player_widgets.clear()

    def _update_label_content(self, precalculated_stats: Dict[str, Any] = None):
        if precalculated_stats is None:
            precalculated_stats = {}
            
        player_names = list(self.current_table_players.keys())
        
        # USE PRE-CALCULATED STATS instead of fetching again on UI thread
        # precalculated_stats is {PlayerName: {Stats...}}
        player_stats = precalculated_stats
        
        # Fallback if empty (e.g. initial load or something), but MonitorThread should provide it.
        # If precalculated_stats is empty but we have players, maybe fetch? 
        # Ideally, we trust the thread.
        if self.active_table_segment and player_names and not player_stats:
             # Only fetch if not provided (fallback)
             try:
                 player_stats = get_stats_for_players(player_names, self.active_table_segment)
             except Exception as e:
                 print(f"HUD Error in get_stats_for_players: {e}")

        try:
            self._clear_player_widgets()
        except Exception as e:
            print(f"HUD Error in _clear_player_widgets: {e}")

        font = QFont("Arial", 13, QFont.Weight.Bold)

        if not self.current_table_players:
            table_info = f"Стол: {self.active_table_name}\nСегмент: {self.active_table_segment}" if self.active_table_name else "Неизвестно"
            self.status_label.setText(f"{table_info}\nОжидание игроков...")
            self.status_label.adjustSize()
            self.status_label.show()
        else:
            self.status_label.hide()
            
            # 1. Находим место Хиро (Martyr40)
            hero_seat = self.current_table_players.get(MY_PLAYER_NAME, 0)
            
            # --- СЕССИОННАЯ СТАТИСТИКА ДЛЯ HERO ---
            # Now handled by MonitorThread and merged into player_stats (precalculated_stats)
            # So we don't need to fetch it here.
            pass
             
             # --- HERO SESSION STATS ---
             # We can't easily move `get_player_extended_stats` to the thread fully 
             # without complexifying the signal payload (it returns a different structure).
             # However, since the user complained about blocking, we MUST optimization this.
             # Option 1: The thread sends basic stats.
             # Option 2: We accept that Hero stats might be slightly delayed or we fetch them async.
             # Since we are already here, let's keep it but check performance. 
             # Actually, the user said "Main window almost doesn't respond".
             # If we moved `get_stats_for_players` (bulk of data), that's a big win.
             # `get_player_extended_stats` is one complex query.
             # Let's wrap it in a try/except or skip if we feel like it, but for now 
             # let's assume moving the bulk `get_stats_for_players` helped enough.
             # TODO: Move Hero Session Stats to Thread if still laggy.

            # Если Хиро нет за столом (наблюдатель), считаем, что он на месте 0 (или 1) для отсчета
            if hero_seat == 0:
                # Пытаемся найти хоть какое-то место для отсчета, или оставляем 0
                pass

            for name, seat_num in self.current_table_players.items():
                # Пропускаем самого себя, если не хотим видеть свой HUD (или оставляем)
                # if name == MY_PLAYER_NAME: continue

                data = player_stats.get(name, {
                    'vpip': '0.0', 'pfr': '0.0',
                    '3bet': '0.0', 'f3bet': '0.0',
                    'cbet': '0.0', 'fcbet': '0.0',
                    'wtsd': '0.0', 'wsd': '0.0',
                    'af': '0.0',
                    'hands': 0
                })

                # 🌟 ИСПРАВЛЕНИЕ: Инициализируем переменные перед блоком try
                vpip_val = 0.0
                pfr_val = 0.0
                hands_val = 0

                try:
                    vpip_val = float(data['vpip'])
                    pfr_val = float(data['pfr'])
                    hands_val = int(data['hands'])
                except ValueError:
                    # Если произошла ошибка парсинга, используем значения по умолчанию (0.0/0).
                    # Переменные уже инициализированы, поэтому здесь ничего не меняем.
                    pass

                # Здесь hands_val ГАРАНТИРОВАННО определен.
                color_code = self._get_player_color(vpip_val, pfr_val, hands_val)

                hud_line = (
                    f"{name} ({data['hands']})\n"
                    f"{data['vpip']}/{data['pfr']}\n"
                    f"3B:{data['3bet']} F3B:{data['f3bet']}\n"
                    f"CB:{data['cbet']} FCB:{data['fcbet']}\n"
                    f"WTSD:{data['wtsd']} WSD:{data['wsd']}\n"
                    f"AF:{data.get('af', '0.0')}"
                )

                player_label = QLabel(hud_line)
                player_label.setParent(self) # Обязательно привязываем к окну
                # Делаем метку прозрачной для кликов мыши
                player_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                player_label.setFont(font)
                # Полупрозрачный фон для читаемости
                player_label.setStyleSheet(f"background-color: rgba(0, 0, 0, 100); color: {color_code}; padding: 4px; border-radius: 4px;")
                player_label.adjustSize()
                
                # Сохраняем виджет и его логические координаты (место)
                self.player_widgets[name] = player_label
                
                # Позиционируем
                self._place_widget(player_label, seat_num, hero_seat)
                player_label.show()

        # self.adjustSize() # Больше не нужно, так как окно фиксировано по размеру стола

    def reposition_all_widgets(self):
        """Пересчитывает и применяет позиции для всех существующих виджетов игроков."""
        if not self.current_table_players:
            return

        hero_seat = self.current_table_players.get(MY_PLAYER_NAME, 0)

        for name, widget in self.player_widgets.items():
            seat_num = self.current_table_players.get(name)
            if seat_num is not None:
                self._place_widget(widget, seat_num, hero_seat)

    def resizeEvent(self, event):
        """Перехватывает событие изменения размера окна для перераспределения виджетов."""
        super().resizeEvent(event)
        # Вызываем перераспределение каждый раз, когда размер окна меняется.
        self.reposition_all_widgets()

    def _place_widget(self, widget: QLabel, seat_num: int, hero_seat: int):
        """
        Размещает виджет игрока на основе его места и места Хиро.
        Мы предполагаем 6-макс стол.
        Позиция 0 - это Низ Центра (Хиро).
        Остальные позиции идут по часовой стрелке.
        """
        if hero_seat == 0:
            # Если хиро нет, просто используем номер места как позицию (сдвиг -1, т.к. места 1-6)
            visual_pos = (seat_num - 1) % 6
        else:
            # Считаем относительную позицию.
            # PokerStars места: 1..6.
            # Если Хиро на месте 3, то место 3 -> поз 0. Место 4 -> поз 1.
            # Формула: (Seat - HeroSeat) % 6
            visual_pos = (seat_num - hero_seat) % 6

        # Координаты в процентах от ширины/высоты окна (x, y)
        # Позиции для 6-макс (примерные, можно подстроить)
        # 0: Низ (Хиро)
        # 1: Лево Низ
        # 2: Лево Верх
        # 3: Верх
        # 4: Право Верх
        # 5: Право Низ
        
        pos_map = {
            0: (0.50, 0.88), # Hero
            1: (0.08, 0.65), # Left Bottom
            2: (0.08, 0.25), # Left Top
            3: (0.50, 0.12), # Top
            4: (0.92, 0.25), # Right Top
            5: (0.92, 0.65), # Right Bottom
        }
        
        rel_x, rel_y = pos_map.get(visual_pos, (0.5, 0.5))
        
        # Вычисляем абсолютные координаты
        # Центрируем виджет относительно точки
        x = int(self.width() * rel_x - widget.width() / 2)
        y = int(self.height() * rel_y - widget.height() / 2)
        
        widget.move(x, y)

    @Slot(object)
    def update_data(self, data: StatUpdateData):
        """Слот для приема данных от MonitorThread."""
        # Unpack 5 elements now
        try:
            _, new_seat_map, _, table_segment, precalculated_stats = data
        except ValueError as e:
            print(f"ERROR unpacking data: {e}. Data len: {len(data)}")
            return

        # ЛОГИКА СОХРАНЕНИЯ (PERSISTENCE):
        # Если место было занято, а в новой раздаче оно пустое (или пропущено),
        # мы оставляем старого игрока. Новые данные перезаписывают старые.
        
        # 1. Инвертируем текущую карту (Seat -> Name) и новую карту
        current_seats = {seat: name for name, seat in self.current_table_players.items()}
        new_seats = {seat: name for name, seat in new_seat_map.items()}
        
        # 2. Обновляем текущие места новыми (новые имеют приоритет)
        current_seats.update(new_seats)
        
        # 3. Возвращаем в формат Name -> Seat
        self.current_table_players = {name: seat for seat, name in current_seats.items()}
        
        self.active_table_segment = table_segment

        self._update_label_content(precalculated_stats)


    @Slot()
    def update_hud_position(self):
        """
        Регулярно обновляет позицию HUD.
        Оптимизирован для скорости. При подозрительных координатах (0, 0)
        запускает надежную проверку закрытия.
        """

        # 1. Если окно потеряно (None), пытаемся его найти.
        if self.target_window is None:
            if not self.find_target_window():
                self.hide()
                if not self.deletion_timer.isActive():
                    print(f"HUD: Запуск таймера удаления для {self.active_table_name}")
                    self.deletion_timer.start()
                return

        # 2. Если мы здесь, self.target_window не None. Сбрасываем таймер удаления.
        if self.deletion_timer.isActive():
            self.deletion_timer.stop()

        # 3. Пытаемся получить координаты (БЫСТРЫЙ ПУТЬ)
        try:
            # OPTIMIZATION: Trigger ONE explicit refresh of geometry, then use cached properties
            if hasattr(self.target_window, 'refresh'):
                 self.target_window.refresh()
            
            target_x = self.target_window.left
            target_y = self.target_window.top

            # *** ЗАЩИТА №3: Агрессивная проверка при подозрительных координатах ***
            if target_x < 5 and target_y < 5:
                # Если проверка подтвердила, что окна нет, вызываем исключение,
                # чтобы перейти в блок очистки (except).
                if not self.is_target_window_still_active(self.target_window):

                    # *** КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: ВЫХОДИМ СРАЗУ! ***
                    # Чтобы не использовать некорректные (0, 0) координаты для self.move()
                    self.target_window = None # Сбрасываем ссылку для запуска except-логики на следующем тике
                    self.hide() # Скрываем немедленно
                    if not self.deletion_timer.isActive():
                        print(f"HUD: Запуск таймера удаления для {self.active_table_name} (причина: закрытие)")
                        self.deletion_timer.start()
                    return # *** ВЫХОДИМ! ***

        except Exception:
            # 4. Сбой при получении координат ИЛИ ИСКУССТВЕННО ВЫЗВАННЫЙ СБОЙ.

            # Если exception сработал, и окно действительно неактивно (или сброшено выше)
            if self.target_window is None or not self.is_target_window_still_active(self.target_window):
                # Окно действительно закрыто. Инициируем удаление.
                self.target_window = None
                self.hide()
                if not self.deletion_timer.isActive():
                    print(f"HUD: Запуск таймера удаления для {self.active_table_name} (причина: исключение)")
                    self.deletion_timer.start()

            return

        # 5. Фильтр для предотвращения "прыжка" (если (0,0) - это реальная позиция)
        if target_x <= 50 and target_y <= 50:
            return

        # 6. Вычисляем и перемещаем HUD
        new_x = target_x + self.tracking_offset_x
        new_y = target_y + self.tracking_offset_y
        
        # 6.1 Также обновляем РАЗМЕР HUD, чтобы он совпадал с окном стола
        new_w = self.target_window.width
        new_h = self.target_window.height
        
        self.resize(new_w, new_h)
        # 7. ДИАГНОСТИЧЕСКИЙ ВЫВОД (Оставляем, пока не попросите убрать)
        # print(f"--- 📍 HUD Диагностика [{self.active_table_name}] ---")
        # print(f"Окно (X, Y): ({target_x}, {target_y})")
        # print(f"Смещение (OffsetX, OffsetY): ({self.tracking_offset_x}, {self.tracking_offset_y})")
        # print(f"Новая позиция HUD (X, Y): ({new_x}, {new_y})")
        # print("---------------------------------------")

        self.move(new_x, new_y)

        # 8. Отображаем HUD (если он был скрыт)
        if not self.isVisible():
            self.show()
            self.raise_()


# --- КЛАСС МЕНЕДЖЕРА HUD ---

class HUDManager(QObject):
    """Класс для управления множеством HUDWindow, по одному на активный стол."""
    def __init__(self):
        super().__init__()
        self.active_huds: Dict[str, HUDWindow] = {}

        # --- Новый код для личной статистики ---
        self.my_player_name = MY_PLAYER_NAME # <-- Ваш никнейм
        self.personal_stats_window: Optional[PersonalStatsWindow] = None

        try:
            self.personal_stats_window = PersonalStatsWindow(self.my_player_name)
            # Если закрывается окно статистики, закрываем всё приложение
            self.personal_stats_window.window_closed.connect(QCoreApplication.quit)
        except Exception as e:
            print(f"Ошибка создания окна личной статистики: {e}")

    @Slot(object)
    def handle_update_signal(self, data: StatUpdateData):
        file_path, player_names, table_title_part, table_segment, _ = data
        key = file_path

        if key not in self.active_huds:
            print(f"MANAGER: Создание нового HUD для стола: {table_title_part}")
            new_hud = HUDWindow(file_path, table_title_part)
            new_hud.closed_table_detected.connect(self.cleanup_closed_hud)
            self.active_huds[key] = new_hud

        hud = self.active_huds[key]
        hud.update_data(data)

    @Slot(str)
    def cleanup_closed_hud(self, file_path: str):
        """Удаляет HUD из списка менеджера, когда соответствующий стол закрыт."""
        if file_path in self.active_huds:
            self.active_huds.pop(file_path)
            print(f"MANAGER: Удален HUD для файла: {os.path.basename(file_path)}. Активных HUD: {len(self.active_huds)}")

    def close_all(self):
        """Закрывает все окна HUD и статистики."""
        print("MANAGER: Closing all HUDs and Stats Windows...")
        for hud in self.active_huds.values():
            hud.close()
        self.active_huds.clear()
        
        if self.personal_stats_window:
            self.personal_stats_window.close_all_children() # We will add this method
            self.personal_stats_window.close()


# --- ФУНКЦИИ УПРАВЛЕНИЯ ---

def run_full_load(directory: str, filter_segment: Optional[str] = None, filter_date: Optional[str] = None):
    """Выполняет полную загрузку всех файлов в директории."""
    print("--- 💾 АКТИВИРОВАН РЕЖИМ ПОЛНОЙ ЗАГРУЗКИ БАЗЫ ДАННЫХ ---")
    files_to_process = [
        os.path.join(directory, item)
        for item in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, item)) and item.endswith('.txt')
    ]

    count = 0
    for full_path in files_to_process:
        process_file_full_load(full_path, filter_segment=args.filter_segment, filter_date=args.filter_date)
        count += 1
        if count % 50 == 0:
            print(f"   Обработано {count} файлов...")

    print(f"--- ✅ Полная загрузка завершена. Обработано файлов: {count} ---")

def parse_arguments():
    """Настраивает и выполняет парсинг аргументов командной строки."""
    parser = argparse.ArgumentParser(description="Poker HUD and Hand History Monitor.")

    # --- Путь к директории ---
    parser.add_argument(
        '--dir',
        type=str,
        default=TARGET_HISTORY_DIR, # Значение по умолчанию
        help=f'Путь к директории с историей раздач (по умолчанию: {TARGET_HISTORY_DIR})'
    )
    # --- Флаг режима полной загрузки ---
    parser.add_argument(
        '--load-all',
        action='store_true',
        help='Активирует режим полной загрузки всех файлов в базу данных.'
    )

    # --- Флаг фильтрации сегмента стола (например, NL2_6MAX) ---
    parser.add_argument(
        '--filter-segment',
        type=str,
        default=None,
        help='Фильтровать историю раздач по сегменту стола (напр., NL2_6MAX).'
    )

    # --- Флаг фильтрации даты (например, 2024-01-01) ---
    parser.add_argument(
        '--filter-date',
        type=str,
        default=None,
        help='Фильтровать историю раздач по дате (включительно) в формате YYYY-MM-DD.'
    )

    # Добавьте аргумент для директории, если она передается как аргумент
    # parser.add_argument('directory', type=str, help='Путь к директории с историей раздач.')

    return parser.parse_args()

if __name__ == '__main__':

    args = parse_arguments()

    TARGET_HISTORY_DIR = args.dir

    if not os.path.isdir(TARGET_HISTORY_DIR):
        print(f"❌ Ошибка: '{TARGET_HISTORY_DIR}' не является директорией.")
        sys.exit(1)

    setup_database()

    if args.load_all:
        print("--- 💾 АКТИВИРОВАН РЕЖИМ ПОЛНОЙ ЗАГРУЗКИ ---")
        # Очистка базы перед загрузкой
        remove_database_files()
        setup_database() # Пересоздаем файлы (пустые)
        run_full_load(TARGET_HISTORY_DIR, filter_segment=args.filter_segment, filter_date=args.filter_date)

    # --- 2. СТАНДАРТНАЯ ИНИЦИАЛИЗАЦИЯ (Для мониторинга) ---
    for item in os.listdir(TARGET_HISTORY_DIR):
        full_path = os.path.join(TARGET_HISTORY_DIR, item)
        if os.path.isfile(full_path) and full_path.endswith('.txt') and not is_tournament_file(item):
            FILE_SIZES[full_path] = os.path.getsize(full_path)

    # --- 3. ЗАПУСК GUI И МОНИТОРИНГА ---
    app = QApplication(sys.argv)

    # --- 🌟 ОБРАБОТКА CTRL+C (SIGINT) ---
    # Привязываем сигнал SIGINT к функции выхода из Qt.
    signal.signal(signal.SIGINT, lambda *args: QCoreApplication.quit())

    # Создаем QTimer для периодической проверки сигналов ОС (для предотвращения блокировки).
    timer = QTimer()
    timer.start(100)
    timer.timeout.connect(lambda: None)
    # ------------------------------------

    hud_manager = HUDManager()

    monitor_signals = MonitorSignals()
    # watchdog_thread теперь создается как не-демонический по умолчанию
    watchdog_thread = WatchdogThread(TARGET_HISTORY_DIR, monitor_signals, session_start_time=SESSION_START_TIME)

    monitor_signals.stat_updated.connect(hud_manager.handle_update_signal)

    # --- 🧹 ЛОГИКА ЧИСТОГО ЗАВЕРШЕНИЯ ПОТОКА ---
    def cleanup_before_exit():
        """Вызывается перед завершением приложения для чистой остановки потока."""
        print("HUD Manager: Завершение потока мониторинга...")
        watchdog_thread.stop()

    # Подключаем функцию очистки к сигналу, который срабатывает при закрытии app.exec()
    app.aboutToQuit.connect(cleanup_before_exit)
    # ------------------------------------------

    # --- GLOBAL CLEANUP ON EXIT ---
    def global_cleanup():
        print("Exiting application, closing all windows...")
        hud_manager.close_all()
        QApplication.closeAllWindows()

    app.aboutToQuit.connect(global_cleanup)

    watchdog_thread.start()
    print(f"--- Запущен мониторинг директории '{TARGET_HISTORY_DIR}' ---")

    sys.exit(app.exec())
