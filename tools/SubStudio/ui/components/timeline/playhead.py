from PyQt6.QtWidgets import QGraphicsLineItem
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPen, QColor

class PlayheadItem(QGraphicsLineItem):
    def __init__(self, track_count):
        super().__init__()
        self.track_count = track_count
        self.setPen(QPen(QColor("#FF4444"), 1))
        self.setZValue(1000) # 始终置顶
        self.update_length()
        
    def update_length(self):
        from .item import TRACK_HEIGHT
        self.setLine(0, 0, 0, self.track_count * TRACK_HEIGHT)

    def set_x(self, x):
        self.setPos(x, 0)
