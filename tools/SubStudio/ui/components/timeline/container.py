import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGraphicsScene, QGraphicsLineItem, QFrame, QTextEdit, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPointF, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPen, QColor

from .ruler import TimelineRuler
from .view import TimelineView
from .item import SubtitleItem, TRACK_HEIGHT
from .playhead import PlayheadItem
from .waveform import WaveformItem
from ....core.audio_processor import AudioProcessor

logger = logging.getLogger(__name__)

class TimelineContainer(QWidget):
    # 信号：当用户在时间轴上手动跳转进度时触发
    request_seek = pyqtSignal(float) # ms
    files_dropped = pyqtSignal(list) # 拖入的文件路径列表

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.pps = 0.1 # Pixels per millisecond
        self.play_time_ms = 0
        self.total_duration_ms = 0
        self.max_tracks = 8 # 默认 8 轨
        
        self.audio_processor = None
        self.waveform_item = None
        
        self.ghost_block_item = None # 幽灵块 (拍键预览)
        
        self.init_ui()
        self._connect_signals()
        self.refresh_all()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # 1. Ruler
        self.ruler = TimelineRuler(self)
        self.layout.addWidget(self.ruler)
        
        # 2. View & Scene
        self.scene = QGraphicsScene()
        # 优化1: BSP Tree 索引加速大量图元查找
        self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)
        
        self.view = TimelineView(self.scene, self)
        # 优化2: 智能视口更新，减少重绘区域
        from PyQt6.QtWidgets import QGraphicsView
        self.view.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        # 优化3: 启用背景缓存 (如果波形也是 Items，这个可能有助于减少背景重绘?)
        # self.view.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground) 
        # (通常视口缓存对动态时间轴有副作用，暂时保持默认)
        
        self.layout.addWidget(self.view)
        
        # 3. 属性编辑器 (内嵌式)
        self.prop_editor = QFrame()
        self.prop_editor.setFixedHeight(90)
        # 精致的暗色渐变处理
        self.prop_editor.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2d2d2d, stop:1 #252525);
                border-top: 1px solid #111;
            }
            QLabel {
                color: #888;
                font-size: 11px;
                font-weight: bold;
                text-transform: uppercase;
            }
        """)
        prop_layout = QVBoxLayout(self.prop_editor)
        prop_layout.setContentsMargins(15, 8, 15, 8)
        prop_layout.setSpacing(5)
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("字幕文本 (Subtitle Text)"))
        header_layout.addStretch()
        prop_layout.addLayout(header_layout)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("选择字幕以开始编辑内容...")
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #121212;
                color: #ffffff;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 6px;
                font-family: 'Inter UI', 'Segoe UI', sans-serif;
                font-size: 13px;
                line-height: 1.4;
            }
            QTextEdit:focus {
                border: 1px solid #3498db;
            }
        """)
        self.text_edit.textChanged.connect(self._on_text_edited)
        prop_layout.addWidget(self.text_edit)
        
        self.layout.addWidget(self.prop_editor)
        self.prop_editor.setVisible(False)
        
        # 4. Playhead
        self.playhead = PlayheadItem(self.max_tracks)
        self.scene.addItem(self.playhead)
        
        # 5. Background Tracks
        self._draw_background_tracks()

    def update_ghost_block(self, start_ms, end_ms):
        """实时绘制幽灵块 (Recording Preview)"""
        from PyQt6.QtWidgets import QGraphicsRectItem
        from PyQt6.QtGui import QColor, QPen, QBrush
        
        if not self.ghost_block_item:
            self.ghost_block_item = QGraphicsRectItem()
            # 样式：半透明红色，强提醒
            self.ghost_block_item.setBrush(QBrush(QColor(231, 76, 60, 150)))
            self.ghost_block_item.setPen(QPen(QColor(255, 255, 255, 200), 1))
            self.ghost_block_item.setZValue(500) # 置于顶层
            self.scene.addItem(self.ghost_block_item)
            
        x_start = start_ms * self.pps
        width = max(10, (end_ms - start_ms) * self.pps)
        # 固定在轨道 0? 或者根据 active group 调整? 暂时固定轨道0
        y = 0 
        h = TRACK_HEIGHT
        
        self.ghost_block_item.setRect(x_start, y, width, h)
        
    def remove_ghost_block(self):
        """清除幽灵块"""
        if self.ghost_block_item:
            self.scene.removeItem(self.ghost_block_item)
            self.ghost_block_item = None
            
    def _connect_signals(self):
        # 监听 Store 变化
        self.store.dataChanged.connect(self.refresh_all)
        self.store.eventsChanged.connect(self._on_events_changed)
        self.store.selectionChanged.connect(self._on_store_selection_changed)
        
        # 监听场景选中变化 (UI -> Store)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        
        # 监听滚动条，同步 Ruler 偏移
        self.view.horizontalScrollBar().valueChanged.connect(self.ruler.set_offset)
        
        # 初始化滚动动画
        self.scroll_anim = QPropertyAnimation(self.view.horizontalScrollBar(), b"value")
        self.scroll_anim.setDuration(400) # 400ms 平滑切换
        self.scroll_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _on_scene_selection_changed(self):
        """当图形场景中的选中项变化时，同步给 Store"""
        if getattr(self, "_is_syncing_selection", False):
            return
            
        selected_items = self.scene.selectedItems()
        indices = [item.event_idx for item in selected_items if isinstance(item, SubtitleItem)]
        
        self._is_syncing_selection = True
        self.store.set_selection(indices)
        self._is_syncing_selection = False

    def _on_store_selection_changed(self, indices):
        """当外部（如列表）改变选中项时，同步高亮场景中的 Chunk"""
        if getattr(self, "_is_syncing_selection", False):
            return
            
        self._is_syncing_selection = True
        self.scene.blockSignals(True)
        # 清除当前场景选中
        self.scene.clearSelection()
        # 匹配 event_idx 并选中
        selected_item = None
        for item in self.scene.items():
            if isinstance(item, SubtitleItem) and item.event_idx in indices:
                item.setSelected(True)
                selected_item = item
        
        # 更新内嵌编辑器状态
        if len(indices) == 1 and selected_item:
            self.prop_editor.setVisible(True)
            self.text_edit.blockSignals(True)
            self.text_edit.setPlainText(selected_item.text)
            self.text_edit.blockSignals(False)
            self._current_edit_idx = indices[0]
        else:
            self.prop_editor.setVisible(False)
            self._current_edit_idx = None
            
        self.scene.blockSignals(False)
        self._is_syncing_selection = False

    def _on_text_edited(self):
        """内嵌编辑器文本变化，写回 Store"""
        if hasattr(self, "_current_edit_idx") and self._current_edit_idx is not None:
            new_text = self.text_edit.toPlainText()
            self.store.update_event(self._current_edit_idx, text=new_text)

    def _draw_background_tracks(self):
        # 绘制背景线
        for i in range(self.max_tracks + 1):
            y = i * TRACK_HEIGHT
            line = self.scene.addLine(0, y, 1000000, y, QPen(QColor("#1A1A1A"), 1))
            line.setZValue(-1)

    def set_duration(self, ms):
        """设置总时长并更新画布范围"""
        self.total_duration_ms = ms
        self.update_scene_rect()
        if self.waveform_item:
            self.waveform_item.update() # 重新绘制

    def load_audio(self, video_path):
        """加载视频音频以生成波形"""
        if self.audio_processor and self.audio_processor.isRunning():
            self.audio_processor.cancel()
            self.audio_processor.wait()
            
        if self.waveform_item:
            self.scene.removeItem(self.waveform_item)
            self.waveform_item = None
            
        logger.info(f"Timeline: Loading audio from {video_path}")
        self.audio_processor = AudioProcessor(video_path)
        self.audio_processor.finished.connect(self._on_audio_extracted)
        self.audio_processor.start()

    def _on_audio_extracted(self, success, data):
        if not success:
            logger.warning(f"Audio extraction failed: {data}")
            return
            
        logger.info(f"Audio waveform data ready. Points: {len(data)}")
        # 创建波形图层
        # 使用全轨道展示作为背景
        self.waveform_item = WaveformItem(data, chunk_ms=10, height=TRACK_HEIGHT, max_tracks=self.max_tracks)
        self.waveform_item.set_pps(self.pps)
        self.scene.addItem(self.waveform_item)
        
        # 移到最底层
        self.waveform_item.setZValue(-100)
        
        # 确保播放头在最上层
        self.playhead.setZValue(100) 

    def update_scene_rect(self):
        w = max(self.total_duration_ms * self.pps, self.view.width())
        self.scene.setSceneRect(0, 0, w + 2000, self.max_tracks * TRACK_HEIGHT)
        # 更新背景线长度
        for item in self.scene.items():
            if isinstance(item, QGraphicsLineItem) and item.zValue() == -1:
                item.setLine(0, item.line().y1(), w + 2000, item.line().y1())
        self.update_playhead_pos()

    def get_current_time(self):
        return self.play_time_ms

    def set_current_time(self, ms):
        """外部调用（如播放器时间变化）同步播放头"""
        self.play_time_ms = ms
        self.update_playhead_pos()
        # 自动滚动逻辑：基于页面的“瞬间/平滑”翻页
        self._check_auto_scroll()

    def seek_to_x(self, x):
        """内部调用（点击跳转）"""
        if self.pps <= 0: return
        target_ms = int(max(0, min(x / self.pps, self.total_duration_ms or 1000000)))
        self.play_time_ms = target_ms
        self.request_seek.emit(target_ms)
        self.update_playhead_pos()
        self.ruler.update()

    def update_playhead_pos(self):
        x = self.play_time_ms * self.pps
        self.playhead.set_x(x)
        self.ruler.update()

    def _check_auto_scroll(self):
        """
        分页式滚动逻辑：
        当播放头超出当前视口的 90% 时，向右平滑飞跃 80% 的视口宽度。
        """
        if self.scroll_anim.state() == QPropertyAnimation.State.Running:
            return

        scrollbar = self.view.horizontalScrollBar()
        viewport_w = self.view.viewport().width()
        x = self.play_time_ms * self.pps
        
        current_scroll = scrollbar.value()
        
        # 1. 向右翻页检测
        if x > current_scroll + viewport_w * 0.9:
            target = int(current_scroll + viewport_w * 0.8)
            self.scroll_anim.setStartValue(current_scroll)
            self.scroll_anim.setEndValue(target)
            self.scroll_anim.start()
            
        # 2. 向左翻页检测 (通常是点击 Seek 触发，但此处也做兜底)
        elif x < current_scroll:
            target = int(max(0, x - viewport_w * 0.2))
            self.scroll_anim.setStartValue(current_scroll)
            self.scroll_anim.setEndValue(target)
            self.scroll_anim.start()

    def _on_events_changed(self, indices, reason):
        """局部或按需重绘字幕块，提升性能"""
        if reason == "delete" or reason == "add":
            # 结构变化，全量刷新
            self.refresh_all()
            return

        # 仅刷新受影响的项
        affected_count = 0
        for item in self.scene.items():
            if isinstance(item, SubtitleItem) and item.event_idx in indices:
                item.update_from_store()
                item.update_rect()
                item.update()
                affected_count += 1
        
        # 如果受影响项从未出现过（比如索引偏移），则刷新全部
        if affected_count == 0:
            self.refresh_all()

    def refresh_all(self):
        """全量刷新所有字幕块"""
        # 清理旧块
        for item in list(self.scene.items()):
            if isinstance(item, SubtitleItem):
                self.scene.removeItem(item)
        
        # 创建新块
        events = self.store.get_all_events()
        for i, event in enumerate(events):
            item = SubtitleItem(i, self.store, self.view)
            self.scene.addItem(item)
            
        self.update_scene_rect()

    def _on_selection_changed(self, indices):
        # 同步选中状态
        for item in self.scene.items():
            if isinstance(item, SubtitleItem):
                item.setSelected(item.event_idx in indices)

    def wheelEvent(self, event):
        """CTRL + 滚轮缩放"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            
            # 缩放中心锚点
            mouse_pos = self.view.viewport().mapFromGlobal(event.globalPosition().toPoint())
            scene_pos = self.view.mapToScene(mouse_pos)
            anchor_time = scene_pos.x() / self.pps if self.pps > 0 else 0
            
            if delta > 0: self.pps *= 1.2
            else: self.pps /= 1.2
            self.pps = max(0.0001, min(self.pps, 10.0))
            
            # 同步更新波形 PPS
            if self.waveform_item:
                self.waveform_item.set_pps(self.pps)
            
            # 更新显示
            self.update_scene_rect()
            for item in self.scene.items():
                if isinstance(item, SubtitleItem):
                    item.update_rect()
            self.ruler.set_pps(self.pps)
            
            # 补偿偏移
            new_scroll_x = (anchor_time * self.pps) - mouse_pos.x()
            self.view.horizontalScrollBar().setValue(int(new_scroll_x))
            event.accept()
        else:
            super().wheelEvent(event)
