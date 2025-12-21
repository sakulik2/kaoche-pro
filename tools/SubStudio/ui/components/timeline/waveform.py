from PyQt6.QtWidgets import QGraphicsPathItem
from PyQt6.QtGui import QPainterPath, QColor, QPen, QBrush, QPainter, QPolygonF, QPixmap, QLinearGradient
from PyQt6.QtCore import Qt, QRectF, QPointF
import numpy as np
import math

class WaveformItem(QGraphicsPathItem):
    """
    工业级分块波形渲染图层 (Tiled Waveform)
    将长音频拆分为 10 秒一个的瓦片 (Tile) 进行缓存，
    拖拽字幕时仅重绘局部受影响的瓦片，彻底消除延迟。
    """
    def __init__(self, peaks_data, chunk_ms=10, height=80, max_tracks=8):
        super().__init__()
        # Peaks 数据处理
        if peaks_data.ndim == 2:
            # 取最大值并进行初步归一化
            self.l0 = np.max(np.abs(peaks_data), axis=1)
        else:
            self.l0 = peaks_data
            
        # 归一化到 0-1
        max_val = np.max(self.l0) if len(self.l0) > 0 else 1
        if max_val > 0:
            self.l0 = self.l0 / max_val
            
        # 使用幂函数增强低振幅部分（类似 Gamma 矫正，让说话声音更明显）
        self.l0 = np.power(self.l0, 0.6) 
            
        self.chunk_ms = chunk_ms
        self.max_tracks = max_tracks
        self.track_height = height
        self.total_height = max_tracks * height
        self.pps = 0.1
        
        # 1. 瓦片常量
        self.TILE_DURATION_MS = 10000 
        self.tile_cache = {} 
        
        # 2. 金字塔 LOD
        self.l1 = self._downsample(self.l0, 10)
        self.l2 = self._downsample(self.l0, 100)
        
        self.setZValue(-100)
        self.setAcceptHoverEvents(False)
        
        # 3. 视觉配置 - 现代深海蓝主题
        self.color_core = QColor(52, 152, 219, 230)      # 核心颜色 (蓝)
        self.color_glow = QColor(52, 152, 219, 60)       # 边缘发光
        
    def _downsample(self, data, factor):
        if len(data) < factor: return data
        n = len(data) // factor
        reshaped = data[:n*factor].reshape(-1, factor)
        return np.max(reshaped, axis=1)

    def set_pps(self, pps):
        if self.pps == pps: return
        self.pps = pps
        # PPS 改变会导致瓦片尺寸改变，必须清空缓存
        self.tile_cache.clear()
        self.update()

    def paint(self, painter, option, widget):
        if self.l0 is None or len(self.l0) == 0:
            return

        # 获取可见区域
        view_rect = option.exposedRect
        tile_width_px = self.TILE_DURATION_MS * self.pps
        
        start_tile = int(view_rect.left() / tile_width_px)
        end_tile = int(view_rect.right() / tile_width_px) + 1
        
        # 批量绘制可见瓦片
        for idx in range(start_tile, end_tile):
            key = (idx, self.pps)
            if key not in self.tile_cache:
                self.tile_cache[key] = self._render_tile(idx)
            
            pixmap = self.tile_cache[key]
            if pixmap:
                painter.drawPixmap(int(idx * tile_width_px), 0, pixmap)

    def _render_tile(self, tile_idx):
        """渲染单个巨大的全轨道覆盖波形（居中于所有轨道背景）"""
        tile_w = int(self.TILE_DURATION_MS * self.pps)
        if tile_w <= 0: return None
        
        # 必须使用总高度，防止波形被裁剪或因偏离中轴线而消失
        pixmap = QPixmap(tile_w, int(self.total_height))
        pixmap.fill(Qt.GlobalColor.transparent)
        
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        mid_y = self.total_height / 2
        
        # 数据映射
        start_ms = tile_idx * self.TILE_DURATION_MS
        end_ms = (tile_idx + 1) * self.TILE_DURATION_MS
        
        if self.pps < 0.005:   src, step = self.l2, 1000
        elif self.pps < 0.05:  src, step = self.l1, 100
        else:                  src, step = self.l0, 10
            
        start_idx = int(start_ms / (step * self.chunk_ms))
        end_idx = int(end_ms / (step * self.chunk_ms))
        
        # 准备笔刷
        pen_glow = QPen(self.color_glow, 2)
        pen_core = QPen(self.color_core, 1)
        
        # 绘制逻辑：单一巨大的波形，横跨所有轨道
        for i in range(start_idx, min(len(src), end_idx)):
            data_ms = i * step * self.chunk_ms
            local_x = (data_ms - start_ms) * self.pps
            
            # 使用 total_height 的 0.45 倍作为振幅半高
            val = src[i] * (self.total_height * 0.45)
            if val < 1: continue 
            
            # 1. 绘制外层光晕
            p.setPen(pen_glow)
            p.drawLine(int(local_x), int(mid_y - val), int(local_x), int(mid_y + val))
            
            # 2. 绘制内层核心
            p.setPen(pen_core)
            p.drawLine(int(local_x), int(mid_y - val * 0.6), int(local_x), int(mid_y + val * 0.6))
        
        p.end()
        return pixmap

    def boundingRect(self):
        if self.l0 is None: return QRectF()
        total_ms = len(self.l0) * self.chunk_ms
        w = total_ms * self.pps
        # 返回全场景真实高度
        return QRectF(0, 0, w, self.total_height) 
