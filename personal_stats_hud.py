from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QDateEdit, QPushButton, QHBoxLayout, QCheckBox, QFrame
)
from PySide6.QtCore import Qt, QTimer, QDate, QPoint
from PySide6.QtGui import QMouseEvent
from datetime import datetime, time
from poker_stats_db import get_player_extended_stats, get_chart_hands_data
from hand_matrix_widget import HandChartDialog

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

        # 1. ЗАГОЛОВОК И КНОПКИ
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        self.title_label = QLabel(f"📊 {target_player_name}")
        self.title_label.setStyleSheet("color: #00BFFF; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        # Кнопка Mini Mode
        self.is_mini_mode = False
        self.btn_mini = QPushButton("_")
        self.btn_mini.setFixedSize(24, 24)
        self.btn_mini.setStyleSheet("background-color: #444; color: white; border: none; font-weight: bold;")
        self.btn_mini.clicked.connect(self.toggle_mode)
        header_layout.addWidget(self.btn_mini)
        
        self.main_layout.addLayout(header_layout)
        
        # Лейбл для Mini Mode
        self.mini_stats_label = QLabel()
        self.mini_stats_label.setStyleSheet("color: #00FF00; font-size: 14px; font-weight: bold; padding: 5px;")
        self.mini_stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mini_stats_label.hide()
        self.main_layout.addWidget(self.mini_stats_label)

        # Контейнер для фильтров (чтобы скрывать)
        self.filter_frame = QFrame()
        self.main_layout.addWidget(self.filter_frame)
        filter_box_layout = QVBoxLayout(self.filter_frame)
        filter_box_layout.setContentsMargins(0, 0, 0, 0)

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
        # self.main_layout.addLayout(filter_layout) # Moved to filter_frame
        filter_box_layout.addLayout(filter_layout)


        # 3. ТАБЛИЦА СТАТИСТИКИ
        # 4 строки: Рук, VPIP, PFR, RFI
        # 6 колонок: Total, UTG, MP, CO, BU, SB
        self.stats_table = QTableWidget(4, 6) 
        
        self.stats_table.setHorizontalHeaderLabels([
            "TOTAL", "UTG", "MP", "CO", "BU", "SB"
        ])
        self.stats_table.setVerticalHeaderLabels(["Hands", "VPIP %", "PFR %", "RFI %"])
        self.stats_table.cellClicked.connect(self.on_table_cell_clicked)

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

        # --- Blind Defense & Steal Stats Section ---
        # A separate container for new stats
        # --- Blind Defense & Steal Stats Section ---
        # A separate container for new stats
        self.defense_group = QFrame()
        defense_main_layout = QVBoxLayout(self.defense_group) # Main Vertical Layout
        defense_main_layout.setContentsMargins(0, 5, 0, 0)
        defense_main_layout.setSpacing(2) # Tight spacing
        
        # Helper to create styled labels
        def create_stat_label(text):
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #ccc; font-size: 12px;")
            return lbl

        self.lbl_steal_succ = create_stat_label("Steal Success: -")
        self.lbl_bb_fold = create_stat_label("BB Fold to Steal: -")
        self.lbl_bb_call = create_stat_label("BB Call vs Steal: -")
        self.lbl_bb_3bet = create_stat_label("BB 3Bet vs Steal: -")
        self.lbl_bb_check_limp = create_stat_label("BB Check vs Limp: -")
        self.lbl_bb_iso_limp = create_stat_label("BB Iso vs Limp: -")
        
        # New Aggression Labels
        self.lbl_3bet = create_stat_label("3-Bet: -")
        self.lbl_cbet = create_stat_label("C-Bet: -")
        self.lbl_fold_to_cbet = create_stat_label("Fold to C-Bet: -")
        
        self.lbl_wtsd = create_stat_label("WTSD: -")
        self.lbl_wsd = create_stat_label("WSD: -")

        # Row 1: Steal Success
        row1 = QHBoxLayout()
        row1.addWidget(self.lbl_steal_succ)
        row1.addStretch()
        defense_main_layout.addLayout(row1)

        # Row 2: BB vs Steal (Fold, Call, 3Bet)
        row2 = QHBoxLayout()
        row2.addWidget(self.lbl_bb_fold)
        row2.addWidget(self.lbl_bb_call)
        row2.addWidget(self.lbl_bb_3bet)
        row2.addStretch()
        defense_main_layout.addLayout(row2)
        
        # Row 3: BB vs Limp
        row3 = QHBoxLayout()
        row3.addWidget(self.lbl_bb_check_limp)
        row3.addWidget(self.lbl_bb_iso_limp)
        row3.addStretch()
        defense_main_layout.addLayout(row3)
        
        # Row 3.5: Aggression (3-Bet, C-Bet, FcBet)
        row_agg = QHBoxLayout()
        row_agg.addWidget(self.lbl_3bet)
        row_agg.addWidget(self.lbl_cbet)
        row_agg.addWidget(self.lbl_fold_to_cbet)
        row_agg.addStretch()
        defense_main_layout.addLayout(row_agg)
        
        # Row 4: WTSD / WSD
        row4 = QHBoxLayout()
        row4.addWidget(self.lbl_wtsd)
        row4.addWidget(self.lbl_wsd)
        row4.addStretch()
        defense_main_layout.addLayout(row4)
        
        self.main_layout.addWidget(self.defense_group)

        # Начальная загрузка
        self.move(20, 50) # Closer to top-left
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

    def toggle_mode(self):
        """Переключение между полным и мини-режимом."""
        self.is_mini_mode = not self.is_mini_mode
        
        if self.is_mini_mode:
            # Hide Full Mode Widgets
            self.filter_frame.hide()
            self.stats_table.hide()
            self.defense_group.hide()
            # Show Mini Label
            self.mini_stats_label.show()
            self.btn_mini.setText("□") # Icon for restore
            
            # Update content
            if hasattr(self, 'current_stats') and self.current_stats:
                hands = self.current_stats.get('hands', {}).get('total', 0)
                vpip = self.current_stats.get('vpip', {}).get('total', '-')
                pfr = self.current_stats.get('pfr', {}).get('total', '-')
                self.mini_stats_label.setText(f"Hands: {hands} | VPIP: {vpip}% | PFR: {pfr}%")
            
            self.resize(250, 60) # Compact size
        else:
            # Restore Full Mode
            self.filter_frame.show()
            self.stats_table.show()
            self.defense_group.show()
            self.mini_stats_label.hide()
            self.btn_mini.setText("_")
            self.adjust_window_size()

    def update_stats_table(self, stats: Dict[str, Dict[str, Any]]):
        """Заполняет таблицу данными."""
        self.current_stats = stats # Save for mini mode
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
        # RFI data: utg, mp, co, bu, sb
        rfi_positions = ["utg", "mp", "co", "bu", "sb"]
        set_cell(3, 0, "-") # Total RFI often N/A or avg
        
        for i, pos in enumerate(rfi_positions):
             # RFI start from col 1 (UTG)
             set_cell(3, i+1, rfi_data.get(pos, "0.0"))

        # --- Update Blind Defense Stats ---
        steal_succ = stats.get('steal_success', '-')
        bb_def = stats.get('bb_defense', {})
              # BB Defense Stats
        bb_def = stats.get('bb_defense', {})
        self.lbl_bb_fold.setText(f"BB Fold to Steal: {bb_def.get('fold_to_steal', '-')}%")
        self.lbl_bb_call.setText(f"BB Call vs Steal: {bb_def.get('call_steal', '-')}%")
        self.lbl_bb_3bet.setText(f"BB 3Bet vs Steal: {bb_def.get('3bet_steal', '-')}%")
        
        # Steal Success
        steal_succ = stats.get('steal_success', '-')
        self.lbl_steal_succ.setText(f"Steal Success: {steal_succ}%")
        
        # BB vs Limp Stats
        bb_limp = stats.get('bb_vs_limp', {})
        self.lbl_bb_check_limp.setText(f"BB Check vs Limp: {bb_limp.get('check', '-')}%")
        self.lbl_bb_iso_limp.setText(f"BB Iso vs Limp: {bb_limp.get('iso', '-')}%")
        
        # Aggression Stats
        t3bet = stats.get('3bet', {}).get('total', '-')
        cbet = stats.get('cbet', {}).get('total', '-')
        fcbet = stats.get('fold_to_cbet', {}).get('total', '-')
        
        self.lbl_3bet.setText(f"3-Bet: {t3bet}%")
        self.lbl_cbet.setText(f"C-Bet: {cbet}%")
        self.lbl_fold_to_cbet.setText(f"Fold to C-Bet: {fcbet}%")
        
        # WTSD/WSD
        wtsd_data = stats.get('wtsd', {})
        self.lbl_wtsd.setText(f"WTSD: {wtsd_data.get('wtsd', '-')}%")
        self.lbl_wsd.setText(f"WSD: {wtsd_data.get('wsd', '-')}%")

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

    def on_table_cell_clicked(self, row, col):
        """Обработка клика по ячейке статистики для показа чарта."""
        stat_types = ['hands', 'vpip', 'pfr', 'rfi']
        positions = ['total', 'utg', 'mp', 'co', 'bu', 'sb']
        
        if row >= len(stat_types) or col >= len(positions):
            return
            
        stat_type = stat_types[row]
        position = positions[col]
        
        # Determine Date Range
        qdate_from = self.date_from.date()
        dt_from = datetime.combine(qdate_from.toPython(), time.min)
        dt_to = None
        if self.check_to.isChecked():
             qdate_to = self.date_to.date()
             dt_to = datetime.combine(qdate_to.toPython(), time.max)
        
        print(f"Fetching Chart: {stat_type} {position}")
        data = get_chart_hands_data(
            self.target_player, 
            stat_type, 
            position, 
            min_time=dt_from, 
            max_time=dt_to
        )
        
        if not data:
            print("No data for chart.")
             # return
            
        dlg = HandChartDialog(f"Hands: {stat_type.upper()} @ {position.upper()}", data)
        dlg.exec()
