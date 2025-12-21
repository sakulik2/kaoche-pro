import sys
import time
import numpy as np
import os
import tempfile
import threading
import hashlib

# 将项目根目录添加到 python 路径以导入核心模块
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.append(project_root)

from PyQt6.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsPathItem, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QFileDialog
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QBrush, QColor, QPen, QPolygonF, QPixmap

try:
    from tools.SubStudio.core.audio_processor import AudioProcessor
except ImportError:
    print("无法导入 AudioProcessor")
    AudioProcessor = None

class TempAudioProcessor(AudioProcessor):
    def __init__(self, video_path):
        super().__init__(video_path, sample_rate=2000)

    def _get_cache_path(self, video_path):
        h = hashlib.md5(video_path.encode('utf-8')).hexdigest()
        temp_dir = tempfile.gettempdir()
        return os.path.join(temp_dir, f"substudio_wave_{h}.npy")

class LodWorker(QObject):
    # l0(10ms), l1(100ms), l2(1s), l3(10s), l4(60s)
    finished = pyqtSignal(object, object, object, object, object) 
    
    def process(self, raw_peaks):
        t0 = time.time()
        print("后台开始构建 5级 LOD 金字塔...")
        
        # L0: 10ms (Base)
        l0 = raw_peaks
        
        def reduce_data(source, factor):
            length = len(source) // factor * factor
            if length == 0: return source
            temp = source[:length].reshape(-1, factor, 2)
            return np.column_stack((temp[:,:,0].min(axis=1), temp[:,:,1].max(axis=1))).astype(np.float32)

        # L1: 100ms (10x L0)
        l1 = reduce_data(l0, 10)
        
        # L2: 1s (10x L1)
        l2 = reduce_data(l1, 10)
        
        # L3: 10s (10x L2)
        l3 = reduce_data(l2, 10)
        
        # L4: 60s (6x L3)
        l4 = reduce_data(l3, 6)
            
        print(f"LOD 构建完成，耗时 {time.time()-t0:.3f}秒。Level Sizes: {len(l0)}, {len(l1)}, {len(l2)}, {len(l3)}, {len(l4)}")
        self.finished.emit(l0, l1, l2, l3, l4)

class LodWaveformItem(QGraphicsPathItem):
    def __init__(self, raw_peaks, chunk_ms=10, height=200):
        super().__init__()
        self.chunk_ms = chunk_ms
        self.height = height
        self.pps = 0.1 
        
        self.setBrush(QBrush(QColor(0, 120, 215)))
        self.setPen(QPen(QColor(0, 120, 215), 1))
        
        self.use_lod = True
        self.use_cache = True
        self.is_zooming = False 
        
        self.tile_cache = {} 
        self.TILE_WIDTH = 2048
        
        self.l0 = None
        self.l1 = None
        self.l2 = None
        self.l3 = None
        self.l4 = None

    def set_lod_data(self, l0, l1, l2, l3, l4):
        self.l0, self.l1, self.l2, self.l3, self.l4 = l0, l1, l2, l3, l4
        self.tile_cache.clear()
        self.update()

    def set_pps(self, pps, is_zooming=False):
        if self.pps != pps:
            self.pps = pps
            self.is_zooming = is_zooming
            self.tile_cache.clear()
            self.update()

    def paint(self, painter, option, widget):
        if self.l0 is None: return
        should_cache = self.use_cache and not self.is_zooming
        if should_cache:
            self._paint_cached(painter, option)
        else:
            self._paint_direct(painter, option)

    def _paint_cached(self, painter, option):
        exposed = option.exposedRect
        start_x = exposed.left()
        end_x = exposed.right()
        
        start_tile = int(start_x / self.TILE_WIDTH)
        end_tile = int(end_x / self.TILE_WIDTH) + 1
        
        for tile_idx in range(start_tile, end_tile):
            key = (tile_idx, self.pps, self.use_lod)
            pixmap = self.tile_cache.get(key)
            if not pixmap:
                pixmap = self._render_tile_to_pixmap(tile_idx)
                if len(self.tile_cache) > 150: self.tile_cache.clear()
                self.tile_cache[key] = pixmap
            painter.drawPixmap(tile_idx * self.TILE_WIDTH, 0, pixmap)

    def _render_tile_to_pixmap(self, tile_idx):
        pix = QPixmap(self.TILE_WIDTH, int(self.height))
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setBrush(self.brush())
        p.setPen(self.pen())
        tile_start_x = tile_idx * self.TILE_WIDTH
        p.translate(-tile_start_x, 0)
        simulated_exposed = QRectF(tile_start_x, 0, self.TILE_WIDTH, self.height)
        self._paint_geometry_on_painter(p, simulated_exposed)
        p.end()
        return pix

    def _paint_direct(self, painter, option):
        self._paint_geometry_on_painter(painter, option.exposedRect)

    def _paint_geometry_on_painter(self, painter, exposed_rect):
        start_x = max(0, exposed_rect.left())
        end_x = exposed_rect.right()
        
        # 1. 智能 LOD 选择
        # 目标：确保每像素不要绘制超过 1-2 个数据点，否则就是这性能浪费
        ms_per_pixel = 1.0 / self.pps
        data = self.l0
        step_ms = 10
        
        if self.use_lod:
            if ms_per_pixel > 40000: # 1px > 40s (极览模式)
                data = self.l4 # 60s accuracy
                step_ms = 60000
            elif ms_per_pixel > 8000: # 1px > 8s
                data = self.l3 # 10s accuracy
                step_ms = 10000
            elif ms_per_pixel > 800: # 1px > 0.8s
                data = self.l2 # 1s accuracy
                step_ms = 1000
            elif ms_per_pixel > 80: # 1px > 0.08s
                data = self.l1 # 100ms accuracy
                step_ms = 100
        
        start_idx = int(start_x / self.pps / step_ms)
        end_idx = int(end_x / self.pps / step_ms) + 1
        
        start_idx = max(0, min(start_idx, len(data)-1))
        end_idx = max(0, min(end_idx, len(data)))
        
        if end_idx <= start_idx: return
        
        # [激进优化] 顶点数量限制
        idx_len = end_idx - start_idx
        if section_limit := 10000: # 提升至 10000 以支持 4K/8K 屏
            if idx_len > section_limit:
                 end_idx = start_idx + section_limit
        
        view_data = data[start_idx:end_idx]
        count = len(view_data)
        
        indices = np.arange(start_idx, end_idx, dtype=np.float32)
        xs = indices * step_ms * self.pps
        
        mid_y = self.height / 2
        scale_y = self.height / 2 * 0.95
        
        ys_top = mid_y - (view_data[:, 1] * scale_y)
        ys_bottom = mid_y - (view_data[:, 0] * scale_y)
        
        points = [QPointF(xs[i], ys_top[i]) for i in range(count)]
        points_bot = [QPointF(xs[i], ys_bottom[i]) for i in range(count-1, -1, -1)]
        points.extend(points_bot)
        
        painter.drawPolygon(QPolygonF(points))
        
        # 存储当前精度供 UI 显示
        self.last_step_ms = step_ms

    def boundingRect(self):
        total_ms = len(self.l0) * 10 if self.l0 is not None else 0
        return QRectF(0, 0, total_ms * self.pps, self.height)


class GlWaveformWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PoC v6: 精度验证版 (Precision Checked)")
        self.resize(1200, 500)
        
        main_layout = QVBoxLayout(self)
        
        toolbar = QHBoxLayout()
        self.btn_load = QPushButton("加载视频文件 (Load Video)...")
        self.btn_load.clicked.connect(self._on_load_video)
        toolbar.addWidget(self.btn_load)
        
        toolbar.addSpacing(20)
        
        btn_zoom_out = QPushButton("缩小 (-)")
        btn_zoom_out.clicked.connect(lambda: self._zoom(0.5))
        toolbar.addWidget(btn_zoom_out)

        btn_zoom_in = QPushButton("放大 (+)")
        btn_zoom_in.clicked.connect(lambda: self._zoom(2.0))
        toolbar.addWidget(btn_zoom_in)
        
        main_layout.addLayout(toolbar)
        
        self.info_label = QLabel("就绪。请观察 '精度' 指标。")
        self.info_label.setStyleSheet("font-size: 14px; padding: 5px; background: #333; color: white;")
        main_layout.addWidget(self.info_label)
        
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        
        self.gl_widget = QOpenGLWidget()
        self.view.setViewport(self.gl_widget)
        self.is_gl = True
        
        main_layout.addWidget(self.view)
        
        self.item = LodWaveformItem([], 10, 200)
        self.scene.addItem(self.item)
        
        self.audio_processor = None
        self.pps = 0.1
        self.extract_start_time = 0
        
        self.lod_thread = None
        
        self.frame_count = 0
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self._update_fps)
        self.fps_timer.start(1000)
        self.last_fps = 0
        
        self.zoom_timer = QTimer()
        self.zoom_timer.setSingleShot(True)
        self.zoom_timer.timeout.connect(self._on_zoom_end)
        
        self._update_view()

    def _on_load_video(self):
        file, _ = QFileDialog.getOpenFileName(self, "选择视频", "", "Video Files (*.mp4 *.mkv *.avi *.mov)")
        if not file: return
        
        if not AudioProcessor:
            self.info_label.setText("错误: 找不到 AudioProcessor 类")
            return

        self.info_label.setText(f"正在提取音频: {os.path.basename(file)}...")
        self.btn_load.setEnabled(False) 
        
        if self.audio_processor:
             try: self.audio_processor.terminate(); self.audio_processor.wait()
             except: pass
        
        self.audio_processor = TempAudioProcessor(file)
        self.audio_processor.finished.connect(self._on_audio_ready)
        self.audio_processor.start()
        
        self.extract_start_time = time.time()

    def _on_audio_ready(self, success, data):
        self.btn_load.setEnabled(True)
        elapsed = time.time() - self.extract_start_time
        
        if not success:
            self.info_label.setText(f"提取失败: {data}")
            return
            
        self.info_label.setText(f"提取完成 ({elapsed:.2f}s)。正在后台构建 5 级细节 (LOD0-LOD4)...")
        
        self.lod_worker = LodWorker()
        self.lod_thread = threading.Thread(target=self.lod_worker.process, args=(data,))
        self.lod_worker.finished.connect(self._on_lod_ready)
        self.lod_thread.start()

    def _on_lod_ready(self, l0, l1, l2, l3, l4):
        self.item.set_lod_data(l0, l1, l2, l3, l4)
        self.info_label.setText(f"数据就绪 (L0-L4)。请测试长视频缩放性能。")
        self._update_view()
        self.view.horizontalScrollBar().setValue(0)

    def _zoom(self, factor):
        self.pps = max(0.001, min(20.0, self.pps * factor))
        self.item.set_pps(self.pps, is_zooming=True)
        self.scene.setSceneRect(self.item.boundingRect())
        self._update_info()
        self.frame_count += 1
        self.zoom_timer.start(200)

    def _on_zoom_end(self):
        self.item.is_zooming = False
        self.item.update() 

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_G:
            self.is_gl = not self.is_gl
            self.view.setViewport(QOpenGLWidget() if self.is_gl else QWidget())
        elif key == Qt.Key.Key_C:
            self.item.use_cache = not self.item.use_cache
            self.item.tile_cache.clear()
            self.item.update()
        elif key == Qt.Key.Key_L:
            self.item.use_lod = not self.item.use_lod
            self.item.tile_cache.clear()
            self.item.update()
        self._update_info()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.3 if delta > 0 else 0.77
        self._zoom(factor)

    def _update_view(self):
        self.item.set_pps(self.pps)
        self.scene.setSceneRect(self.item.boundingRect())
        self._update_info()
        self.frame_count += 1
        
    def _update_fps(self):
        self.last_fps = self.frame_count
        self.frame_count = 0
        self._update_info()

    def _update_info(self):
        scale = 1/self.pps if self.pps > 0 else 0
        
        # 获取当前渲染精度
        step_ms = getattr(self.item, 'last_step_ms', 10)
        precision_str = f"{step_ms}ms"
        if step_ms == 10: precision_str += " (原始 Raw)"
        elif step_ms == 60000: precision_str += " (L4)"
        
        txt = self.info_label.text().split("|")[0].strip()
        self.info_label.setText(f"{txt} | 精度: {precision_str} | FPS: {self.last_fps} | PPS: {self.pps:.4f}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = GlWaveformWidget()
    w.show()
    sys.exit(app.exec())
