import logging
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QMenuBar, QFileDialog, QSplitter, QMessageBox, QProgressDialog
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QSettings, QTimer

logger = logging.getLogger(__name__)
from ..core.subtitle_store import SubtitleStore
from ..core.overlay_sync import OverlaySyncController
from ..core.model_manager import ModelManager 
from .overlay_window import OverlayWindow
from ui.components.video_player import VideoPlayerWidget
from ..core.rapid_creator import RapidCreationController

LIGHT_THEME = """
    QWidget {
        background-color: #F3F4F6;
        color: #111827;
        font-family: 'Inter', 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
    }
    QMenuBar {
        background-color: #FFFFFF;
        border-bottom: 1px solid #D1D5DB;
        padding: 2px;
        color: #111827;
    }
    QMenuBar::item:selected {
        background-color: #E5E7EB;
    }
    QSplitter::handle {
        background-color: #D1D5DB;
    }
    QSplitter::handle:horizontal {
        width: 1px;
    }
    QSplitter::handle:vertical {
        height: 1px;
    }
    QTabWidget::pane {
        border-top: 1px solid #D1D5DB;
        background-color: #FFFFFF;
    }
    QTabBar::tab {
        background: #F3F4F6;
        border: 1px solid #D1D5DB;
        padding: 6px 15px;
        margin-right: 1px;
        font-size: 11px;
        color: #4B5563;
        text-transform: uppercase;
    }
    QTabBar::tab:selected {
        background: #FFFFFF;
        border-bottom: 2px solid #3B82F6;
        color: #111827;
        font-weight: bold;
    }
    QTabBar::tab:hover:!selected {
        background: #E5E7EB;
    }
    QScrollArea, QListWidget, QTableWidget {
        border: none;
        background-color: #FFFFFF;
        color: #111827;
    }
    QHeaderView::section {
        background-color: #F9FAFB;
        border: 1px solid #D1D5DB;
        padding: 4px;
        color: #374151;
    }
"""

DARK_THEME = """
    QWidget {
        background-color: #1E1E1E;
        color: #D4D4D4;
        font-family: 'Inter', 'Segoe UI', 'Microsoft YaHei UI', sans-serif;
    }
    QMenuBar {
        background-color: #2D2D2D;
        border-bottom: 1px solid #333;
        padding: 2px;
    }
    QMenuBar::item:selected {
        background-color: #3E3E42;
    }
    QSplitter::handle {
        background-color: #111;
    }
    QSplitter::handle:horizontal {
        width: 2px;
    }
    QSplitter::handle:vertical {
        height: 2px;
    }
    QTabWidget::pane {
        border-top: 1px solid #333;
        background-color: #1E1E1E;
    }
    QTabBar::tab {
        background: #2D2D2D;
        border: 1px solid #1A1A1A;
        padding: 6px 15px;
        margin-right: 1px;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    QTabBar::tab:selected {
        background: #1E1E1E;
        border-bottom: 2px solid #3498DB;
        color: #FFFFFF;
    }
    QTabBar::tab:hover:!selected {
        background: #3E3E42;
    }
    QScrollArea, QListWidget, QTableWidget {
        border: none;
        background-color: #1E1E1E;
    }
"""

class SubStudioMainView(QWidget):
    def __init__(self, hub, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.setAcceptDrops(True) # 开启拖拽支持
        
        # 1. 核心数据层
        self.store = SubtitleStore()
        
        # 2. AI 模型管理 & 推理引擎
        self.model_manager = ModelManager()
        self._init_model_signals()
        
        from ..core.whisper_engine import WhisperEngine
        self.engine = WhisperEngine(self.model_manager)
        self._init_engine_signals()
        
        # 3. UI 初始化
        self.settings = QSettings("KaochePro", "SubStudio")
        self.init_ui()
        
        # 3.1 听音拍键控制器
        self.rapid_controller = RapidCreationController(self.store)
        self.rapid_controller.recording_progress.connect(self.timeline.update_ghost_block)
        
        # 加载持久化的布局模式
        saved_mode = self.settings.value("layout_mode", "timeline")
        self.apply_layout(saved_mode)
        
        # 4. 视频/Overlay 集成
        self.init_overlay_system()
        
        # 5. 恢复布局状态 (Splitter 记忆)
        self._restore_layout_state()
        
        # 6. 核心播控同步 (软件同步机制)
        self.is_playing = False
        self.current_time_ms = 0.0
        self._setup_playback_sync()

    def _setup_playback_sync(self):
        """设置高性能播控同步时钟 (60FPS)"""
        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(self._on_frame_sync)
        self.sync_timer.start(16) # 16ms = 60FPS
        
        # 状态联动
        self.player.playback_started.connect(self._on_playback_started)
        self.player.playback_paused.connect(self._on_playback_paused)
        self.player.playback_stopped.connect(self._on_playback_stopped)

    def _on_playback_started(self):
        self.is_playing = True
        self.overlay.set_playing_state(True)

    def _on_playback_paused(self):
        self.is_playing = False
        self.overlay.set_playing_state(False)

    def _on_playback_stopped(self):
        self.is_playing = False
        self.overlay.set_playing_state(False)

    def _on_frame_sync(self):
        """核心 Soft-Sync 阻尼同步算法"""
        if self.is_playing:
            # 1. 从硬件获取准确时钟
            hw_clock = self.player.get_current_time()
            if hw_clock < 0: return

            # --- 平滑算法 ---
            if not hasattr(self, "_last_hw_clock") or abs(hw_clock - self._last_hw_clock) > 500:
                # 初始启动或跳变
                self.current_time_ms = float(hw_clock)
                self._last_hw_clock = hw_clock
            else:
                # 正常步进 + 阻尼校准
                rate = self.player.get_rate()
                self.current_time_ms += 16 * rate
                
                drift = hw_clock - self.current_time_ms
                if abs(drift) > 30:
                    self.current_time_ms += drift * 0.2
                self._last_hw_clock = hw_clock
            
            # 2. 推送至时间轴与覆盖层
            self.timeline.set_current_time(int(self.current_time_ms))
            self.overlay.set_current_time(int(self.current_time_ms))
            
            # 3. 辅助空间同步 (针对窗口缩放/移动)
            if hasattr(self, "sync_controller"):
                self.sync_controller.sync_now()

    def closeEvent(self, event):
        """关闭时保存布局状态"""
        self._save_layout_state()
        super().closeEvent(event)

    def _save_layout_state(self):
        self.settings.setValue("v_splitter_state", self.v_splitter.saveState())
        self.settings.setValue("top_h_splitter_state", self.top_h_splitter.saveState())
        logger.info("SubStudio: Layout state saved.")

    def _restore_layout_state(self):
        v_state = self.settings.value("v_splitter_state")
        h_state = self.settings.value("top_h_splitter_state")
        if v_state:
            self.v_splitter.restoreState(v_state)
        if h_state:
            self.top_h_splitter.restoreState(h_state)
        logger.info("SubStudio: Layout state restored.")
        
    def _init_engine_signals(self):
        """初始化推理引擎信号"""
        self.engine.task_progress.connect(self._on_transcribe_progress)
        self.engine.task_finished.connect(self._on_transcribe_finished)

    def _on_transcribe_progress(self, msg, percent):
        if not hasattr(self, '_trans_dialog') or self._trans_dialog is None:
            self._trans_dialog = QProgressDialog("正在初始化 AI 引擎...", "取消", 0, 100, self)
            self._trans_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self._trans_dialog.setMinimumDuration(0)
            self._trans_dialog.canceled.connect(self.engine.cancel)
            self._trans_dialog.show()
            
        if msg:
            self._trans_dialog.setLabelText(msg)
        if percent >= 0:
            self._trans_dialog.setValue(percent)

    def _on_transcribe_finished(self, success, result):
        if hasattr(self, '_trans_dialog') and self._trans_dialog:
            self._trans_dialog.close()
            self._trans_dialog = None
            
        if success:
            # 结果结构: [{start, end, text}, ...]
            # Populate Store
            count = len(result)
            self.store.subs.events.clear() # 清空旧字幕
            
            from pysubs2 import SSAEvent
            for seg in result:
                start_ms = int(seg['start'] * 1000)
                end_ms = int(seg['end'] * 1000)
                text = seg['text'].strip()
                self.store.subs.events.append(SSAEvent(start=start_ms, end=end_ms, text=text))
                
            self.store._mark_dirty()
            self.store.dataChanged.emit()
            
            QMessageBox.information(self, "生成完成", f"已生成 {count} 条字幕。")
        else:
            if result == "Task already running":
                return
            QMessageBox.critical(self, "生成失败", f"错误信息：\n{result}")

    def _open_settings(self):
        """打开全局设置对话框"""
        from .dialogs.settings_dialog import SubStudioSettingsDialog
        dialog = SubStudioSettingsDialog(self.model_manager, self)
        dialog.exec()

    def _start_transcription(self):
        """启动字幕生成"""
        # 1. 检查视频
        video_path = self.player.current_video
        if not video_path:
            QMessageBox.warning(self, "错误", "请先打开一个视频文件。")
            return
            
        # 2. 检查模型
        if not self.model_manager.get_model_path():
            QMessageBox.warning(self, "错误", "未找到可用的 AI 模型。\n请前往 [文件 -> 设置 -> AI 引擎] 下载或选择模型。")
            self._open_settings()
            return
            
        # 3. 提取语言设置与自定义提示词
        lang = self.settings.value("transcription_lang", None)
        prompt = self.settings.value("transcription_prompt", "")
        
        # 4. 启动
        success, msg = self.engine.start_transcription(video_path, language=lang, initial_prompt=prompt)
        if not success:
            QMessageBox.warning(self, "错误", f"无法启动: {msg}")

    def _init_menubar(self):
        """初始化菜单栏"""
        menubar = QMenuBar(self)
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        action_open_vid = QAction("打开视频...", self)
        action_open_vid.triggered.connect(self.action_open_video)
        file_menu.addAction(action_open_vid)
        
        action_open_sub = QAction("打开字幕...", self)
        action_open_sub.triggered.connect(self.action_open_subtitle)
        file_menu.addAction(action_open_sub)
        
        file_menu.addSeparator()
        
        action_save = QAction("保存", self)
        action_save.setShortcut("Ctrl+S")
        action_save.triggered.connect(self.action_save_subtitle)
        file_menu.addAction(action_save)
        
        action_save_as = QAction("另存为...", self)
        action_save_as.setShortcut("Ctrl+Shift+S")
        action_save_as.triggered.connect(self.action_save_subtitle_as)
        file_menu.addAction(action_save_as)
        
        file_menu.addSeparator()
        
        # 设置菜单项
        action_settings = QAction("设置...", self)
        action_settings.triggered.connect(self._open_settings)
        file_menu.addAction(action_settings)
        
        # 视图菜单 (View)
        view_menu = menubar.addMenu("视图")
        
        from PyQt6.QtGui import QActionGroup
        layout_group = QActionGroup(self)
        
        self.action_timeline = QAction("时间轴模式", self)
        self.action_timeline.setCheckable(True)
        self.action_timeline.triggered.connect(lambda: self.apply_layout("timeline"))
        layout_group.addAction(self.action_timeline)
        view_menu.addAction(self.action_timeline)
        
        self.action_classic = QAction("经典模式", self)
        self.action_classic.setCheckable(True)
        self.action_classic.triggered.connect(lambda: self.apply_layout("classic"))
        layout_group.addAction(self.action_classic)
        view_menu.addAction(self.action_classic)
        
        view_menu.addSeparator()
        
        # 主题切换
        self.action_dark_mode = QAction("深色模式", self)
        self.action_dark_mode.setCheckable(True)
        self.action_dark_mode.triggered.connect(self.toggle_theme)
        view_menu.addAction(self.action_dark_mode)
        
        # AI 生成菜单 (Tools)
        tools_menu = menubar.addMenu("工具")
        action_gen = QAction("✨ AI 生成字幕", self)
        action_gen.triggered.connect(self._start_transcription)
        tools_menu.addAction(action_gen)
        
        self.main_layout.addWidget(menubar)
        
    def init_ui(self):
        # 主布局改为垂直，以便放置顶部的菜单栏
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # A. 菜单栏
        self._init_menubar()
        
        # 状态栏
        from PyQt6.QtWidgets import QStatusBar
        self.setStatusBar(QStatusBar(self))
        
        # 应用初始主题
        current_theme = self.settings.value("theme", "light")
        self.apply_theme(current_theme)
        
        # 核心工作区
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 容器 B1: 上部工作区 (水平 Splitter) - 用于 Timeline 模式
        self.top_h_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 1. 播放器容器
        self.player_container = QWidget()
        player_layout = QVBoxLayout(self.player_container)
        player_layout.setContentsMargins(0, 0, 0, 0)
        self.player = VideoPlayerWidget()
        player_layout.addWidget(self.player)
        
        # 2. 侧边栏/底部 Tab
        from .components.style_editor import StyleEditorWidget
        from .components.group_editor import GroupEditorWidget
        from .components.subtitle_list import SubtitleListWidget
        from PyQt6.QtWidgets import QTabWidget
        
        self.tabs = QTabWidget()
        self.sub_list = SubtitleListWidget(self.store)
        self.sub_list.request_seek.connect(self.player.seek_to_time)
        self.tabs.addTab(self.sub_list, "列表")
        
        self.style_editor = StyleEditorWidget(self.store)
        self.tabs.addTab(self.style_editor, "样式")
        
        self.group_editor = GroupEditorWidget(self.store)
        self.tabs.addTab(self.group_editor, "分组")
        
        # 3. 时间轴
        from .components.timeline.container import TimelineContainer
        self.timeline = TimelineContainer(self.store)
        self.timeline.files_dropped.connect(self._on_files_dropped)
        
        # 将工作区加入主布局
        self.main_layout.addWidget(self.v_splitter)

    def apply_layout(self, mode="timeline"):
        """
        动态切换 UI 布局
        mode: "classic" | "timeline"
        """
        logger.info(f"切换布局模式至: {mode}")
        self.settings.setValue("layout_mode", mode)
        
        # 更新菜单状态
        if mode == "timeline":
            self.action_timeline.setChecked(True)
        else:
            self.action_classic.setChecked(True)
        
        # 清空外层 Splitter 的当前内容（断开连接，不删除对象）
        # 直接按模式重新添加组件
        
        if mode == "classic":
            # 经典模式：上播放器，下 Tabs
            self.timeline.hide()
            self.top_h_splitter.hide()
            
            # 确保 Tabs 中包含列表
            if self.tabs.indexOf(self.sub_list) == -1:
                self.tabs.insertTab(0, self.sub_list, "列表")
            
            # 手动调整层级
            self.v_splitter.addWidget(self.player_container)
            self.v_splitter.addWidget(self.tabs)
            
            self.v_splitter.setStretchFactor(0, 3)
            self.v_splitter.setStretchFactor(1, 7)
            
        else:
            # 时间轴模式：上(播放器+侧边栏)，下时间轴
            self.timeline.show()
            self.top_h_splitter.show()
            
            # 移除侧边栏中的列表
            idx = self.tabs.indexOf(self.sub_list)
            if idx != -1:
                self.tabs.removeTab(idx)
            
            # 将播放器和 Tabs 放入水平 Splitter
            self.top_h_splitter.addWidget(self.player_container)
            self.top_h_splitter.addWidget(self.tabs)
            # 极大化播放器占比：85% 播放器, 15% 侧边栏
            self.top_h_splitter.setStretchFactor(0, 85)
            self.top_h_splitter.setStretchFactor(1, 15)
            
            # 将组合放入垂直 Splitter
            self.v_splitter.addWidget(self.top_h_splitter)
            self.v_splitter.addWidget(self.timeline)
            
            # 垂直比例：70% 上部(播放器+侧边), 30% 下部(时间轴)
            self.v_splitter.setStretchFactor(0, 7)
            self.v_splitter.setStretchFactor(1, 3)

    def apply_theme(self, theme="light"):
        """切换深色/浅色主题"""
        if theme == "dark":
            self.setStyleSheet(DARK_THEME)
            self.action_dark_mode.setChecked(True)
        else:
            self.setStyleSheet(LIGHT_THEME)
            self.action_dark_mode.setChecked(False)
        self.settings.setValue("theme", theme)

    def toggle_theme(self, checked):
        theme = "dark" if checked else "light"
        self.apply_theme(theme)

    def closeEvent(self, event):
        """主窗口关闭清理"""
        logger.info("正在关闭 SubStudio 并清理资源...")
        
        # 1. 停止 AI 任务 (如果正在运行)
        if hasattr(self, 'engine') and self.engine:
            if self.engine.is_running():
                logger.info("强制停止正在运行的 AI 转录任务...")
                self.engine.cancel()
                if self.engine.worker:
                    self.engine.worker.wait(1000) # 等待最多 1s
            
        # 2. 停止同步 (这将隐藏 Overlay)
        if hasattr(self, 'sync_controller') and self.sync_controller:
            self.sync_controller.stop_sync()
            
        # 3. 销毁 Overlay 窗口 (顶级窗口需要显式处理)
        if hasattr(self, 'overlay') and self.overlay:
            self.overlay.close()
            self.overlay.deleteLater()
            self.overlay = None

        # 4. 停止播放器 (释放 VLC 实例)
        if hasattr(self, 'player') and self.player:
            self.player.close() # 内部已实现释放逻辑 (释放 VLC 实例)
            
        # 5. 确保主进程退出
        from PyQt6.QtWidgets import QApplication
        import sys
        logger.info("SubStudio 资源释放完毕，正在退出进程...")
        QApplication.quit()
        # 这是一个兜底方案，防止某些 C++ 扩展 (如 VLC, PyTorch) 挂起主进程
        # 如果是作为独立工具运行，则强制退出
        sys.exit(0)
            
        super().closeEvent(event)

    def _init_model_signals(self):
        """初始化 AI 模型相关信号"""
        # 移除了直接的 ProgressDialog 绑定，改为由 Dialog 内部处理
        pass
        

    def action_open_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "Video Files (*.mp4 *.mkv *.avi *.mov);;All Files (*.*)"
        )
        if file_path:
            self.player.load_video(file_path)
            # 重新应用字幕配置（因为重载视频可能会重置某些状态）
            self.player.toggle_subtitles(False)

    def action_open_subtitle(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择字幕文件", "", "Subtitle Files (*.srt *.ass *.ssa);;All Files (*.*)"
        )
        if file_path:
            self.store.load_file(file_path)

    def init_overlay_system(self):
        """初始化覆盖层系统"""
        # A. 创建 Overlay Window
        self.overlay = OverlayWindow(self.store)
        
        # B. 绑定物理吸附 (Spatial Sync)
        # 注意：我们要吸附的是 player.video_frame (实际渲染视频的黑底区域)
        self.sync_controller = OverlaySyncController(
            self.overlay, 
            self.player.video_frame
        )
        self.sync_controller.start_sync()
        
        # C. 绑定时间驱动 (Temporal Sync)
        # 注意：此处不再使用 player.time_changed 直接推送到 UI, 
        # 而是改为在 MainView 的 _on_frame_sync 中主动 Pull, 以实现平滑算法。
        # 但我们保留 RapidController 的信号，因为它对精度要求不高
        self.player.time_changed.connect(self.rapid_controller.update_video_time)
        
        # Timeline seek -> Player seek
        self.timeline.request_seek.connect(self.player.seek_to_time)
        
        # 绑定播放状态以控制动画时钟 (60FPS Loop)
        self.player.playback_started.connect(lambda: self.overlay.set_playing_state(True))
        self.player.playback_paused.connect(lambda: self.overlay.set_playing_state(False))
        self.player.playback_stopped.connect(lambda: self.overlay.set_playing_state(False))
        
        # D. 冲突解决：禁用 Player 原生字幕
        from PyQt6.QtCore import QTimer
        # 延时一点确保 player init 完成
        QTimer.singleShot(500, lambda: self.player.toggle_subtitles(False))
        
        # E. 信号联动
        # 当数据层发生改变时，强制重绘当前帧
        self.store.dataChanged.connect(
            lambda: self.overlay.set_current_time(self.player.get_current_time())
        )
        # 当视频加载后，通知时间轴更新总时长
        self.player.time_changed.connect(self._sync_timeline_duration)
        
        # F. 样式预览联邦 (Style Preview Federation)
        self.style_editor.previewRequested.connect(self.overlay.set_preview_style)

    def _sync_timeline_duration(self):
        """确保时间轴知道当前视频的总时长"""
        duration = self.player.get_length()
        if duration > 0:
            self.timeline.set_duration(duration)
            # 只有在第一次成功探测到时长时断开这个信号绑定（避免频繁重复设置）
            # 或者每次都设置也可以

    def dragEnterEvent(self, event):
        """拖拽进入事件"""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """拖拽释放事件 - 智能加载逻辑"""
        import os
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for file_path in files:
            if os.path.isfile(file_path):
                self._smart_load(file_path)

    def _smart_load(self, path):
        """
        智能加载逻辑：
        1. 根据后缀识别类型
        2. 加载目标文件
        3. 自动寻找同级同名的配对文件并加载
        """
        import os
        video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv'}
        sub_exts = {'.srt', '.ass', '.ssa', '.vtt'}
        
        _, ext = os.path.splitext(path.lower())
        base_name, _ = os.path.splitext(path)
        
        if ext in video_exts:
            # A. 加载视频
            logger.info(f"智能加载: 加载视频 -> {path}")
            self.player.load_video(path)
            self.player.toggle_subtitles(False) # 确保禁用原生字幕
            self.timeline.load_audio(path)
            
            # B. 寻找配对字幕
            for s_ext in sub_exts:
                candidate = base_name + s_ext
                if os.path.exists(candidate):
                    logger.info(f"智能匹配: 找到对应字幕 -> {candidate}")
                    self.store.load_file(candidate)
                    break
        
        elif ext in sub_exts:
            # C. 加载字幕
            logger.info(f"智能加载: 加载字幕 -> {path}")
            self.store.load_file(path)
            
            # D. 寻找配对视频
            for v_ext in video_exts:
                candidate = base_name + v_ext
                if os.path.exists(candidate):
                    logger.info(f"智能匹配: 找到对应视频 -> {candidate}")
                    self.player.load_video(candidate)
                    self.player.toggle_subtitles(False)
                    self.timeline.load_audio(candidate)
                    break
        else:
            logger.warning(f"Unsupported file type: {ext}")

    def _on_files_dropped(self, files):
        """处理来自子组件（如时间轴）的拖放"""
        import os
        for f in files:
            if os.path.isfile(f):
                self._smart_load(f)

    def action_open_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "Video Files (*.mp4 *.mkv *.avi *.mov);;All Files (*.*)"
        )
        if file_path:
            self._smart_load(file_path)

    def action_open_subtitle(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择字幕文件", "", "Subtitle Files (*.srt *.ass *.ssa);;All Files (*.*)"
        )
        if file_path:
            self._smart_load(file_path)

    def action_save_subtitle(self):
        """保存当前字幕"""
        if not self.store.filename:
            self.action_save_subtitle_as()
        else:
            try:
                self.store.save_file()
                self.statusBar().showMessage(f"已保存: {self.store.filename}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "保存失败", str(e))

    def action_save_subtitle_as(self):
        """另存为字幕"""
        # 默认文件名
        default_path = self.store.filename
        if not default_path and self.player.current_video:
             # 如果是新建的，默认跟视频同名
             base, _ = os.path.splitext(self.player.current_video)
             default_path = base + ".srt"
             
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "另存为", default_path or "", 
            "SubRip (*.srt);;Advanced SubStation Alpha (*.ass);;All Files (*.*)"
        )
        if file_path:
            # 自动补全后缀
            if selected_filter.startswith("SubRip") and not file_path.lower().endswith(".srt"):
                file_path += ".srt"
            elif selected_filter.startswith("Advanced") and not file_path.lower().endswith(".ass"):
                file_path += ".ass"
                
            try:
                self.store.save_file(file_path)
                self.statusBar().showMessage(f"已保存: {file_path}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "保存失败", str(e))

    def get_project_data(self) -> dict:
        return {
            "video_path": self.player.current_video,
            "subtitle_file": self.store.filename
        }

    def load_project_data(self, data: dict):
        if "video_path" in data and data["video_path"]:
            self.player.load_video(data["video_path"])
        if "subtitle_file" in data and data["subtitle_file"]:
            self.store.load_file(data["subtitle_file"])

    def keyPressEvent(self, event):
        # A. 空格键播放/暂停 (全局)
        if event.key() == Qt.Key.Key_Space:
            if self.player:
                self.player.toggle_play_pause()
            event.accept()
            return

        # B. 听音拍键 J/K 拦截
        # 仅当视频正在播放且非输入框焦点时...
        if not event.modifiers() and (event.key() == Qt.Key.Key_J or event.key() == Qt.Key.Key_K):
            if self.player.is_playing():
                self.rapid_controller.on_key_press()
                # 更新 Overlay 状态
                self.overlay.show_recording_status(True)
                return 
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if not event.modifiers() and (event.key() == Qt.Key.Key_J or event.key() == Qt.Key.Key_K):
             if self.rapid_controller.is_recording:
                 self.rapid_controller.on_key_release()
                 self.overlay.show_recording_status(False)
                 self.timeline.remove_ghost_block()
                 return
        super().keyReleaseEvent(event)
