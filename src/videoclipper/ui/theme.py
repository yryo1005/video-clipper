from __future__ import annotations

from videoclipper.config import BASE_FONT_SIZE

STYLESHEET = """
QWidget {
    background-color: #202124;
    color: #e8e8e8;
    font-size: __FONT_SIZE__pt;
}

QMainWindow, QMessageBox {
    background-color: #202124;
}

QLabel {
    background: transparent;
}

QPushButton {
    background-color: #33353a;
    border: 1px solid #45484f;
    border-radius: 4px;
    padding: 5px 10px;
}

QPushButton:hover {
    background-color: #3d4046;
}

QPushButton:pressed {
    background-color: #2a2c30;
}

QPushButton:disabled {
    color: #777;
    background-color: #2a2c30;
}

QLineEdit, QComboBox {
    background-color: #2a2c30;
    border: 1px solid #45484f;
    border-radius: 4px;
    padding: 3px 6px;
    selection-background-color: #4a6fa5;
}

QComboBox QAbstractItemView {
    background-color: #2a2c30;
    selection-background-color: #4a6fa5;
}

QListWidget, QTreeWidget {
    background-color: #26282c;
    border: 1px solid #3a3c42;
    border-radius: 4px;
    alternate-background-color: #2a2c30;
}

QTreeWidget::item {
    padding: 3px;
}

QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #4a6fa5;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #3a3a3a;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #9aa0a6;
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QSlider::groove:vertical {
    width: 6px;
    background: #3a3a3a;
    border-radius: 3px;
}

QSlider::handle:vertical {
    background: #9aa0a6;
    height: 14px;
    margin: 0 -5px;
    border-radius: 7px;
}

QMenu {
    background-color: #2a2c30;
    border: 1px solid #45484f;
}

QMenu::item:selected {
    background-color: #4a6fa5;
}
""".replace("__FONT_SIZE__", str(BASE_FONT_SIZE))
