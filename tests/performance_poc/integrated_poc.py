import sys
import os
import time
import numpy as np
import pysubs2
import logging

# --- 1. 环境准备：将项目根目录加入模块搜索路径 ---
# 这样可以直接 import tools.SubStudio 相关组件
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QFileDialog, QLabel, QFrame)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF, QPoint
from PyQt6.QtGui import QColor, QPalette

# --- 2. 引入真实项目的核心组件 ---
try:
    from tools.SubStudio.core.subtitle_store import SubtitleStore
    from tools.SubStudio.ui.components.timeline.container import TimelineContainer
    from tools.SubStudio.ui.components.timeline.waveform import WaveformItem
    from tools.SubStudio.ui.components.timeline.item import TRACK_HEIGHT
    from tools.SubStudio.ui.overlay_window import OverlayWindow
    logger_name = "RealCoreIntegration"
except ImportError as e:
    print(f"Error: 无法加载主项目组件，请检查路径。详情: {e}")
    sys.exit(1)

# --- 3. 引入 VLC 渲染引擎 ---
try:
    import vlc
except ImportError:
    print("Error: python-vlc not found.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FinalIntegrationPoc")

# ==========================================
# 5. PLAYER: 支持 Soft-Sync 的 VLC 播放器
# ==========================================
class VlcPlayerFrame(QFrame):
    def __init__(self, store):
        super().__init__()
        self.setStyleSheet("background: black; border-bottom: 2px solid #111;")
        self.instance = vlc.Instance("--avcodec-hw=none --quiet")
        self.player = self.instance.media_player_new()
        if sys.platform == "win32": self.player.set_hwnd(self.winId())
        
        # 使用真实的生产级 OverlayWindow
        self.overlay = OverlayWindow(store)
        self.overlay.show()

    def moveEvent(self, e):
        super().moveEvent(e)
        self._sync_overlay()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._sync_overlay()
        
    def _sync_overlay(self):
        if not hasattr(self, "overlay"): return
        
        # 显隐同步：如果主窗口最小化或播放器不可见，隐藏 Overlay
        main_win = self.window()
        is_visible = self.isVisible() and main_win and not main_win.isMinimized()
        self.overlay.setVisible(is_visible)
        if not is_visible: return

        # 使用 QPoint(0,0) 获取整型屏幕坐标
        global_pos = self.mapToGlobal(QPoint(0, 0))
        raw_rect = self.rect()
        
        if self.overlay.geometry().topLeft() != global_pos or self.overlay.size() != raw_rect.size():
            print(f"[DEBUG] Overlay Sync: PlayerGlobal={global_pos}, Size={raw_rect.size()}")
            self.overlay.setGeometry(global_pos.x(), global_pos.y(), 
                                     raw_rect.width(), raw_rect.height())
            self.overlay.raise_() # 确保在最顶层

    def load(self, path):
        self.player.set_media(self.instance.media_new(path))
        self.player.play()
    
    def seek(self, ms):
        """跳转到指定毫秒"""
        self.player.set_time(int(ms))

    def get_time(self): return self.player.get_time()
    def get_rate(self): return self.player.get_rate()
    def get_length(self): return self.player.get_length()

    def toggle_pause(self):
        """切换播放状态"""
        if self.player.is_playing():
            self.player.pause()
        else:
            self.player.play()
        return self.player.is_playing()

    def set_pause(self, paused: bool):
        """强制设定或取消暂停"""
        if paused:
            self.player.set_pause(1)
        else:
            self.player.set_pause(0)

    def closeEvent(self, e):
        self.overlay.close()
        super().closeEvent(e)

# ==========================================
# 5. MAIN WINDOW: 最终集成形态
# ==========================================
class ProductionArchitecturePoc(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SubStudio 生产级架构最终集成 PoC (v7.0 Stable)")
        self.resize(1200, 900)
        
        # 数据模型 (使用真实的 SubtitleStore)
        self.store = SubtitleStore()
        self.current_time_ms = 0.0
        self.is_playing = False
        
        self._init_ui()
        self._setup_animation()

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 视频区域
        self.player = VlcPlayerFrame(self.store)
        self.player.setMinimumHeight(450)
        layout.addWidget(self.player, 3)

        # 2. Middle: Real Timeline Container
        self.timeline = TimelineContainer(self.store)
        self.timeline.request_seek.connect(self._on_timeline_seek) # 连接跳转信号
        # 优化：智能更新（修复初始渲染不显示波形的问题）
        from PyQt6.QtWidgets import QGraphicsView
        self.timeline.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        layout.addWidget(self.timeline, 2)
        
        # 3. 拦截顶层窗口移动事件 (辅助同步 Overlay)
        self.installEventFilter(self)

        # 底部状态栏
        self.status = QFrame()
        self.status.setFixedHeight(40)
        self.status.setStyleSheet("background: #252525; border-top: 1px solid #111;")
        status_layout = QHBoxLayout(self.status)
        
        btn_load = QPushButton("  📂 加载视频 (Load Media)  ")
        btn_load.clicked.connect(self._select_file)
        status_layout.addWidget(btn_load)
        
        self.lbl_info = QLabel("准备就绪")
        status_layout.addWidget(self.lbl_info)
        status_layout.addStretch()
        
        layout.addWidget(self.status)

    def eventFilter(self, obj, event):
        # 如果主窗口移动，强制触发 Overlay 同步
        if event.type() in [event.Type.Move, event.Type.Resize]:
            self.player._sync_overlay()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.is_playing = not self.is_playing
            # 同步真正的 VLC 播放/暂停
            self.player.set_pause(not self.is_playing)
            self.player.overlay.set_playing_state(self.is_playing)
            self.lbl_info.setText(f"状态: {'播放中' if self.is_playing else '暂停'}")
            event.accept()
        else:
            super().keyPressEvent(event)

    def _setup_animation(self):
        # 60FPS 渲染循环
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_frame_sync)
        self.timer.start(16)

    def _on_frame_sync(self):
        if self.is_playing:
            # 1. 从硬件获取准确时钟
            vlc_clock = self.player.get_time()
            if vlc_clock < 0: return # 等待 VLC 初始化
            
            # --- 平滑算法优化 ---
            if not hasattr(self, "_last_vlc_clock") or abs(vlc_clock - self._last_vlc_clock) > 500:
                # 初始启动或大跨度跳转时，强制对齐，消除瞬移
                self.current_time_ms = float(vlc_clock)
                self._last_vlc_clock = vlc_clock
            else:
                # 正常步进
                vlc_rate = self.player.get_rate()
                rate = vlc_rate if vlc_rate > 0 else 1.0
                self.current_time_ms += 16 * rate
                
                # 柔性同步校准
                drift = vlc_clock - self.current_time_ms
                if abs(drift) > 30:
                    self.current_time_ms += drift * 0.2 # 提高校准权重以解决卡顿
                self._last_vlc_clock = vlc_clock
                
            # 3. 同步到时间轴和 Overlay
            self.timeline.set_current_time(int(self.current_time_ms))
            self.player.overlay.set_current_time(int(self.current_time_ms))
            
            # 4. 每帧微调 Overlay 位置
            self.player._sync_overlay()

    def _on_timeline_seek(self, ms):
        """处理时间轴拖拽跳转"""
        self.current_time_ms = float(ms)
        self.player.seek(ms)
        self.player.overlay.set_current_time(int(ms))
        if not self.is_playing:
            self.player.overlay.update() # 暂停时手动刷新

    def _update_overlay(self):
        # 已经在 _on_frame_sync 中通过 set_current_time 处理了
        pass

    def _select_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择视频/音频", "", "Media (*.mp4 *.mkv *.mp3 *.wav)")
        if f:
            self.player.load(f) # 恢复加载
            self.is_playing = True
            
            # 获取并同步总时长
            def update_duration():
                length_ms = self.player.get_length()
                if length_ms > 0:
                    self.timeline.total_duration_ms = length_ms
                    logger.info(f"Updated total duration: {length_ms}ms")
            QTimer.singleShot(500, update_duration) # VLC 加载后异步获取时长
            
            # --- 核心修复：清理旧层 ---
            if hasattr(self.timeline, "waveform_item") and self.timeline.waveform_item:
                self.timeline.scene.removeItem(self.timeline.waveform_item)
            
            # 彻底清理所有重复的 Playhead
            for item in self.timeline.scene.items():
                from tools.SubStudio.ui.components.timeline.playhead import PlayheadItem
                if isinstance(item, PlayheadItem) and item != self.timeline.playhead:
                    self.timeline.scene.removeItem(item)
            
            # 注入模拟波形数据 (分块瓦片渲染)
            mock_peaks = np.random.uniform(0.1, 0.9, 120000)
            wv = WaveformItem(mock_peaks, height=TRACK_HEIGHT * 8) 
            wv.set_pps(self.timeline.pps)
            wv.setZValue(-1000) 
            self.timeline.scene.addItem(wv)
            self.timeline.waveform_item = wv 
            
            # 注入模拟字幕到真实的 Store
            self.store.subs.events = []
            self.store.subs.info["PlayResX"] = 1280
            self.store.subs.info["PlayResY"] = 720
            for i in range(20):
                e = pysubs2.SSAEvent(start=i*3000, end=i*3000+2000, text=f"专业交互验证 #{i+1}")
                e.effect = str(i % 3)
                self.store.subs.events.append(e)
            
            self.player.overlay._rebuild_search_index()
            self.player.overlay.set_playing_state(True)
            self.player.overlay.update()
            
            # 确保播放头在最顶层
            if hasattr(self.timeline, "playhead"):
                self.timeline.playhead.setZValue(9999)
            
            # 通知 UI 刷新
            self.timeline.refresh_all()
            self.timeline.view.viewport().update()
            self.lbl_info.setText(f"已加载: {os.path.basename(f)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # 全局暗色调
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    app.setPalette(palette)
    
    poc = ProductionArchitecturePoc()
    poc.show()
    sys.exit(app.exec())
