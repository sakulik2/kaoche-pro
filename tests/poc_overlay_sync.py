import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QFrame, QVBoxLayout, QWidget, QLabel
from PyQt6.QtCore import Qt, QPoint, QEvent, QTimer, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QPen

class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绿色描边：严丝合缝校验
        painter.setBrush(QColor(0, 255, 0, 10))
        painter.setPen(QPen(QColor(0, 255, 0), 2))
        # 绘制 1 像素内缩的线，确保能看到蓝色边框被包裹
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
        
        painter.setPen(QColor(255, 0, 0))
        painter.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "【V5 对齐校验层】\nCUDA 12.8 环境确认")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SubStudio POC v5 - 坐标补强版")
        self.resize(800, 600)
        
        cw = QWidget()
        self.setCentralWidget(cw)
        layout = QVBoxLayout(cw)
        layout.setContentsMargins(40, 40, 40, 40)
        
        self.container = QFrame()
        self.container.setStyleSheet("border: 5px solid blue; background-color: #FAFAFA;")
        
        inner = QVBoxLayout(self.container)
        self.info = QLabel("正在使用【四角坐标映射】算法...\n请观察绿色框是否正好落在蓝色边框的中线上")
        self.info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.addWidget(self.info)
        
        layout.addWidget(self.container)
        
        self.overlay = OverlayWindow()
        self.overlay.show()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync)
        self.timer.start(16)
        
        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.WindowDeactivate:
            self.overlay.hide()
        elif event.type() == QEvent.Type.WindowActivate:
            self.overlay.show()
        return super().eventFilter(obj, event)

    def sync(self):
        if not self.isActiveWindow(): return
        
        # 算法改进：不再直接取 size，而是通过 mapToGlobal 映射矩形的两个关键点
        # 这可以规避逻辑像素缩放不一致的问题
        top_left = self.container.mapToGlobal(QPoint(0, 0))
        bottom_right = self.container.mapToGlobal(QPoint(self.container.width(), self.container.height()))
        
        actual_rect = QRect(top_left, bottom_right)
        
        # 调试输出
        if self.overlay.geometry() != actual_rect:
            self.overlay.setGeometry(actual_rect)
            # print(f"[SYNC] Rect: {actual_rect.x()}, {actual_rect.y()}, {actual_rect.width()}x{actual_rect.height()}")

    def closeEvent(self, event):
        self.overlay.close()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
