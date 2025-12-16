import sys
import os
import signal
import argparse
from typing import Dict, Any, Optional, List
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Slot, QObject, Signal, QCoreApplication
from PySide6.QtGui import QFont
import pywinctl as pwc

# Импорт модулей проекта (предполагается, что они доступны)
from poker_globals import MY_PLAYER_NAME, TARGET_HISTORY_DIR, FILE_SIZES, StatUpdateData
from poker_monitor import WatchdogThread, MonitorSignals, process_file_full_load, is_tournament_file
from poker_stats_db import setup_database, get_stats_for_players, get_player_extended_stats
from personal_stats_hud import PersonalStatsWindow

# --- КЛАСС HUD ОКНА ---

class HUDWindow(QWidget):
    """Отдельное окно HUD, привязанное к одному столу."""
    closed_table_detected = Signal(str)

    def __init__(self, file_path: str, target_title_part: str):
        super().__init__()

        self.setWindowTitle(f"HUD Tracker - {target_title_part}")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint #|
            # Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 150); border-radius: 5px;")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(2)

        self.status_label = QLabel(f"Ожидание окна: {target_title_part}...")
        font = QFont("Arial", 14, QFont.Weight.Bold)
        self.status_label.setFont(font)
        self.status_label.setStyleSheet("color: white;")
        self.main_layout.addWidget(self.status_label)

        # --- Хранилище ---
        self.target_window = None
        self.tracking_offset_x = 20
        self.tracking_offset_y = 60

        # Идентификаторы стола
        self.file_path = file_path
        self.active_table_name: str = target_title_part
        self.active_table_segment: Optional[str] = None
        self.current_table_players: List[str] = []

        self.hide()

        # Таймер для регулярного позиционирования
        self.pos_timer = QTimer(self)
        self.pos_timer.timeout.connect(self.update_hud_position)
        self.pos_timer.start(20)

        # Таймер для задержки удаления (5 секунд)
        self.deletion_timer = QTimer(self)
        self.deletion_timer.setInterval(5000)
        self.deletion_timer.setSingleShot(True)
        self.deletion_timer.timeout.connect(self.finalize_deletion)

    # --- Методы управления ---

    def is_target_window_still_active(self, window_obj) -> bool:
        """Проверяет, существует ли объект окна pywinctl в списке активных окон по его ID."""
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
        target_part = self.active_table_name

        try:
            windows = pwc.getAllWindows()
        except Exception:
            return False

        for win in windows:
            if target_part.lower() in win.title.lower():
                try:
                    app_name = win.ownerName
                except Exception:
                    app_name = "N/A"
                if 'terminal' in app_name.lower() or 'python' in app_name.lower() or 'pycharm' in app_name.lower() or 'code' in app_name.lower():
                    continue

                # *** ЗАЩИТА №1: Игнорировать окна, найденные в (0,0) ***
                try:
                    # Если окно в самом верху или слева (например, свернуто/скрыто), пропускаем.
                    if win.left < 5 and win.top < 5:
                        continue
                except Exception:
                    continue # Окно нестабильно, пропускаем

                self.target_window = win
                return True

        self.target_window = None
        return False

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

    def _clear_hud_widgets(self):
        while self.main_layout.count() > 0:
            item = self.main_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _update_label_content(self):
        player_stats = {}
        if self.active_table_segment:
             player_stats = get_stats_for_players(self.current_table_players, self.active_table_segment)

        self._clear_hud_widgets()
        font = QFont("Arial", 14, QFont.Weight.Bold)

        if not self.current_table_players:
            table_info = f"Стол: {self.active_table_name}\nСегмент: {self.active_table_segment}" if self.active_table_name else "Неизвестно"
            self.status_label.setText(f"{table_info}\nОжидание игроков...")
            self.main_layout.addWidget(self.status_label)
        else:
            for name in self.current_table_players:
                data = player_stats.get(name, {
                    'vpip': '0.0', 'pfr': '0.0',
                    '3bet': '0.0', 'f3bet': '0.0',
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
                    f"{name}: {data['vpip']}/{data['pfr']} "
                    f"| 3B: {data['3bet']}/F3B: {data['f3bet']} | AF: {data.get('af', '0.0')} ({data['hands']})"
                )

                player_label = QLabel(hud_line)
                player_label.setFont(font)
                player_label.setStyleSheet(f"color: {color_code};")
                self.main_layout.addWidget(player_label)

        self.adjustSize()

    @Slot(object)
    def update_data(self, data: StatUpdateData):
        """Слот для приема данных от MonitorThread."""
        _, player_names, _, table_segment = data

        self.current_table_players = player_names
        self.active_table_segment = table_segment

        self._update_label_content()

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
        except Exception as e:
            print(f"Ошибка создания окна личной статистики: {e}")

        if self.personal_stats_window:
            self.personal_stats_timer = QTimer()
            # Обновление раз в 1 секунду
            self.personal_stats_timer.setInterval(1000)
            # Привязываем таймер к новому слоту
            self.personal_stats_timer.timeout.connect(self.update_personal_stats)
            self.personal_stats_timer.start()

    @Slot(object)
    def handle_update_signal(self, data: StatUpdateData):
        file_path, player_names, table_title_part, table_segment = data
        key = file_path

        if key not in self.active_huds:
            print(f"MANAGER: Создание нового HUD для стола: {table_title_part}")
            new_hud = HUDWindow(file_path, table_title_part)
            new_hud.closed_table_detected.connect(self.cleanup_closed_hud)
            self.active_huds[key] = new_hud

        hud = self.active_huds[key]
        hud.update_data(data)

    @Slot()
    def update_personal_stats(self):
        """Регулярно загружает и обновляет данные в окне личной статистики."""

        # Проверяем, существует ли окно
        if not self.personal_stats_window:
            return

        # 1. Загрузка данных ИЗ БАЗЫ ДАННЫХ
        extended_stats = get_player_extended_stats(self.my_player_name, 'NL2_6MAX')
        if extended_stats:
            # 2. Обновление интерфейса
            self.personal_stats_window.update_stats(
                extended_stats["hands"],
                extended_stats["pfr"],
                extended_stats["rfi"]
            )


    @Slot(str)
    def cleanup_closed_hud(self, file_path: str):
        """Удаляет HUD из списка менеджера, когда соответствующий стол закрыт."""
        if file_path in self.active_huds:
            self.active_huds.pop(file_path)
            print(f"MANAGER: Удален HUD для файла: {os.path.basename(file_path)}. Активных HUD: {len(self.active_huds)}")


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
    watchdog_thread = WatchdogThread(TARGET_HISTORY_DIR, monitor_signals)

    monitor_signals.stat_updated.connect(hud_manager.handle_update_signal)

    # --- 🧹 ЛОГИКА ЧИСТОГО ЗАВЕРШЕНИЯ ПОТОКА ---
    def cleanup_before_exit():
        """Вызывается перед завершением приложения для чистой остановки потока."""
        print("HUD Manager: Завершение потока мониторинга...")
        watchdog_thread.stop()

    # Подключаем функцию очистки к сигналу, который срабатывает при закрытии app.exec()
    app.aboutToQuit.connect(cleanup_before_exit)
    # ------------------------------------------

    watchdog_thread.start()
    print(f"--- Запущен мониторинг директории '{TARGET_HISTORY_DIR}' ---")

    sys.exit(app.exec())
