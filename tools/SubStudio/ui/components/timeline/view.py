from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen

class TimelineView(QGraphicsView):
    def __init__(self, scene, parent_container):
        super().__init__(scene, parent_container)
        self.container = parent_container
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.dragging_seeker = False
        
        # 背景样式 (与标尺对齐的深色)
        self.setBackgroundBrush(QColor("#121212"))
        
        # 拖拽支持
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        self.container.files_dropped.emit(files)
        event.accept()

    def mousePressEvent(self, event):
        # 允许点击空白区域或辅助线进行跳转
        item = self.itemAt(event.position().toPoint())
        # 这里判断时，可以通过 zValue 或类型确定是否为背景
        if not item or (hasattr(item, 'zValue') and item.zValue() < 0): 
            scene_pos = self.mapToScene(event.position().toPoint())
            self.container.seek_to_x(scene_pos.x())
            self.dragging_seeker = True
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging_seeker:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.container.seek_to_x(scene_pos.x())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.dragging_seeker = False
        super().mouseReleaseEvent(event)
