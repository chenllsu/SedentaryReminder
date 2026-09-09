"""Qt6 关闭选择框：退出程序 / 最小化到托盘 / 取消。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
)
from PySide6.QtGui import QPainter, QPainterPath, QColor
from PySide6.QtWidgets import QFrame


class ChoiceWindow(QWidget):
    """轻量小窗，置于妮子浮窗旁。"""
    action_chosen = Signal(str)   # "exit" | "minimize" | "cancel"

    def __init__(self, ctrl, on_exit, on_minimize):
        super().__init__()
        self.ctrl = ctrl
        self.on_exit = on_exit
        self.on_minimize = on_minimize
        self.setWindowTitle("关闭浮窗")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Popup | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(260, 132)

        frame = QFrame(self)
        frame.setObjectName("card")
        frame.setStyleSheet(
            "#card { background: #fff7e6; border: 1px solid #e6d8b5;"
            " border-radius: 12px; }")
        frame.setGeometry(6, 6, 248, 120)

        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)
        title = QLabel("要怎么关闭浮窗？")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 13px; color:#5a4a2a;")
        lay.addWidget(title)

        row = QHBoxLayout()
        b_exit = QPushButton("退出程序")
        b_min = QPushButton("最小化到托盘")
        b_exit.clicked.connect(lambda: (self.close(), self.on_exit()))
        b_min.clicked.connect(lambda: (self.close(), self.on_minimize()))
        row.addWidget(b_exit)
        row.addWidget(b_min)
        lay.addLayout(row)

        b_cancel = QPushButton("取消")
        b_cancel.clicked.connect(self.close)
        lay.addWidget(b_cancel, alignment=Qt.AlignCenter)

    def show_beside(self, ref):
        rx = ref.window().frameGeometry().x()
        ry = ref.window().frameGeometry().y()
        self.move(rx + 24, ry + 24)
        self.show()
