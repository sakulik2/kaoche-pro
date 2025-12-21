from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QPen, QFont, QPainter, QPolygonF, QBrush, QPixmap

class TimelineRuler(QWidget):
    """
    SubStudio 专业时间轴标尺 (Optimized with Caching)
    支持动态刻度、防遮挡时间码、高对比度播放指示器
    """
    def __init__(self, parent_container):
        super().__init__(parent_container)
        self.container = parent_container
        self.setFixedHeight(32) # 标准紧凑风格
        self.pps = 0.1
        self.offset = 0
        self.dragging = False
        
        # 缓存机制: 背景刻度通常只有在滚动或缩放时才变
        # 播放头每帧动，但不应重绘整个背景
        self.bg_cache = None
        self._cache_dirty = True

    def set_pps(self, pps):
        if self.pps != pps:
            self.pps = pps
            self._cache_dirty = True
            self.update()

    def set_offset(self, offset):
        if self.offset != offset:
            self.offset = offset
            self._cache_dirty = True
            self.update()

    def resizeEvent(self, event):
        self._cache_dirty = True
        super().resizeEvent(event)

    def _update_cache(self):
        """重新生成背景刻度缓存"""
        if self.width() <= 0 or self.height() <= 0:
            return
            
        self.bg_cache = QPixmap(self.size())
        # self.bg_cache.setDevicePixelRatio(self.devicePixelRatio()) # HDPI support if needed
        self.bg_cache.fill(QColor("#121212"))
        
        painter = QPainter(self.bg_cache)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. 绘制背景与底线
        # painter.fillRect(self.rect(), QColor("#121212")) # 已 Fill
        painter.setPen(QPen(QColor("#252525"), 1))
        painter.drawLine(0, self.height()-1, self.width(), self.height()-1)
        
        if self.pps <= 0:
            painter.end()
            return
            
        width = self.width()
        start_ms = self.offset / self.pps
        
        # 2. 动态刻度计算
        target_label_gap_px = 120
        raw_interval = target_label_gap_px / self.pps
        
        intervals = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 30000, 60000, 300000]
        interval_ms = intervals[-1]
        for i in intervals:
            if i >= raw_interval:
                interval_ms = i
                break
        
        first_tick_ms = (int(start_ms) // interval_ms) * interval_ms
        
        # 3. 绘制刻度
        main_tick_pen = QPen(QColor("#777777"), 1)
        sub_tick_pen = QPen(QColor("#333333"), 1)
        text_pen = QPen(QColor("#999999"), 1)
        
        font = QFont("Segoe UI", 7)
        painter.setFont(font)
        
        max_ms = first_tick_ms + width / self.pps + interval_ms
        
        # Loop range
        for ms in range(int(first_tick_ms), int(max_ms), int(interval_ms)):
            x = (ms * self.pps) - self.offset
            if x < -50 or x > width + 50: continue
            
            # 主刻度
            painter.setPen(main_tick_pen)
            painter.drawLine(int(x), self.height() - 10, int(x), self.height() - 2)
            
            # 标签
            painter.setPen(text_pen)
            minutes = int(ms // 60000)
            seconds = (ms % 60000) / 1000.0
            time_str = f"{minutes:02d}:{seconds:04.1f}"
            painter.drawText(int(x) + 4, self.height() - 13, time_str)
            
            # 子刻度
            painter.setPen(sub_tick_pen)
            sub_count = 5 if interval_ms < 500 else 10
            sub_interval = interval_ms / sub_count
            for j in range(1, sub_count):
                sx = x + (j * sub_interval * self.pps)
                if 0 <= sx <= width:
                    painter.drawLine(int(sx), self.height() - 6, int(sx), self.height() - 2)
                    
        painter.end()
        self._cache_dirty = False

    def paintEvent(self, event):
        painter = QPainter(self)
        
        # 1. 绘制缓存的背景
        if self._cache_dirty or not self.bg_cache:
            self._update_cache()
            
        if self.bg_cache:
            painter.drawPixmap(0, 0, self.bg_cache)
        else:
            # Fallback
            painter.fillRect(self.rect(), QColor("#121212"))
            
        # 2. 绘制动态播放头 (三角形)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        ph_x = (self.container.play_time_ms * self.pps) - self.offset
        
        # 仅在可见范围内绘制
        if -15 <= ph_x <= width + 15:
            painter.setBrush(QColor("#3498DB"))
            painter.setPen(Qt.PenStyle.NoPen)
            
            poly = QPolygonF([
                QPointF(ph_x - 6, 0),
                QPointF(ph_x + 6, 0),
                QPointF(ph_x, 10)
            ])
            painter.drawPolygon(poly)
            
            # 引导线
            painter.setPen(QPen(QColor(52, 152, 219, 100), 1, Qt.PenStyle.SolidLine))
            painter.drawLine(int(ph_x), 10, int(ph_x), self.height())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.container.seek_to_x(event.position().x() + self.offset)
            self.dragging = True

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.container.seek_to_x(event.position().x() + self.offset)

    def mouseReleaseEvent(self, event):
        self.dragging = False
