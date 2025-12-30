import sys
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QRadioButton, QButtonGroup, QLabel, QComboBox
from PySide6.QtCore import Qt
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates

class PokerGraphWidget(QWidget):
    """
    Виджет для отображения покерного графика (Net Won, EV, Showdown, Non-Showdown).
    Принимает Pandas DataFrame.
    Поддерживает переключение между валютой ($) и большими блайндами (BB).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Настройка Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(5)

        # --- Панель управления ---
        self.controls_layout = QHBoxLayout()
        self.controls_layout.setContentsMargins(10, 5, 10, 0)
        
        self.mode_label = QLabel("Mode:")
        self.mode_label.setStyleSheet("color: gray; font-weight: bold;")
        self.controls_layout.addWidget(self.mode_label)

        self.radio_bb = QRadioButton("Big Blinds (BB)")
        self.radio_bb.setChecked(True)
        self.radio_bb.setStyleSheet("color: white;")

        self.radio_usd = QRadioButton("Money ($)")
        self.radio_usd.setStyleSheet("color: white;")
        
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_bb, 0)
        self.mode_group.addButton(self.radio_usd, 1)
        
        self.controls_layout.addWidget(self.radio_bb)
        self.controls_layout.addWidget(self.radio_usd)
        
        # --- Position Filter ---
        self.controls_layout.addSpacing(20)
        self.pos_label = QLabel("Pos:")
        self.pos_label.setStyleSheet("color: gray; font-weight: bold;")
        self.controls_layout.addWidget(self.pos_label)
        
        self.pos_combo = QComboBox()
        self.pos_combo.addItem("All")
        self.pos_combo.setStyleSheet("""
            QComboBox { 
                background-color: #3b3b3b; 
                color: white; 
                border: 1px solid gray; 
                padding: 2px;
                min-width: 60px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #3b3b3b;
                color: white;
                selection-background-color: #555555;
                selection-color: white;
                border: 1px solid gray;
            }
        """)
        self.controls_layout.addWidget(self.pos_combo)
        
        self.controls_layout.addStretch()

        self.main_layout.addLayout(self.controls_layout)
        
        # --- График ---
        # Создаем фигуру Matplotlib
        plt.style.use('dark_background')
        
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.figure)

        # Header Label
        self.header_label = QLabel("Cumulative Results")
        self.header_label.setAlignment(Qt.AlignCenter)
        self.header_label.setStyleSheet("QLabel { font-size: 16px; font-weight: bold; color: white; margin-bottom: 5px; }")
        self.main_layout.addWidget(self.header_label)

        self.main_layout.addWidget(self.canvas)
        
        # Настройка цветов графика под темную тему
        self.figure.patch.set_facecolor('#2b2b2b')
        
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor('#2b2b2b')
        
        # Данные
        # Данные
        self.df = None
        self.full_df = None
        self.current_mode = 'BB' # Default to BB
        self.current_position = 'All'

        # Связываем сигналы
        self.mode_group.buttonToggled.connect(self._on_mode_changed)
        self.pos_combo.currentTextChanged.connect(self._on_position_changed)

    def _on_mode_changed(self, button, checked):
        if not checked: return
        
        if button == self.radio_usd:
            self.current_mode = 'USD'
        else:
            self.current_mode = 'BB'
            
        self._redraw_graph()

    def plot_data(self, df: pd.DataFrame):
        """
        Строит график по переданному DataFrame.
        """
        self.full_df = df.copy()
        self._update_position_filter()
        self._apply_filters()

    def _update_position_filter(self):
        self.pos_combo.blockSignals(True)
        self.pos_combo.clear()
        self.pos_combo.addItem("All")
        
        if self.full_df is not None and 'position' in self.full_df.columns:
            unique_pos = self.full_df['position'].dropna().astype(str).unique().tolist()
            
            # Position ranking (Standard 6-max/9-max starting from UTG)
            pos_rank = {
                'UTG': 1, 'UTG1': 2, 'UTG+1': 2, 'UTG2': 3, 'UTG+2': 3,
                'EP': 4, 'MP': 5, 'MP1': 6, 'HJ': 7, 
                'CO': 8, 'CUTOFF': 8,
                'BTN': 9, 'BUTTON': 9, 'BU': 9, 'D': 9,
                'SB': 10, 'BB': 11
            }
            
            # Sort: Known positions by rank, then others alphabetically
            positions = sorted(unique_pos, key=lambda p: (pos_rank.get(p.upper(), 99), p))
            self.pos_combo.addItems(positions)
            
        self.pos_combo.setCurrentText("All")
        self.current_position = "All"
        self.pos_combo.blockSignals(False)
        
    def _on_position_changed(self, text):
        self.current_position = text
        self._apply_filters()
        
    def _apply_filters(self):
        if self.full_df is None:
            self.df = None
            self._redraw_graph()
            return
            
        if self.current_position == "All" or not self.current_position:
            self.df = self.full_df.copy()
        else:
             if 'position' in self.full_df.columns:
                 # Filter by position
                 self.df = self.full_df[self.full_df['position'] == self.current_position].copy()
             else:
                 self.df = self.full_df.copy()
                 
        self._redraw_graph()

    def _redraw_graph(self):
        try:
            if self.df is None or self.df.empty:
                self.ax.clear()
                self.canvas.draw()
                if hasattr(self, 'header_label'):
                    self.header_label.setText("No Data")
                return
            
            # Выбор колонок в зависимости от режима
            col_net = 'net_won'
            col_ev = 'ev_adjusted'
            col_sd = 'showdown_won'
            col_nsd = 'non_showdown_won'
            
            if self.current_mode == 'BB':
                if 'bb_won' in self.df.columns: col_net = 'bb_won'
                elif 'net_won_bb' in self.df.columns: col_net = 'net_won_bb'
                else: pass
                
                if 'ev_adjusted_bb' in self.df.columns: col_ev = 'ev_adjusted_bb'
                if 'showdown_won_bb' in self.df.columns: col_sd = 'showdown_won_bb'
                if 'non_showdown_won_bb' in self.df.columns: col_nsd = 'non_showdown_won_bb'

            self.ax.clear()
            
            # 1. Расчет кумулятивных сумм
            # Net
            if col_net in self.df.columns:
                data_net = self.df[col_net].cumsum()
            elif self.current_mode == 'BB' and 'net_won' in self.df.columns:
                 data_net = pd.Series([0]*len(self.df))
            else:
                if hasattr(self, 'header_label'):
                    self.header_label.setText("No Data (Missing Net Won)")
                return

            # EV
            if col_ev in self.df.columns:
                # Fill NaNs with Net Won (Realized EV)
                if self.df[col_ev].isnull().any():
                     # Caution: fillna with column requires index alignment, which implies row-wise fill if correctly done.
                     # ensure alignment
                     self.df[col_ev] = self.df[col_ev].fillna(self.df[col_net])
                     # Safety fallback if net is also NaN (shouldnt happen)
                     self.df[col_ev] = self.df[col_ev].fillna(0.0)
                data_ev = self.df[col_ev].cumsum()
            else:
                 data_ev = pd.Series([0]*len(self.df))
                 
            # SD / NSD
            has_sd_col = col_sd in self.df.columns
            has_nsd_col = col_nsd in self.df.columns
            
            if has_sd_col:
                data_sd = self.df[col_sd].cumsum()
            else:
                # Пытаемся вычислить из Net
                if 'wtsd' in self.df.columns and col_net in self.df.columns:
                     sd_vals = self.df.apply(lambda x: x[col_net] if x['wtsd'] else 0.0, axis=1)
                     data_sd = sd_vals.cumsum()
                else:
                     data_sd = pd.Series([0]*len(self.df))

            if has_nsd_col:
                data_nsd = self.df[col_nsd].cumsum()
            else:
                # Пытаемся вычислить из Net
                if 'wtsd' in self.df.columns and col_net in self.df.columns:
                     # NSD = Total - SD (roughly) or logic: if not wtsd, then val.
                     # But simple approach: all profit where NOT wtsd
                     nsd_vals = self.df.apply(lambda x: x[col_net] if not x['wtsd'] else 0.0, axis=1)
                     data_nsd = nsd_vals.cumsum()
                else:
                     data_nsd = pd.Series([0]*len(self.df))

            # Ось X
            x_values = range(len(self.df))

            # 2. Рисование
            self.ax.plot(x_values, data_sd, label='Showdown', color='#2980b9', linewidth=1.5, alpha=0.9)
            self.ax.plot(x_values, data_nsd, label='Non-Showdown', color='#e74c3c', linewidth=1.5, alpha=0.9)
            self.ax.plot(x_values, data_ev, label='EV Adjusted', color='#f1c40f', linewidth=2, alpha=0.7)
            self.ax.plot(x_values, data_net, label='Net Won', color='#2ecc71', linewidth=2.5)

            # 3. Оформление
            self.ax.axhline(0, color='gray', linestyle='--', linewidth=1, alpha=0.5)
            self.ax.grid(True, which='both', color='gray', linestyle='-', linewidth=0.5, alpha=0.2)
            self.ax.legend(loc='upper left', frameon=True, facecolor='#2b2b2b', edgecolor='gray')
            
            title_unit = "($)" if self.current_mode == 'USD' else "(BB)"
            
            # Calculate Stats for Header
            total_val = 0.0
            bb_100 = 0.0
            if not data_net.empty:
                total_val = float(data_net.iloc[-1])
                
            color = "#2ecc71" if total_val > 0 else "#e74c3c" if total_val < 0 else "gray"
            
            stats_html = ""
            if self.current_mode == 'USD':
                fmt_val = f"+${total_val:,.2f}" if total_val >= 0 else f"-${abs(total_val):,.2f}"
                stats_html = f"<span style='color: {color};'>({fmt_val})</span>"
            else:
                # BB Mode
                total_hands = len(self.df)
                if total_hands > 0:
                    bb_100 = (total_val / total_hands) * 100
                    
                fmt_val = f"+{total_val:,.1f}" if total_val >= 0 else f"{total_val:,.1f}"
                stats_html = f"<span style='color: {color};'>({fmt_val} BB / {bb_100:.1f} BB/100)</span>"
                
            if hasattr(self, 'header_label'):
                self.header_label.setText(f"Cumulative Results {title_unit} {stats_html}")

            self.ax.set_xlabel("Hands", color='gray')
            self.ax.set_ylabel(f"Result {title_unit}", color='gray')
            
            self.ax.tick_params(axis='x', colors='gray')
            self.ax.tick_params(axis='y', colors='gray')
            
            for spine in self.ax.spines.values():
                spine.set_color('gray')
                spine.set_alpha(0.5)

            self.canvas.draw()

        except Exception as e:
            print(f"CRITICAL GRAPH ERROR: {e}")
            import traceback
            traceback.print_exc()

        # End of _redraw_graph logic


# --- Тестовый запуск ---
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import numpy as np

    app = QApplication(sys.argv)
    
    np.random.seed(42)
    n_hands = 500
    
    # Генерация данных
    net_won = np.random.normal(0, 5, n_hands)
    wtsd = np.random.choice([True, False], n_hands, p=[0.25, 0.75])
    
    # Имитация BB
    # Предположим NL100 ($1) -> 1 BB = $1. (Упрощенно)
    # Или NL2 ($0.02) -> 1 BB = $0.02
    bb_size = 1.0 
    bb_won = net_won / bb_size
    
    data = {
        'net_won': net_won,
        'bb_won': bb_won,  # Колонка для BB
        'ev_adjusted': np.random.normal(0.5, 4, n_hands),
        'ev_adjusted_bb': np.random.normal(0.5, 4, n_hands) / bb_size,
        'wtsd': wtsd,
        'position': np.random.choice(['BTN', 'SB', 'BB', 'UTG'], n_hands)
    }
    
    df = pd.DataFrame(data)
    
    # Корректировка WTSD
    # для наглядности
    df.loc[df['wtsd'], 'net_won'] = np.random.normal(0, 20, df['wtsd'].sum())
    df['bb_won'] = df['net_won'] / bb_size # пересчит
    
    window = QWidget()
    window.setWindowTitle("Test Poker Graph (Toggle)")
    window.resize(900, 600)
    layout = QVBoxLayout(window)
    
    graph = PokerGraphWidget()
    layout.addWidget(graph)
    
    graph.plot_data(df)
    
    window.show()
    sys.exit(app.exec())
