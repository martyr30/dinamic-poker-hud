from PySide6.QtWidgets import QWidget, QGridLayout, QLabel, QDialog, QVBoxLayout
from PySide6.QtCore import Qt
from typing import Dict, List

class HandMatrixWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QGridLayout(self)
        self.layout.setSpacing(2)
        self.cells = {} # Map "AKs" -> QLabel
        self._init_grid()

    def _init_grid(self):
        ranks = "AKQJT98765432"
        for i, r1 in enumerate(ranks):
            for j, r2 in enumerate(ranks):
                # Logic for hand notation
                if i < j:
                    # Suited (Upper right)
                    hand = f"{r1}{r2}s"
                    bg_color = "#f0f0f0" # Default
                    text_color = "#333"
                elif i > j:
                    # Offsuit (Lower left)
                    hand = f"{r2}{r1}o" # r2 (lower index in string, but actually higher rank)
                    # Wait. Rows are i (r1). Cols are j (r2).
                    # If i > j: r1 is lower rank (since K is index 1, A is 0).
                    # Notation uses HIGHER rank first.
                    # so if r1=K(1), r2=A(0). i > j (1 > 0).
                    # Hand is AKo. r2 is A. r1 is K.
                    hand = f"{r2}{r1}o"
                    bg_color = "#e0e0e0"
                    text_color = "#333"
                else:
                    # Pair (Diagonal)
                    hand = f"{r1}{r2}"
                    bg_color = "#d0d0d0"
                    text_color = "#333"

                lbl = QLabel(hand)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setFixedSize(30, 30)
                lbl.setStyleSheet(f"background-color: {bg_color}; color: {text_color}; border: 1px solid #ccc; font-size: 10px;")
                
                self.layout.addWidget(lbl, i, j)
                self.cells[hand] = lbl

    def set_data(self, hand_counts: Dict[str, int]):
        """Highlights hands present in hand_counts."""
        if not hand_counts:
            self.reset_grid()
            return
            
        max_val = max(hand_counts.values()) if hand_counts else 1
        
        for hand, lbl in self.cells.items():
            count = hand_counts.get(hand, 0)
            if count > 0:
                # Active! Blue.
                # Opacity based on frequency? Or just Solid Blue?
                # User asked for "Visualization". Simple Blue is safest start.
                color = "#3498db" # Blue
                lbl.setStyleSheet(f"background-color: {color}; color: white; border: 1px solid #2980b9; font-weight: bold;")
                lbl.setToolTip(f"{hand}: {count} hands")
            else:
                # Reset
                self._reset_cell_style(hand, lbl)

    def reset_grid(self):
        for hand, lbl in self.cells.items():
            self._reset_cell_style(hand, lbl)

    def _reset_cell_style(self, hand, lbl):
        # Determine base style again (lazy way)
        is_suited = 's' in hand
        is_off = 'o' in hand
        is_pair = not is_suited and not is_off
        
        if is_suited: bg = "#f0f0f0"
        elif is_off: bg = "#e0e0e0"
        else: bg = "#d0d0d0"
        
        lbl.setStyleSheet(f"background-color: {bg}; color: #888; border: 1px solid #ccc;")
        lbl.setToolTip("")

class HandChartDialog(QDialog):
    def __init__(self, title, data):
        super().__init__()
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Tool) # Popup
        layout = QVBoxLayout(self)
        
        self.matrix = HandMatrixWidget()
        self.matrix.set_data(data)
        layout.addWidget(self.matrix)
        
        # Info Label
        total = sum(data.values())
        lbl = QLabel(f"Total Hands: {total}")
        layout.addWidget(lbl)
