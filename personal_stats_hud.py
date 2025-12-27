from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QLabel, QTableWidget, QTableWidgetItem, QGridLayout, 
    QHeaderView, QDateEdit, QPushButton, QHBoxLayout, QCheckBox, QVBoxLayout
)
from PySide6.QtCore import Qt, QPoint, QDate, QTime, QTimer
from PySide6.QtGui import QMouseEvent
from datetime import datetime, time
from poker_stats_db import get_player_extended_stats

class PersonalStatsWindow(QWidget):
    """
    Отдельное окно для отображения расширенной статистики текущего игрока (Hero).
    Позволяет фильтровать статистику по дате.
    """

    def __init__(self, target_player_name: str):
        super().__init__()

        self.setWindowTitle(f"Моя Статистика - {target_player_name}")
        self.target_player = target_player_name

        self.dragging = False
        self.offset = QPoint()
        # Настройка окна: всегда сверху, без рамки, темный фон
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint
        )
        self.setStyleSheet("background-color: rgb(50, 50, 50); border-radius: 8px; color: white;")

        # Основной лейаут
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # 1. ЗАГОЛОВОК
        self.title_label = QLabel(f"📊 {target_player_name} (Extended)")
        self.title_label.setStyleSheet("color: #00BFFF; font-size: 16px; font-weight: bold;")
        self.main_layout.addWidget(self.title_label)

        # 2. ПАНЕЛЬ ФИЛЬТРОВ (ДАТА)
        filter_layout = QHBoxLayout()
        
        # Дата С (From)
        filter_layout.addWidget(QLabel("С:"))
        self.date_from = QDateEdit()
        self.date_from.setDisplayFormat("dd.MM.yyyy")
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate()) # По умолчанию - сегодня
        self.date_from.setStyleSheet("background-color: #333; color: white; border: 1px solid #555;")
        filter_layout.addWidget(self.date_from)

        # Дата ПО (To)
        self.check_to = QCheckBox("По:")
        self.check_to.setStyleSheet("color: white;")
        self.check_to.stateChanged.connect(self._toggle_date_to)
        filter_layout.addWidget(self.check_to)

        self.date_to = QDateEdit()
        self.date_to.setDisplayFormat("dd.MM.yyyy")
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setEnabled(False) # По умолчанию отключено
        self.date_to.setStyleSheet("background-color: #333; color: white; border: 1px solid #555;")
        filter_layout.addWidget(self.date_to)

        # Кнопка ОБНОВИТЬ
        self.btn_refresh = QPushButton("⟳")
        self.btn_refresh.setFixedWidth(30)
        self.btn_refresh.setStyleSheet("background-color: #444; color: white; border: 1px solid #666;")
        self.btn_refresh.clicked.connect(self.refresh_stats)
        filter_layout.addWidget(self.btn_refresh)
        
        filter_layout.addStretch()
        self.main_layout.addLayout(filter_layout)


        # 3. ТАБЛИЦА СТАТИСТИКИ
        # 4 строки: Рук, VPIP, PFR, RFI
        # 6 колонок: Total, UTG, MP, CO, BU, SB
        self.stats_table = QTableWidget(4, 6) 
        
        self.stats_table.setHorizontalHeaderLabels([
            "TOTAL", "UTG", "MP", "CO", "BU", "SB"
        ])
        self.stats_table.setVerticalHeaderLabels(["Hands", "VPIP %", "PFR %", "RFI %"])

        # Стилизация таблицы
        header_style = "QHeaderView::section { background-color: #333; color: white; font-weight: bold; }"
        self.stats_table.horizontalHeader().setStyleSheet(header_style)
        self.stats_table.verticalHeader().setStyleSheet(header_style)
        
        table_style = """
            QTableWidget { 
                gridline-color: #555; 
                background-color: transparent; 
                color: white; 
                border: none; 
                font-size: 13px;
            }
        """
        self.stats_table.setStyleSheet(table_style)
        self.stats_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stats_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Растягиваем колонки
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.stats_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        self.main_layout.addWidget(self.stats_table)

        # Начальная загрузка
        self.show()
        # Даем интерфейсу время на отрисовку перед обновлением данных
        QTimer.singleShot(100, self.refresh_stats)

    def _toggle_date_to(self, state):
        self.date_to.setEnabled(self.check_to.isChecked())

    def refresh_stats(self):
        """Загружает данные из БД с учетом выбранных дат."""
        try:
            # 1. Определяем диапазон времени
            # Начало дня "С"
            qdate_from = self.date_from.date()
            dt_from = datetime.combine(qdate_from.toPython(), time.min)

            # Конец дня "По" (если включено)
            dt_to = None
            if self.check_to.isChecked():
                qdate_to = self.date_to.date()
                dt_to = datetime.combine(qdate_to.toPython(), time.max)
            
            # 2. Запрос в БД
            # Используем пустой table_segment, так как фильтруем по all my_hand_log
            stats = get_player_extended_stats(self.target_player, "", min_time=dt_from, max_time=dt_to)
            
            if stats:
                self.update_stats_table(stats)
            else:
                 # Если данных нет (например, пустой результат), можно очистить таблицу или оставить нули
                 pass 

        except Exception as e:
            print(f"Ошибка обновления личной статистики: {e}")

    def update_stats_table(self, stats: Dict[str, Dict[str, Any]]):
        """Заполняет таблицу данными."""
        positions = ["total", "utg", "mp", "co", "bu", "sb"]
        
        hands_data = stats.get('hands', {})
        vpip_data = stats.get('vpip', {})
        pfr_data = stats.get('pfr', {})
        rfi_data = stats.get('rfi', {})

        # Вспомогательная функция для установки ячейки
        def set_cell(row, col, value):
            item = QTableWidgetItem(str(value))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stats_table.setItem(row, col, item)

        for col_idx, pos in enumerate(positions):
            # Row 0: Hands
            set_cell(0, col_idx, hands_data.get(pos, 0))
            # Row 1: VPIP
            set_cell(1, col_idx, vpip_data.get(pos, "0.0"))
            # Row 2: PFR
            set_cell(2, col_idx, pfr_data.get(pos, "0.0"))

        # Row 3: RFI (нет Total для RFI обычно, но если есть - выведем)
        # У нас positions = ["total", ...], а RFI обычно с UTG.
        # RFI data: utg, mp, co, bu, sb
        rfi_positions = ["utg", "mp", "co", "bu", "sb"]
        set_cell(3, 0, "-") # Total RFI often N/A or avg
        
        for i, pos in enumerate(rfi_positions):
             # RFI start from col 1 (UTG)
             set_cell(3, i+1, rfi_data.get(pos, "0.0"))

        self.stats_table.viewport().update()
        self.adjust_window_size()

    def adjust_window_size(self):
        """Подгоняет размер окна под контент."""
        self.stats_table.resizeColumnsToContents()
        self.stats_table.resizeRowsToContents()
        
        # Вычисляем высоту
        h_header_h = self.stats_table.horizontalHeader().height()
        rows_h = sum(self.stats_table.rowHeight(i) for i in range(self.stats_table.rowCount()))
        total_table_h = h_header_h + rows_h + 10
        
        # Высота контролов и заголовка
        # Можно использовать sizeHint, но мы дали Layout работать
        # Просто используем adjustSize() Qt, он сам посчитает
        self.adjustSize() 

    # --- DRAG & DROP UTILS ---
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.dragging:
            self.move(event.globalPosition().toPoint() - self.offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
             self.dragging = False
             event.accept()
