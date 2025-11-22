# personal_stats_hud.py

from typing import Dict, Any, Optional
from PySide6.QtWidgets import QWidget, QLabel, QTableWidget, QTableWidgetItem, QGridLayout, QHeaderView
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent
from poker_stats_db import get_player_extended_stats # Будет добавлен позже

class PersonalStatsWindow(QWidget):
    """Отдельное окно для отображения расширенной статистики текущего игрока (Martyr40)."""

    def __init__(self, target_player_name: str):
        super().__init__()

        self.setWindowTitle(f"Моя Статистика - {target_player_name}")
        self.target_player = target_player_name

        self.dragging = False
        self.offset = QPoint()
        # Настройка окна: всегда сверху, без рамки, прозрачный фон
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint
        )

        # self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # self.setStyleSheet("background-color: rgba(0, 0, 0, 180); border-radius: 8px;")
        self.setStyleSheet("background-color: rgb(50, 50, 50); border-radius: 8px;")

        self.main_layout = QGridLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        # Заголовок
        self.title_label = QLabel(f"📊 {target_player_name} (Расширенная)")
        self.title_label.setStyleSheet("color: #00BFFF; font-size: 16px; font-weight: bold;")
        self.main_layout.addWidget(self.title_label, 0, 0, 1, 2)

        # --- Создание таблицы ---
        self.stats_table = QTableWidget(3, 6) # 2 строки (Рук/PFR %), 6 колонок (Общ, UTG, MP, CO, BU, SB)

        # ⚠️ ВАЖНО: Используем LaTeX для обозначения позиций UTG, MP, CO, BU, SB
        self.stats_table.setHorizontalHeaderLabels([
            "TOTAL", "UTG", "MP", "CO", "BU", "SB"
        ])

        self.stats_table.setVerticalHeaderLabels(["Рук", "PFR %", "RFI %"])

        # Настройка внешнего вида таблицы
        header_style = "QHeaderView::section { background-color: #333; color: white; }"
        self.stats_table.horizontalHeader().setStyleSheet(header_style)
        self.stats_table.verticalHeader().setStyleSheet(header_style)
        table_style = "QTableWidget { gridline-color: #555; background-color: transparent; color: white; border: none; }"
        self.stats_table.setStyleSheet(table_style)

        self.stats_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stats_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 1. Горизонтальные заголовки (Столбцы: Общий, UTG, MP...)
        # Stretch — чтобы равномерно распределить оставшееся пространство между колонками
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # 2. Вертикальные заголовки (Строки: Рук, PFR %)
        # ResizeToContents — чтобы гарантировать, что названия строк ("Рук", "PFR %") поместятся
        self.stats_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        # 3. Принудительно подгоняем заголовки после установки данных/стилей
        self.stats_table.resizeColumnsToContents() # Подгоняет ширину столбцов под текущие данные
        self.stats_table.resizeRowsToContents()   # Подгоняет высоту строк под содержимое

        self.main_layout.addWidget(self.stats_table, 1, 0, 1, 2)

        self.show()
        # 🌟 Важно: Снова подгоняем размер окна под новый контент
        self.adjustSize()

    def calculate_table_width(self) -> int:
        """Рассчитывает общую необходимую ширину для всех столбцов и заголовков."""

        # 1. Ширина вертикального заголовка (строки 'Рук', 'PFR %')
        v_header_width = self.stats_table.verticalHeader().sizeHint().width()

        # 2. Общая ширина горизонтальных столбцов (Общий PFR, UTG, MP, ...)
        columns_width = 0
        for i in range(self.stats_table.columnCount()):
            # Берем ширину, которая была рассчитана с помощью resizeColumnsToContents
            columns_width += self.stats_table.columnWidth(i)

        # 3. Дополнительные элементы:
        # - Ширина рамки таблицы (table border)
        # - Ширина скролл-бара (даже если он отключен, иногда учитывается)
        # - Небольшой запас (padding)
        padding = 20

        total_width = v_header_width + columns_width + padding

        return total_width

    def calculate_table_height(self) -> int:
        """Рассчитывает общую необходимую высоту для всех строк и заголовков."""

        # 1. Высота горизонтального заголовка (столбцы 'Общий PFR', 'UTG', ...)
        h_header_height = self.stats_table.horizontalHeader().sizeHint().height()

        # 2. Общая высота строк
        rows_height = 0
        for i in range(self.stats_table.rowCount()):
            # Берем высоту, рассчитанную resizeRowsToContents
            rows_height += self.stats_table.rowHeight(i)

        # 3. Добавим небольшой запас 🌟 (Для рамки и отступов)
        padding = 30

        total_height = h_header_height + rows_height + padding

        # 4. Учитываем высоту остальных элементов в макете (заголовок окна)
        # У нас есть метка (self.title_label) над таблицей
        title_height = self.title_label.sizeHint().height()

        # Общая высота окна
        total_window_height = total_height + title_height + 5 # Дополнительный запас между заголовком и таблицей

        return total_window_height

    def update_stats(self, hands_data: Dict[str, int], pfr_data: Dict[str, str], rfi_data: Dict[str, str]):
        """Обновляет данные в таблице."""
        positions = ["total", "utg", "mp", "co", "bu", "sb"]

        # 1. Заполнение строки "Рук" (Hands) - Строка 0
        for col, pos in enumerate(positions):
            hands = hands_data.get(pos, 0)
            item = QTableWidgetItem(str(hands))
            # 🌟 КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ 1: Установка выравнивания
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stats_table.setItem(0, col, item) # Строка 0

        # 2. Заполнение строки "PFR %" - Строка 1
        for col, pos in enumerate(positions):
            pfr = pfr_data.get(pos, "0.0")
            item = QTableWidgetItem(str(pfr))
            # 🌟 КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ 2: Установка выравнивания
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stats_table.setItem(1, col, item) # Строка 1

        positions = ["utg", "mp", "co", "bu"]
        for col, pos in enumerate(positions):
            rfi = rfi_data.get(pos, "0.0")
            item = QTableWidgetItem(str(rfi))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stats_table.setItem(2, col+1, item) # Строка 2

        # 🌟 КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ 3: Принудительная перерисовка и подгонка размеров
        self.stats_table.viewport().update()

        self.stats_table.resizeColumnsToContents()
        self.stats_table.resizeRowsToContents()

        new_width = self.calculate_table_width()
        new_height = self.calculate_table_height()

        self.setFixedSize(new_width, new_height)
        self.adjustSize()

    def mousePressEvent(self, event: QMouseEvent):
        """Начинает операцию перемещения при нажатии левой кнопки мыши."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            # Запоминаем смещение (offset) между положением окна и точкой клика
            self.offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        """Перемещает окно вслед за курсором мыши."""
        if self.dragging:
            # Новая позиция окна: Глобальная позиция курсора - сохраненное смещение
            new_pos = event.globalPosition().toPoint() - self.offset
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Завершает операцию перемещения."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            event.accept()
