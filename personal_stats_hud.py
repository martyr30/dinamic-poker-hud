from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QDateEdit, QPushButton, QHBoxLayout, QCheckBox, QFrame, QComboBox
)
from PySide6.QtCore import Qt, QTimer, QDate, QPoint, Signal, QThread, Slot
from PySide6.QtGui import QMouseEvent, QColor
from datetime import datetime, time
from poker_stats_db import get_player_extended_stats, get_chart_hands_data, get_player_hand_log_df
from hand_matrix_widget import HandChartDialog
from graph_widget import PokerGraphWidget


class StatsLoaderThread(QThread):
    stats_loaded = Signal(object) # Returns dict or None

    def __init__(self, player_name, dt_from, dt_to):
        super().__init__()
        self.player_name = player_name
        self.dt_from = dt_from
        self.dt_to = dt_to

    def run(self):
        try:
             # Используем пустой table_segment, так как фильтруем по all my_hand_log
            stats = get_player_extended_stats(self.player_name, "", min_time=self.dt_from, max_time=self.dt_to)
            self.stats_loaded.emit(stats)
        except Exception as e:
            print(f"Thread Error: {e}")
            self.stats_loaded.emit(None)

class PersonalStatsWindow(QWidget):
    """
    Отдельное окно для отображения расширенной статистики текущего игрока (Hero).
    Позволяет фильтровать статистику по дате.
    """

    # Сигнал закрытия окна
    window_closed = Signal()

    def __init__(self, target_player_name: str):
        super().__init__()


        self.setWindowTitle(f"Моя Статистика - {target_player_name}")
        self.target_player = target_player_name
        
        # Thread reference
        self.loader_thread = None

        self.dragging = False
        self.offset = QPoint()
        # Настройка окна: всегда сверху, без рамки, темный фон
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
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

        # Кнопка Refresh для Mini Mode (скрыта по умолчанию)
        self.btn_mini_refresh = QPushButton("⟳")
        self.btn_mini_refresh.setFixedSize(24, 24)
        self.btn_mini_refresh.setStyleSheet("background-color: #444; color: white; border: none; font-weight: bold;")
        self.btn_mini_refresh.clicked.connect(self.refresh_stats)
        self.btn_mini_refresh.hide()
        header_layout.addWidget(self.btn_mini_refresh)

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
        
        # Кнопка GRAPH
        self.btn_graph = QPushButton("📈")
        self.btn_graph.setToolTip("Show Graph")
        self.btn_graph.setFixedWidth(30)
        self.btn_graph.setStyleSheet("background-color: #444; color: white; border: 1px solid #666;")
        self.btn_graph.clicked.connect(self.open_graph)
        filter_layout.addWidget(self.btn_graph)
        
        # --- VIEW MODE SELECTOR ---
        # from PySide6.QtWidgets import QComboBox # Moved to top
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["Total ($)", "Total (BB)", "BB/100"])
        self.view_mode_combo.setStyleSheet("""
            QComboBox { background-color: #333; color: white; border: 1px solid #555; padding: 2px; }
            QComboBox::drop-down { border: none; }
        """)
        self.view_mode_combo.currentIndexChanged.connect(self.on_view_mode_changed)
        filter_layout.addWidget(self.view_mode_combo)
        
        filter_layout.addStretch()
        # self.main_layout.addLayout(filter_layout) # Moved to filter_frame
        filter_box_layout.addLayout(filter_layout)


        # 3. ТАБЛИЦА СТАТИСТИКИ
        # 4 строки: Рук, VPIP, PFR, RFI
        # 6 колонок: Total, UTG, MP, CO, BU, SB
        self.stats_table = QTableWidget(8, 7) 
        
        self.stats_table.setHorizontalHeaderLabels([
            "TOTAL", "UTG", "MP", "CO", "BU", "SB", "BB"
        ])
        # Default Headers (will be updated)
        self.stats_table.setVerticalHeaderLabels(["Hands", "VPIP %", "PFR %", "RFI %", "Net Won", "WSD", "WNSD", "EV"])
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
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
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

        self.lbl_steal_succ = create_stat_label("<b>Steal Success:</b> -")
        self.lbl_bb_fold = create_stat_label("<b>BB Fold to Steal:</b> -")
        self.lbl_bb_call = create_stat_label("<b>BB Call vs Steal:</b> -")
        self.lbl_bb_3bet = create_stat_label("<b>BB 3Bet vs Steal:</b> -")
        self.lbl_bb_check_limp = create_stat_label("<b>BB Check vs Limp:</b> -")
        self.lbl_bb_iso_limp = create_stat_label("<b>BB Iso vs Limp:</b> -")
        
        # New Aggression Labels
        self.lbl_3bet = create_stat_label("<b>3-Bet:</b> -")
        self.lbl_cbet = create_stat_label("<b>C-Bet:</b> -")
        self.lbl_fold_to_cbet = create_stat_label("<b>Fold to C-Bet:</b> -")
        self.lbl_fold_to_3bet = create_stat_label("<b>Fold to 3-Bet:</b> -")
        
        self.lbl_wtsd = create_stat_label("<b>WTSD:</b> -")
        self.lbl_wsd = create_stat_label("<b>WSD:</b> -")

        # Row 1 (Preflop Agg): 3-Bet, Fold to 3-Bet
        row_pre_agg = QHBoxLayout()
        row_pre_agg.addWidget(self.lbl_3bet)
        row_pre_agg.addWidget(self.lbl_fold_to_3bet)
        row_pre_agg.addStretch()
        defense_main_layout.addLayout(row_pre_agg)

        # Row 2 (Steal Success)
        row_steal_succ = QHBoxLayout()
        row_steal_succ.addWidget(self.lbl_steal_succ)
        row_steal_succ.addStretch()
        defense_main_layout.addLayout(row_steal_succ)

        # Row 3 (BB vs Steal)
        row_bb_steal = QHBoxLayout()
        row_bb_steal.addWidget(self.lbl_bb_fold)
        row_bb_steal.addWidget(self.lbl_bb_call)
        row_bb_steal.addWidget(self.lbl_bb_3bet)
        row_bb_steal.addStretch()
        defense_main_layout.addLayout(row_bb_steal)
        
        # Row 4 (BB vs Limp)
        row_bb_limp = QHBoxLayout()
        row_bb_limp.addWidget(self.lbl_bb_check_limp)
        row_bb_limp.addWidget(self.lbl_bb_iso_limp)
        row_bb_limp.addStretch()
        defense_main_layout.addLayout(row_bb_limp)
        
        # Row 5 (Postflop Agg: C-Bet, Fold to C-Bet)
        row_post_agg = QHBoxLayout()
        row_post_agg.addWidget(self.lbl_cbet)
        row_post_agg.addWidget(self.lbl_fold_to_cbet)
        row_post_agg.addStretch()
        defense_main_layout.addLayout(row_post_agg)
        
        # Row 6: WTSD / WSD
        row_wtsd = QHBoxLayout()
        row_wtsd.addWidget(self.lbl_wtsd)
        row_wtsd.addWidget(self.lbl_wsd)
        row_wtsd.addStretch()
        defense_main_layout.addLayout(row_wtsd)
        
        self.main_layout.addWidget(self.defense_group)

        # Начальная загрузка
        self.move(20, 50) # Closer to top-left
        self.show()
        # Даем интерфейсу время на отрисовку перед обновлением данных
        QTimer.singleShot(100, self.refresh_stats)
        self.toggle_mode() # Default to Mini Mode

    def _toggle_date_to(self, state):
        self.date_to.setEnabled(self.check_to.isChecked())

    def refresh_stats(self):
        """Запускает обновление статистики в отдельном потоке."""
        if self.loader_thread and self.loader_thread.isRunning():
            return # Уже обновляемся

        # 1. UI Feedback
        self.btn_refresh.setEnabled(False)
        self.btn_mini_refresh.setEnabled(False)
        self.btn_mini_refresh.setText("⏳") # Clock hourglass
        
        if self.is_mini_mode:
            self.mini_stats_label.setText("Загрузка...")

        # 2. Определяем параметры
        qdate_from = self.date_from.date()
        dt_from = datetime.combine(qdate_from.toPython(), time.min)

        dt_to = None
        if self.check_to.isChecked():
            qdate_to = self.date_to.date()
            dt_to = datetime.combine(qdate_to.toPython(), time.max)
            
        # 3. Запускаем поток
        self.loader_thread = StatsLoaderThread(self.target_player, dt_from, dt_to)
        self.loader_thread.stats_loaded.connect(self.on_stats_loaded)
        self.loader_thread.start()

    @Slot(object)
    def on_stats_loaded(self, stats):
        """Слот, вызываемый по завершении потока."""
        self.loader_thread = None
        
        # Восстанавливаем кнопки
        self.btn_refresh.setEnabled(True)
        self.btn_mini_refresh.setEnabled(True)
        self.btn_mini_refresh.setText("⟳")
        
        if stats:
             self.update_stats_table(stats)
        else:
             if self.is_mini_mode:
                  self.mini_stats_label.setText("Нет данных")

    # update_stats_table остается без изменений, он обновляет UI.


    def closeEvent(self, event):
        self.close_all_children()
        self.window_closed.emit()
        event.accept()

    def close_all_children(self):
        """Закрывает все дочерние окна (графики и т.д.)."""
        # Закрываем окно графика
        if hasattr(self, '_graph_window') and self._graph_window:
            self._graph_window.close()
            self._graph_window = None
        
        # Если есть другие (например, HandChartDialog блокирующий, он закроется сам)
        pass

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
            self.btn_mini_refresh.show() # Show refresh button in mini mode
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
            self.btn_mini_refresh.hide() # Hide refresh button in full mode
            self.btn_mini.setText("_")
            self.adjust_window_size()

    def on_view_mode_changed(self):
        """Redraws table with new mode using cached stats."""
        if hasattr(self, 'current_stats') and self.current_stats:
            self.update_stats_table(self.current_stats)

    def update_stats_table(self, stats: Dict[str, Dict[str, Any]]):
        """Заполняет таблицу данными."""
        self.current_stats = stats # Save for mini mode
        
        # Determine Mode
        mode = self.view_mode_combo.currentText()
        # Update Row Headers based on mode
        suffix = ""
        if mode == "Total ($)": suffix = " ($)"
        elif mode == "Total (BB)": suffix = " (BB)"
        elif mode == "BB/100": suffix = " BB/100"
        
        self.stats_table.setVerticalHeaderLabels([
            "Hands", "VPIP %", "PFR %", "RFI %", 
            f"Net Won{suffix}", f"WSD{suffix}", f"WNSD{suffix}", f"EV{suffix}"
        ])

        # Update Mini Label dynamically
        if self.is_mini_mode:
             hands = stats.get('hands', {}).get('total', 0)
             vpip = stats.get('vpip', {}).get('total', '-')
             pfr = stats.get('pfr', {}).get('total', '-')
             self.mini_stats_label.setText(f"Hands: {hands} | VPIP: {vpip}% | PFR: {pfr}%")
        
        positions = ["total", "utg", "mp", "co", "bu", "sb", "bb"]
        
        hands_data = stats.get('hands', {})
        vpip_data = stats.get('vpip', {})
        pfr_data = stats.get('pfr', {})
        rfi_data = stats.get('rfi', {})
        
        # Raw Data Sources
        net_won_data = stats.get('net_won', {})      # Dollars
        bb_won_data = stats.get('bb_won', {})        # BB Sum (Total BB)
        
        wsd_profit_data = stats.get('wsd_profit', {}) # Dollars
        wsd_bb_data = stats.get('wsd_bb', {})         # BB Sum
        
        wnsd_profit_data = stats.get('wnsd_profit', {}) # Dollars
        wnsd_bb_data = stats.get('wnsd_bb', {})         # BB Sum
        
        ev_data = stats.get('ev', {})               # Dollars
        ev_bb_data = stats.get('ev_bb', {})         # BB Sum

        # Helper to get the right value for the cell
        def get_mode_value(pos, dollar_dict, bb_dict, cnt):
            if mode == "Total ($)":
                return dollar_dict.get(pos, 0.0)
            elif mode == "Total (BB)":
                return bb_dict.get(pos, 0.0)
            elif mode == "BB/100":
                bb_total = bb_dict.get(pos, 0.0)
                if cnt > 0:
                    return (bb_total / cnt) * 100
                return 0.0
            return 0.0

        def set_cell_fin(row, col, val, is_bb100_mode=False):
            text_val = f"{val:.2f}"
            if is_bb100_mode: text_val = f"{val:+.2f}" # Always show sign for BB/100
            elif mode == "Total ($)": text_val = f"${val:.2f}"
            elif mode == "Total (BB)": text_val = f"{val:+.1f} BB"
            
            item = QTableWidgetItem(text_val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Color logic
            if val > 0: item.setForeground(QColor("#00FF00"))
            elif val < 0: item.setForeground(QColor("#FF0000"))
            
            self.stats_table.setItem(row, col, item)

        def set_cell_simple(row, col, val):
            item = QTableWidgetItem(str(val))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stats_table.setItem(row, col, item)

        for col_idx, pos in enumerate(positions):
            cnt_hands = hands_data.get(pos, 0)
            
            # Row 0: Hands
            set_cell_simple(0, col_idx, cnt_hands)
            # Row 1: VPIP
            set_cell_simple(1, col_idx, vpip_data.get(pos, "0.0"))
            # Row 2: PFR
            set_cell_simple(2, col_idx, pfr_data.get(pos, "0.0"))
            
            # Financial Rows
            # Row 4: Net Won
            val_net = get_mode_value(pos, net_won_data, bb_won_data, cnt_hands)
            set_cell_fin(4, col_idx, val_net, mode=="BB/100")
            
            # Row 5: WSD
            val_wsd = get_mode_value(pos, wsd_profit_data, wsd_bb_data, cnt_hands)
            set_cell_fin(5, col_idx, val_wsd, mode=="BB/100")
            
            # Row 6: WNSD
            val_wnsd = get_mode_value(pos, wnsd_profit_data, wnsd_bb_data, cnt_hands)
            set_cell_fin(6, col_idx, val_wnsd, mode=="BB/100")
            
            # Row 7: EV
            val_ev = get_mode_value(pos, ev_data, ev_bb_data, cnt_hands)
            set_cell_fin(7, col_idx, val_ev, mode=="BB/100")

        # Row 3: RFI
        rfi_positions = ["utg", "mp", "co", "bu", "sb"]
        set_cell_simple(3, 0, "-") 
        
        for i, pos in enumerate(rfi_positions):
             set_cell_simple(3, i+1, rfi_data.get(pos, "0.0"))
        
        # BB RFI
        set_cell_simple(3, 6, "-")

        # --- Update Blind Defense Stats ---
        bb_def = stats.get('bb_defense', {})
        self.lbl_bb_fold.setText(f"<b>BB Fold to Steal:</b> {bb_def.get('fold_to_steal', '-')}%")
        self.lbl_bb_call.setText(f"<b>BB Call vs Steal:</b> {bb_def.get('call_steal', '-')}%")
        self.lbl_bb_3bet.setText(f"<b>BB 3Bet vs Steal:</b> {bb_def.get('3bet_steal', '-')}%")
        
        # Steal Success
        steal_succ = stats.get('steal_success', '-')
        self.lbl_steal_succ.setText(f"<b>Steal Success:</b> {steal_succ}%")
        
        # BB vs Limp Stats
        bb_limp = stats.get('bb_vs_limp', {})
        self.lbl_bb_check_limp.setText(f"<b>BB Check vs Limp:</b> {bb_limp.get('check', '-')}%")
        self.lbl_bb_iso_limp.setText(f"<b>BB Iso vs Limp:</b> {bb_limp.get('iso', '-')}%")
        
        # Aggression Stats
        t3bet = stats.get('3bet', {}).get('total', '-')
        cbet = stats.get('cbet', {}).get('total', '-')
        fcbet = stats.get('fold_to_cbet', {}).get('total', '-')
        
        self.lbl_3bet.setText(f"<b>3-Bet:</b> {t3bet}%")
        self.lbl_cbet.setText(f"<b>C-Bet:</b> {cbet}%")
        self.lbl_fold_to_cbet.setText(f"<b>Fold to C-Bet:</b> {fcbet}%")
        
        f3bet = stats.get('fold_to_3bet', {}).get('total', '-')
        self.lbl_fold_to_3bet.setText(f"<b>Fold to 3-Bet:</b> {f3bet}%")
        
        # WTSD/WSD
        wtsd_data = stats.get('wtsd', {})
        self.lbl_wtsd.setText(f"<b>WTSD:</b> {wtsd_data.get('wtsd', '-')}%")
        self.lbl_wsd.setText(f"<b>WSD:</b> {wtsd_data.get('wsd', '-')}%")

        self.stats_table.viewport().update()
        self.adjust_window_size()

    def adjust_window_size(self):
        """Подгоняет размер окна под контент."""
        self.stats_table.resizeColumnsToContents()
        self.stats_table.resizeRowsToContents()
        
        # Calculate full table width
        v_header_w = self.stats_table.verticalHeader().width()
        cols_w = sum(self.stats_table.columnWidth(i) for i in range(self.stats_table.columnCount()))
        table_content_w = v_header_w + cols_w + 10 # + small buffer
        
        # Force table min width so layout respects it
        self.stats_table.setMinimumWidth(table_content_w)
        
        # Calculate height
        h_header_h = self.stats_table.horizontalHeader().height()
        rows_h = sum(self.stats_table.rowHeight(i) for i in range(self.stats_table.rowCount()))
        # Set Min Height for table too
        self.stats_table.setMinimumHeight(h_header_h + rows_h + 5)

        # Trigger layout update
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
        positions = ['total', 'utg', 'mp', 'co', 'bu', 'sb', 'bb']
        
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
        

        data = get_chart_hands_data(
            self.target_player, 
            stat_type, 
            position, 
            min_time=dt_from, 
            max_time=dt_to
        )
        
        if not data:
            return
            
        dlg = HandChartDialog(f"Hands: {stat_type.upper()} @ {position.upper()}", data)
        dlg.exec()

    def open_graph(self):
        """Opens the graph widget in a separate window."""
        try:
            # 1. Determine Date Range
            qdate_from = self.date_from.date()
            dt_from = datetime.combine(qdate_from.toPython(), time.min)
            dt_to = None
            if self.check_to.isChecked():
                qdate_to = self.date_to.date()
                dt_to = datetime.combine(qdate_to.toPython(), time.max)
            
            # 2. Fetch Data
            df = get_player_hand_log_df(self.target_player, min_time=dt_from, max_time=dt_to)
            
            if df.empty:

                return

            # 3. Open Window
            # Use 'self' as parent? better creating a Dialog or independent widget.
            # Independent widget is better for resizing.
            
            # Keep reference to avoid garbage collection
            self._graph_window = QWidget()
            self._graph_window.setWindowTitle(f"Graph: {self.target_player}")
            # Ensure it stays on top of the Always-On-Top parent stats window
            self._graph_window.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
            self._graph_window.resize(900, 600)
            layout = QVBoxLayout(self._graph_window)
            
            graph_widget = PokerGraphWidget()
            layout.addWidget(graph_widget)
            
            graph_widget.plot_data(df)
            
            self._graph_window.show()
            self._graph_window.raise_()
            self._graph_window.activateWindow()
            
        except Exception as e:
            print(f"Error opening graph: {e}")
