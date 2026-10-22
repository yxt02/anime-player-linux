"""Dark theme stylesheet and palette."""

ACCENT = "#3ec8a0"          # teal accent
ACCENT_HOVER = "#57dbb5"
BG = "#14141c"
BG_ELEVATED = "#1c1c26"
BG_CARD = "#22222e"
TEXT = "#e8e8f0"
TEXT_DIM = "#9a9aad"
DANGER = "#e05c5c"

STYLE_SHEET = f"""
* {{
    font-family: "Noto Sans CJK SC", "WenQuanYi Micro Hei", "Sans CJK SC", sans-serif;
    color: {TEXT};
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#sidebar {{
    background: {BG_ELEVATED};
    border-right: 1px solid #26263a;
}}
QLabel#brand {{
    font-size: 18px;
    font-weight: 700;
    color: {ACCENT};
    padding: 18px 12px 8px 12px;
}}
QPushButton.nav {{
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 11px 14px;
    font-size: 14px;
    text-align: left;
    color: {TEXT_DIM};
}}
QPushButton.nav:hover {{ background: #26263a; color: {TEXT}; }}
QPushButton.nav:checked {{ background: {ACCENT}; color: white; font-weight: 600; }}
QPushButton {{
    background: {BG_CARD};
    border: 1px solid #2c2c3c;
    border-radius: 8px;
    padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton#primary {{
    background: {ACCENT};
    border: none;
    color: white;
    font-weight: 600;
    padding: 8px 18px;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: #3a3a4c; color: {TEXT_DIM}; }}
QLineEdit, QComboBox, QSpinBox {{
    background: {BG_CARD};
    border: 1px solid #2c2c3c;
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea {{ background: {BG}; }}
QScrollArea > QWidget {{ background: {BG}; }}
QWidget#page {{ background: {BG}; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #34344a; border-radius: 5px; min-height: 30px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QFrame#banner {{ border-radius: 12px; background: {BG_CARD}; }}
QLabel.title {{ font-size: 15px; font-weight: 600; }}
QLabel.dim {{ color: {TEXT_DIM}; font-size: 12px; }}
QFrame#card {{
    background: {BG_CARD};
    border: 1px solid #262636;
    border-radius: 10px;
}}
QFrame#card:hover {{ border-color: {ACCENT}; }}
QToolTip {{ background: {BG_ELEVATED}; border: 1px solid #34344a; padding: 6px; }}
QStatusBar {{ background: {BG_ELEVATED}; color: {TEXT_DIM}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; padding: 8px 16px; color: {TEXT_DIM};
}}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QSlider::groove:horizontal {{ height: 4px; background: #34344a; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 12px; height: 12px; margin: -4px 0;
    background: {ACCENT}; border-radius: 6px;
}}
QTableWidget {{
    background: {BG_ELEVATED};
    gridline-color: #262636;
    border: none;
}}
QHeaderView::section {{
    background: {BG_CARD}; border: none; padding: 6px; color: {TEXT_DIM};
}}
"""
