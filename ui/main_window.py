"""
主窗口

整合所有功能的主应用界面
"""

# ============ 标准库 ============
import os
import json
import time
import logging
import subprocess
import sys

# ============ PyQt6 ============
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QGroupBox, QTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QProgressBar, QMenuBar, QMenu, QToolBar, QStatusBar,
    QDialog, QInputDialog, QLineEdit, QRadioButton, QButtonGroup,
    QDialogButtonBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings, QDir, QTimer
from PyQt6.QtGui import QAction, QFont, QColor, QIcon

# ============ 项目核心模块 ============
from core.utils.exporters import DataExporter
from core.utils.preview_generator import PreviewGenerator
from core.models.project_model import ProjectModel
from core.parsers.bilingual_parser import detect_bilingual_format, parse_bilingual_file
from core.parsers.subtitle_parser import parse_subtitle_file
from core.utils.utils import detect_source_language
from core.api.api_client import APIClient, load_providers_config

# ============ UI 模块 ============
from ui.components.video_player import VideoPlayerWidget
from ui.components.delegates import ScoreDelegate
from core.workers import AlignmentWorker, LQAWorker
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.report_dialog import GlobalReportDialog
from ui.sections.log_panel import LogPanel
from ui.sections.lqa_details_panel import LQADetailsPanel
from ui.sections.subtitle_table import SubtitleTable
from core.services.input_handler import InputOrchestrator, SuggestedAction

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(self.tr("kaoche-pro"))
        self.setAcceptDrops(True)  # 启用拖放
        
        # 设置图标
        icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'icon.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 数据模型
        self.project_model = ProjectModel()
        
        # 输入智能编排器
        self.input_orchestrator = InputOrchestrator()
        
        # Worker
        self.lqa_worker = None
        self.alignment_worker = None
        
        # 状态标志
        self.has_timestamps = False  # 默认为双语文本模式
        
        self.setup_ui()
        self.create_menus()
        self.create_toolbar()
        self.create_statusbar()
        
        # 加载初始状态
        self.load_window_state()
        self.apply_layout_for_mode()
        
        self.log("✨ 应用已启动")

    @property
    def subtitle_data(self):
        return self.project_model.subtitle_data
        
    @subtitle_data.setter
    def subtitle_data(self, value):
        self.project_model.subtitle_data = value
        
    @property
    def source_file(self):
        return self.project_model.source_file
        
    @source_file.setter
    def source_file(self, value):
        self.project_model.source_file = value
        
    @property
    def target_file(self):
        return self.project_model.target_file
        
    @target_file.setter
    def target_file(self, value):
        self.project_model.target_file = value

    @property
    def global_context(self):
        return self.project_model.global_context
        
    @global_context.setter
    def global_context(self, value):
        self.project_model.global_context = value

    @property
    def video_file(self):
        return self.project_model.video_file
        
    @video_file.setter
    def video_file(self, value):
        self.project_model.video_file = value


    
    # 拖放事件支持
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for f in files:
            if os.path.isfile(f):
                self.process_file_input(f)


    def process_file_input(self, file_path):
        """处理输入文件（拖控或选择）"""
        decision = self.input_orchestrator.decide_action(
            file_path,
            has_video=bool(hasattr(self.video_player, 'current_video') and self.video_player.current_video),
            has_subtitle_data=bool(self.subtitle_data),
            has_source_file=bool(self.source_file),
            has_target_file=bool(self.target_file)
        )
        
        action = decision['action']
        
        # 1. 视频处理
        if action == SuggestedAction.LOAD_VIDEO:
            self.load_video_file(file_path)
        elif action == SuggestedAction.VIDEO_CONFLICT:
            reply = QMessageBox.question(
                self, self.tr("视频冲突"),
                self.tr("当前已加载视频：\n{}\n\n是否替换为新视频？\n(No = 在新窗口打开)").format(os.path.basename(self.video_player.current_video)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.load_video_file(file_path)
            elif reply == QMessageBox.StandardButton.No:
                self.open_new_window(file_path)
                
        # 2. 双语处理
        elif action == SuggestedAction.LOAD_BILINGUAL:
            self._confirm_and_load_bilingual(file_path, decision['format_hint'])
        elif action == SuggestedAction.BILINGUAL_CONFLICT:
            reply = QMessageBox.question(
                self, self.tr("文件冲突"),
                self.tr("检测到双语文件 ({})，但当前已有内容。\n\n是否在新窗口中打开？(No = 替换当前内容)").format(decision['format_hint']),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.open_new_window(file_path)
            elif reply == QMessageBox.StandardButton.No:
                self._confirm_and_load_bilingual(file_path, decision['format_hint'])
                
        # 3. 单语处理
        elif action == SuggestedAction.ASK_TYPE:
            items = [self.tr("原文 (Source)"), self.tr("译文 (Target)")]
            
            # 根据智能识别结果设置默认选项
            suggested = decision.get('suggested')
            default_idx = 0 if suggested == 'source' else (1 if suggested == 'target' else 0)
            
            lang_hint = f" (检测到: {decision.get('detected')})" if decision.get('detected') else ""
            
            item, ok = QInputDialog.getItem(
                self, 
                self.tr("文件类型"), 
                self.tr("请选择类型: {}{}").format(os.path.basename(file_path), lang_hint), 
                items, 
                default_idx, 
                False
            )
            if ok and item:
                if "原文" in item: self._load_as_source(file_path)
                else: self._load_as_target(file_path)
                
        elif action == SuggestedAction.SUGGEST_TARGET:
            reply = QMessageBox.question(
                self, self.tr("加载确认"), 
                self.tr("已有原文，将 {} 作为译文加载？").format(os.path.basename(file_path)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._load_as_target(file_path)
            else:
                self._handle_conflict(file_path, "source")
                
        elif action == SuggestedAction.SUGGEST_SOURCE:
            reply = QMessageBox.question(
                self, self.tr("加载确认"), 
                self.tr("已有译文，将 {} 作为原文加载？").format(os.path.basename(file_path)),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._load_as_source(file_path)
            else:
                self._handle_conflict(file_path, "target")
                
        elif action == SuggestedAction.FULL_CONFLICT:
            self._handle_conflict(file_path, "full")

    def _confirm_and_load_bilingual(self, file_path, format_type):
        """确认并加载双语文件"""
        reply = QMessageBox.question(
            self, self.tr("检测到双语文件"),
            self.tr("是否按双语文件加载？\n{} ({})").format(os.path.basename(file_path), format_type),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            pairs = parse_bilingual_file(file_path)
            if pairs:
                self.subtitle_data = [
                    {'source': {'text': src}, 'target': {'text': tgt}, 'lqa_result': None}
                    for src, tgt in pairs
                ]
                self.update_table_columns(has_timestamps=False)
                self.populate_table()
                self.source_file = None
                self.target_file = None
                self.log(f"✅ 加载双语文件: {len(pairs)} 对")

    def _handle_conflict(self, file_path, conflict_type):
        """处理文件冲突"""
        msg = self.tr("当前已加载文件，新文件: {}\n\n请选择操作：").format(os.path.basename(file_path))
        
        # 即使是 Cancel 或者是 X 关闭，最好也什么都不做
        
        # 选项列表
        options = [self.tr("在新窗口打开 (推荐)"), self.tr("替换原文"), self.tr("替换译文")]
        
        item, ok = QInputDialog.getItem(
            self, self.tr("文件冲突"), msg, options, 0, False
        )
        
        if ok and item:
            if "新窗口" in item:
                self.open_new_window(file_path)
            elif "替换原文" in item:
                self._load_as_source(file_path)
            elif "替换译文" in item:
                self._load_as_target(file_path)

    def _load_as_source(self, path):
        self.source_file = path
        self.log(f"✅ 加载原文: {os.path.basename(path)}")
        if path.lower().endswith(('.srt', '.ass', '.vtt')):
            self.show_video_panel()
        if self.target_file:
            self.auto_align()

    def _load_as_target(self, path):
        self.target_file = path
        self.log(f"✅ 加载译文: {os.path.basename(path)}")
        if path.lower().endswith(('.srt', '.ass', '.vtt')):
            self.show_video_panel()
        if self.source_file:
            self.auto_align()

    def open_new_window(self, file_path):
        """打开新窗口并加载文件"""
        
        # 使用 subprocess 启动新实例，实现完全隔离且非模态
        # 传递文件路径作为参数 (需要在 main.py 处理参数)
        # 这里暂时只启动新窗口，不传参，因为 main.py 还没改支持参数
        # 或者我们直接实例化 MainWindow (PyQt 支持多窗口)
        # 但是局部变量会被回收，需要挂载到 app 或者 self
        
        # 方案 B: 实例化新窗口 (更简单，同进程)
        # 需要 import main 或者在此处创建
        # 为了避免循环引用，我们在 main.py 里处理比较好，或者这里直接以此类实例化
        
        # 注意：必须保持引用，否则会被 GC
        if not hasattr(self, 'child_windows'):
            self.child_windows = []
            
        new_win = MainWindow()
        new_win.show()
        new_win.process_file_input(file_path)
        self.child_windows.append(new_win)
        self.log(f"已在新窗口打开: {os.path.basename(file_path)}")

    def _get_last_dir(self, key):
        settings = QSettings("Kaoche", "KaochePro")
        return settings.value(key, QDir.homePath())

    def _set_last_dir(self, key, path):
        settings = QSettings("Kaoche", "KaochePro")
        settings.setValue(key, os.path.dirname(path))

    def smart_load_file(self):
        """智能加载文件（按钮点击）"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择文件"),
            self._get_last_dir("last_dir"),
            self.tr("所有支持文件 (*.srt *.ass *.vtt *.txt *.csv *.tsv *.mp4 *.mkv *.avi);;字幕文件 (*.srt *.ass *.vtt);;视频文件 (*.mp4 *.mkv *.avi);;文本文件 (*.txt *.csv *.tsv);;所有文件 (*.*)")
        )
        if file_path:
            self._set_last_dir("last_dir", file_path)
            self.process_file_input(file_path)
    
    def setup_ui(self):
        """设置UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # 主分割器：水平分割 [左侧表格 | 右侧面板]
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 1. 左侧：字幕表格
        self.subtitle_table = SubtitleTable()
        
        self.main_splitter.addWidget(self.subtitle_table)
        
        # 2. 右侧面板：垂直布局 [视频 | LQA详情 | 日志]
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 视频播放器
        self.video_group = QGroupBox(self.tr("📺 视频预览"))
        video_layout = QVBoxLayout(self.video_group)
        self.video_player = VideoPlayerWidget()
        video_layout.addWidget(self.video_player)
        
        # 默认隐藏视频面板
        self.video_group.setVisible(False)
        
        # LQA详情
        self.lqa_details_panel = LQADetailsPanel()
        
        # 日志输出
        self.log_panel = LogPanel()
        
        self.right_splitter.addWidget(self.video_group)
        self.right_splitter.addWidget(self.lqa_details_panel)
        self.right_splitter.addWidget(self.log_panel)
        
        # 设置右侧分割比例
        self.right_splitter.setStretchFactor(0, 3) # Video (3份)
        self.right_splitter.setStretchFactor(1, 2) # Details (2份)
        self.right_splitter.setStretchFactor(2, 1) # Log (1份)
        
        right_layout.addWidget(self.right_splitter)
        self.main_splitter.addWidget(right_panel)
        
        # 设置主分割器比例 (左8 : 右2)
        self.main_splitter.setStretchFactor(0, 8)
        self.main_splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(self.main_splitter)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # ============ 信号连接 (确保所有组件已初始化) ============
        self.subtitle_table.row_selected.connect(self.on_row_selected)
        self.subtitle_table.time_jump_requested.connect(self.video_player.seek_to_time)
        self.subtitle_table.request_delete.connect(self.delete_row)
        self.subtitle_table.request_insert.connect(self.insert_row)
        self.subtitle_table.request_merge.connect(self.merge_rows)
        self.subtitle_table.request_ai_check.connect(self.ai_check_row)
        self.subtitle_table.request_justify.connect(self.add_row_justification)
        self.video_player.time_changed.connect(self.on_video_time_changed)
        
        # 初始加载通用布局
        self.load_window_state()
    
    
    def update_table_columns(self, has_timestamps: bool):
        """更新表格列显示，并恢复对应模式的布局"""
        # 保存旧模式布局
        if hasattr(self, 'has_timestamps'):
            self.save_window_state()
            
        self.has_timestamps = has_timestamps
        self.subtitle_table.has_timestamps = has_timestamps
        
        if has_timestamps:
            # 显示时间列
            self.subtitle_table.setColumnHidden(1, False)
            self.subtitle_table.setColumnHidden(2, False)
            self.video_group.setVisible(True)
        else:
            # 隐藏时间列（双语文本模式）
            self.subtitle_table.setColumnHidden(1, True)
            self.subtitle_table.setColumnHidden(2, True)
            self.video_group.setVisible(False)
            
        # 应用新模式布局
        self.apply_layout_for_mode()
    
    def create_menus(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        menubar.setObjectName("main_menubar")
        
        # 文件菜单
        file_menu = menubar.addMenu(self.tr("&文件 (File)"))
        
        open_project_action = QAction(self.tr("📂 打开项目 (.kcp)"), self)
        open_project_action.setShortcut("Ctrl+O")
        open_project_action.triggered.connect(self.open_project)
        file_menu.addAction(open_project_action)
        
        save_project_action = QAction(self.tr("💾 保存项目 (.kcp)"), self)
        save_project_action.setShortcut("Ctrl+S")
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)
        
        file_menu.addSeparator()
        
        load_source_action = QAction(self.tr("📂 加载原文字幕"), self)
        load_source_action.triggered.connect(self.load_source_file)
        file_menu.addAction(load_source_action)
        
        load_target_action = QAction(self.tr("📂 加载译文字幕"), self)
        load_target_action.triggered.connect(self.load_target_file)
        file_menu.addAction(load_target_action)
        
        load_bilingual_action = QAction(self.tr("📂 加载双语文件"), self)
        load_bilingual_action.triggered.connect(self.load_bilingual_file)
        file_menu.addAction(load_bilingual_action)
        
        file_menu.addSeparator()
        
        # 视频相关
        load_video_action = QAction(self.tr("🎬 加载视频"), self)
        load_video_action.triggered.connect(self.load_video)
        file_menu.addAction(load_video_action)
        
        file_menu.addSeparator()
        
        # 导出子菜单
        export_menu = file_menu.addMenu(self.tr("📤 导出 (Export)"))
        
        export_report_action = QAction(self.tr("📊 导出报告 (LQA Report)"), self)
        export_report_action.triggered.connect(self.export_report)
        export_menu.addAction(export_report_action)
        
        export_source_action = QAction(self.tr("📄 导出原文 (Source)"), self)
        export_source_action.triggered.connect(self.export_source)
        export_menu.addAction(export_source_action)
        
        export_target_action = QAction(self.tr("📄 导出译文 (Target)"), self)
        export_target_action.triggered.connect(self.export_target)
        export_menu.addAction(export_target_action)
        
        export_suggestions_action = QAction(self.tr("💡 导出建议 (Suggestions)"), self)
        export_suggestions_action.triggered.connect(self.export_suggestions)
        export_menu.addAction(export_suggestions_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction(self.tr("❌ 退出"), self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Tools菜单
        tools_menu = menubar.addMenu(self.tr("&工具 (Tools)"))
        
        analyze_action = QAction(self.tr("🚀 开始LQA分析"), self)
        analyze_action.triggered.connect(self.start_lqa_analysis)
        tools_menu.addAction(analyze_action)
        
        report_action = QAction(self.tr("📊 全局分析报告"), self)
        report_action.triggered.connect(self.show_global_report)
        tools_menu.addAction(report_action)
        
        realign_action = QAction(self.tr("⚙️ 重新对齐"), self)
        realign_action.triggered.connect(self.realign_subtitles)
        tools_menu.addAction(realign_action)
        
        # Settings菜单
        settings_menu = menubar.addMenu(self.tr("&设置 (Settings)"))
        
        settings_action = QAction(self.tr("⚙️ 设置"), self)
        settings_action.triggered.connect(self.open_settings)
        settings_menu.addAction(settings_action)
        
        # Help菜单
        help_menu = menubar.addMenu(self.tr("&帮助 (Help)"))
        
        about_action = QAction(self.tr("ℹ️ 关于"), self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar(self.tr("主工具栏"))
        toolbar.setObjectName("main_toolbar")  # 必须设置 objectName 才能保存状态
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # 智能加载按钮
        btn_load = QPushButton(self.tr("📂 加载文件"))
        btn_load.clicked.connect(self.smart_load_file)
        toolbar.addWidget(btn_load)
        
        toolbar.addSeparator()
        
        # 开始LQA
        analyze_action = QAction(self.tr("🚀 LQA分析"), self)
        analyze_action.triggered.connect(self.start_lqa_analysis)
        toolbar.addAction(analyze_action)
        
        toolbar.addSeparator()
        
        # 全局说明按钮（点击打开对话框）
        global_context_action = QAction(self.tr("📝 全局说明"), self)
        global_context_action.triggered.connect(self.open_global_context_dialog)
        toolbar.addAction(global_context_action)
    

    
    def create_statusbar(self):
        """创建状态栏"""
        self.statusbar = QStatusBar()
        self.statusbar.setObjectName("main_statusbar")
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage(self.tr("就绪"))
    
    def open_project(self):
        """打开项目"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("打开项目"),
            self._get_last_dir("last_project_dir"),
            self.tr("Kaoche Pro 项目 (*.kcp)")
        )
        if file_path:
            self._set_last_dir("last_project_dir", file_path)
            if self.project_model.load_project(file_path):
                self.log(self.tr("✅ 项目已加载: {}").format(os.path.basename(file_path)))
                
                # 恢复项目数据
                self.populate_table()
                
                # 恢复视频
                if self.video_file and os.path.exists(self.video_file):
                    self.show_video_panel()
                    self.video_player.load_video(self.video_file)
                else:
                    self.video_group.setVisible(False)
                
                # 记录恢复的文件
                if self.source_file:
                     self.log(f"  - 原文: {os.path.basename(self.source_file)}")
                if self.target_file:
                     self.log(f"  - 译文: {os.path.basename(self.target_file)}")
            else:
                 QMessageBox.warning(self, self.tr("错误"), self.tr("加载项目失败"))

    def save_project(self):
        """保存项目"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("保存项目"),
            self._get_last_dir("last_project_dir"),
            self.tr("Kaoche Pro 项目 (*.kcp)")
        )
        if file_path:
            self._set_last_dir("last_project_dir", file_path)
            if not file_path.endswith('.kcp'):
                file_path += '.kcp'
            
            if self.project_model.save_project(file_path):
                self.log(self.tr("✅ 项目已保存: {}").format(os.path.basename(file_path)))
            else:
                QMessageBox.warning(self, self.tr("错误"), self.tr("保存项目失败"))

    def load_source_file(self):
        """加载原文文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择文件"),
            self._get_last_dir("last_subtitle_dir"),
            self.tr("所有支持文件 (*.srt *.ass *.vtt *.txt *.mp4 *.mkv *.avi);;字幕文件 (*.srt *.ass *.vtt *.txt);;视频文件 (*.mp4 *.mkv *.avi);;所有文件 (*.*)")
        )
        
        if file_path:
            self._set_last_dir("last_subtitle_dir", file_path)
            # 检查视频文件
            if file_path.lower().endswith(('.mp4', '.mkv', '.avi')):
                self.load_video_file(file_path)
                return

            self._load_as_source(file_path)
    
    def load_target_file(self):
        """加载译文文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择文件"),
            self._get_last_dir("last_subtitle_dir"),
            self.tr("所有支持文件 (*.srt *.ass *.vtt *.txt *.mp4 *.mkv *.avi);;字幕文件 (*.srt *.ass *.vtt *.txt);;视频文件 (*.mp4 *.mkv *.avi);;所有文件 (*.*)")
        )
        
        if file_path:
            self._set_last_dir("last_subtitle_dir", file_path)
            # 检查视频文件
            if file_path.lower().endswith(('.mp4', '.mkv', '.avi')):
                self.load_video_file(file_path)
                return

            self._load_as_target(file_path)
    
    def load_video_file(self, file_path):
        """直接加载视频文件辅助方法"""
        self.show_video_panel()
        if self.video_player.load_video(file_path):
            self.video_file = file_path
            self.log(self.tr("✅ 视频加载成功: {}").format(os.path.basename(file_path)))
            self._sync_video_subtitles()
        else:
            QMessageBox.warning(self, self.tr("错误"), self.tr("视频加载失败"))
    
    def load_bilingual_file(self):
        """加载双语文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("选择双语文件"),
            self._get_last_dir("last_subtitle_dir"),
            self.tr("文本文件 (*.txt *.csv *.tsv);;所有文件 (*.*)")
        )
        
        if file_path:
            self._set_last_dir("last_subtitle_dir", file_path)
            try:
                
                pairs = parse_bilingual_file(file_path)
                
                if pairs:
                    self.subtitle_data = [
                        {'source': {'text': src}, 'target': {'text': tgt}, 'lqa_result': None}
                        for src, tgt in pairs
                    ]
                    self.update_table_columns(has_timestamps=False)  # 双语文本无时间戳
                    self.populate_table()
                    self.log(self.tr("✅ 加载双语文件: {} 对").format(len(pairs)))
                else:
                    QMessageBox.warning(self, self.tr("错误"), self.tr("解析双语文件失败"))
                    
            except Exception as e:
                QMessageBox.warning(self, self.tr("错误"), self.tr("加载失败: {}").format(str(e)))
                self.log(self.tr("❌ 加载双语文件失败: {}").format(str(e)))
    
    def auto_align(self):
        """自动对齐字幕"""
        if not self.source_file or not self.target_file:
            return
        
        # 询问用户选择对齐锚点
        
        items = [
            self.tr("原文为准 (Source) - 以原文时间轴为基准"),
            self.tr("译文为准 (Target) - 以译文时间轴为基准"),
            self.tr("自动选择 (Auto) - 自动选择最佳锚点")
        ]
        
        item, ok = QInputDialog.getItem(
            self,
            self.tr("对齐方式"),
            self.tr("请选择对齐锚点模式："),
            items,
            0,  # 默认选择原文
            False
        )
        
        if not ok:
            return
        
        # 解析选择
        if "原文" in item:
            anchor_mode = 'source'
        elif "译文" in item:
            anchor_mode = 'target'
        else:
            anchor_mode = 'auto'
        
        # 保存锚点模式
        self.anchor_mode = anchor_mode
        
        self.log(self.tr("开始自动对齐... (模式: {})").format(anchor_mode))
        self.statusbar.showMessage(self.tr("对齐中..."))
        
        try:
            
            # 解析字幕
            source_data = parse_subtitle_file(self.source_file)
            target_data = parse_subtitle_file(self.target_file)
            
            if not source_data or not target_data:
                QMessageBox.warning(self, self.tr("错误"), self.tr("字幕文件解析失败"))
                return
            
            # 获取设置中的对齐批处理大小
            from core.utils.config_manager import get_config_manager
            config = get_config_manager().load()
            batch_size = config.get('api', {}).get('batch_size_alignment', 10)
            
            # 启动对齐Worker
            self.alignment_worker = AlignmentWorker(
                source_data,
                target_data,
                anchor_mode=anchor_mode,
                auto_fill=True,
                api_client=self.get_api_client(),
                batch_size=batch_size
            )
            
            self.alignment_worker.progress.connect(self.log)
            self.alignment_worker.alignment_complete.connect(self.on_alignment_complete)
            self.alignment_worker.error_occurred.connect(lambda msg: self.log(self.tr("❌ {}").format(msg)))
            self.alignment_worker.finished.connect(lambda: self.statusbar.showMessage(self.tr("就绪")))
            
            self.alignment_worker.start()
            
        except Exception as e:
            QMessageBox.warning(self, self.tr("错误"), self.tr("对齐失败: {}").format(str(e)))
            self.log(self.tr("❌ 对齐失败: {}").format(str(e)))
    
    def on_alignment_complete(self, aligned_pairs):
        """对齐完成"""
        # 保存完整的字幕数据对象（包含时间戳）
        self.subtitle_data = [
            {'source': src, 'target': tgt, 'lqa_result': None}
            for src, tgt in aligned_pairs
        ]
        self.update_table_columns(has_timestamps=True)  # 对齐的字幕有时间戳
        self.populate_table()
        self.log(self.tr("✅ 对齐完成: {} 对").format(len(aligned_pairs)))
        
        # 同步字幕到视频播放器
        if self.video_group.isVisible():
            self._sync_video_subtitles()
    
    def populate_table(self):
        """填充表格数据 (转发给组件)"""
        self.subtitle_table.set_data(self.subtitle_data, getattr(self, 'has_timestamps', True))
    
    def format_timestamp(self, ms: int) -> str:
        """将毫秒转换为时间格式"""
        if ms == 0:
            return "00:00:00"
        
        hours = ms // 3600000
        ms %= 3600000
        minutes = ms // 60000
        ms %= 60000
        seconds = ms // 1000
        milliseconds = ms % 1000
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    
    def start_lqa_analysis(self):
        """开始LQA分析"""
        if not self.subtitle_data:
            QMessageBox.warning(self, self.tr("提示"), self.tr("请先加载字幕文件"))
            return
            
        self.log(self.tr("开始LQA分析..."))
        self.statusbar.showMessage(self.tr("分析中..."))
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        try:
            # 准备数据 - 通过 ProjectModel 获取
            pairs = self.project_model.get_lqa_pairs()
            
            # 读取prompt
            prompt_template = self.load_prompt_template()
            context = self.context_input.toPlainText().strip()
            
            # 加载设置
            from core.utils.config_manager import get_config_manager
            config = get_config_manager().load()
            
            # 获取目标语言设置
            target_lang = config.get('ui', {}).get('target_language', 'zh_CN')
            batch_size_lqa = config.get('api', {}).get('batch_size_lqa', 10)
            
            # 自动识别原文语言
            from core.utils import detect_source_language
            # 提取前50行原文用于检测 (匹配 utils.py 的逻辑)
            sample_sources = [p[0] for p in pairs[:50]]
            source_lang = detect_source_language(sample_sources)
            self.log(f"自动识别原文语言: {source_lang}")
            
            # 创建Worker
            self.lqa_worker = LQAWorker(
                pairs, 
                self.get_api_client(), 
                prompt_template, 
                context,
                target_language=target_lang,
                source_language=source_lang,
                batch_size=batch_size_lqa
            )
            
            self.lqa_worker.progress.connect(self.on_lqa_progress)
            self.lqa_worker.result_ready.connect(self.on_lqa_result)
            self.lqa_worker.error_occurred.connect(lambda i, msg: self.log(f"❌ 行{i+1}: {msg}"))
            self.lqa_worker.finished.connect(self.on_lqa_finished)
            
            self.lqa_worker.start()
            
        except Exception as e:
            QMessageBox.warning(self, "错误", f"LQA分析失败: {str(e)}")
            self.log(f"❌ LQA分析失败: {str(e)}")
    
    def on_lqa_progress(self, current, total):
        """LQA进度更新"""
        progress = int(current / total * 100)
        self.progress_bar.setValue(progress)
        self.statusbar.showMessage(f"分析中... {current}/{total}")
    
    def on_lqa_result(self, row_index, lqa_result):
        """单行LQA结果"""
        if row_index < len(self.subtitle_data):
            # 更新LQA结果
            self.subtitle_data[row_index]['lqa_result'] = lqa_result
            
            # 刷新表格
            self.subtitle_table.set_data(self.subtitle_data, getattr(self, 'has_timestamps', True))
    
    def on_lqa_finished(self):
        """LQA完成"""
        self.progress_bar.setVisible(False)
        self.statusbar.showMessage("就绪")
        self.log("✅ LQA分析完成")
        
        # 弹出全局报告
        from ui.dialogs.report_dialog import GlobalReportDialog
        dialog = GlobalReportDialog(self.subtitle_data, self)
        dialog.exec()

    def show_global_report(self):
        """显示全局分析报告"""
        if not self.subtitle_data:
            QMessageBox.information(self, self.tr("提示"), self.tr("请先加载数据"))
            return
            
        dialog = GlobalReportDialog(self.subtitle_data, self)
        dialog.exec()
    
    def on_row_selected(self, row, data=None):
        """行选择变化"""
        if row < 0 or row >= len(self.subtitle_data):
            return
        
        item = self.subtitle_data[row]
        lqa_result = item.get('lqa_result')
        
        if lqa_result:
            details = f"""评分: {lqa_result.get('score', 0)}
问题: {', '.join(lqa_result.get('issues', ['无']))}
建议: {lqa_result.get('suggestions', '无')}
"""
            self.lqa_details_panel.set_details(details)
        else:
            self.lqa_details_panel.set_details("尚未分析")
    
    def ai_check_row(self, row):
        """对单行进行单句复查 (原单句 LQA)"""
        if row < 0 or row >= len(self.subtitle_data):
            return
            
        self.log(f"🚀 正在复查第 {row+1} 行...")
        self.statusbar.showMessage(f"单句复查中: 第 {row+1} 行")
        
        # 获取数据
        item = self.subtitle_data[row]
        src = item.get('source', {})
        tgt = item.get('target', {})
        src_text = src.get('text', '') if isinstance(src, dict) else str(src)
        tgt_text = tgt.get('text', '') if isinstance(tgt, dict) else str(tgt)
        
        # 准备 API
        client = self.get_api_client()
        if not client: return
        
        prompt = self.load_prompt_template()
        
        # 使用 LQAWorker 执行单行任务
        single_worker = LQAWorker(
            subtitle_pairs=[(src_text, tgt_text)],
            api_client=client,
            prompt_template=prompt,
            context=self.global_context,
            batch_size=1
        )
        
        # 保持引用
        if not hasattr(self, '_single_workers'):
            self._single_workers = {}
        self._single_workers[row] = single_worker
        
        def on_single_result(idx, result):
            self.on_lqa_result(row, result)
            self.log(f"✅ 第 {row+1} 行复查完成 (得分: {result.get('score')})")
            
        def on_single_finished():
            if row in self._single_workers:
                del self._single_workers[row]
            self.statusbar.showMessage("就绪")
            
        single_worker.result_ready.connect(on_single_result)
        single_worker.finished.connect(on_single_finished)
        single_worker.start()
    
    def realign_subtitles(self):
        """重新对齐"""
        if self.source_file and self.target_file:
            self.auto_align()
        else:
            QMessageBox.information(self, "提示", "请先加载原文和译文文件")
    
    def export_report(self):
        """导出报告"""
        if not self.subtitle_data:
            QMessageBox.information(self, "提示", "没有数据可导出")
            return
        
        # 创建导出格式选择对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("导出选项")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        # 导出类型选择
        layout.addWidget(QLabel("选择导出类型:"))
        
        export_type_group = QButtonGroup(dialog)
        
        rb_report = QRadioButton("LQA报告 (JSON)")
        rb_report.setChecked(True)
        export_type_group.addButton(rb_report, 1)
        layout.addWidget(rb_report)
        
        rb_suggestions = QRadioButton("建议译文 (字幕文件)")
        export_type_group.addButton(rb_suggestions, 2)
        layout.addWidget(rb_suggestions)
        
        rb_csv = QRadioButton("CSV表格")
        export_type_group.addButton(rb_csv, 3)
        layout.addWidget(rb_csv)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        export_type = export_type_group.checkedId()
        
        # 根据类型选择文件名和过滤器
        if export_type == 1:  # JSON报告
            file_path, _ = QFileDialog.getSaveFileName(
                self, "保存LQA报告", "lqa_report.json",
                "JSON Files (*.json)"
            )
            if file_path:
                self._export_json_report(file_path)
                
        elif export_type == 2:  # 建议译文
            file_path, _ = QFileDialog.getSaveFileName(
                self, "保存建议译文", "suggestions.srt",
                "SRT Files (*.srt);;TXT Files (*.txt);;JSON Files (*.json)"
            )
            if file_path:
                self._export_suggestions(file_path)
                
        elif export_type == 3:  # CSV
            file_path, _ = QFileDialog.getSaveFileName(
                self, "保存CSV", "lqa_data.csv",
                "CSV Files (*.csv)"
            )
            if file_path:
                self._export_csv(file_path)
    
    def _export_json_report(self, file_path):
        """导出JSON格式LQA报告"""
        success, msg = DataExporter.export_json_report(self.subtitle_data, file_path)
        if success:
            QMessageBox.information(self, self.tr("成功"), self.tr("报告已导出"))
            self.log(f"✅ {msg}")
        else:
            QMessageBox.warning(self, self.tr("错误"), self.tr("导出失败: {}").format(msg))
    
    def export_suggestions(self, file_path=None):
        """导出LQA建议译文"""
        # 允许外部调用者(如菜单)不传参
        
        # 智能判断默认格式
        default_ext = "txt"
        filters = "Text Files (*.txt);;JSON Files (*.json)"
        if getattr(self, 'has_timestamps', False):
            default_ext = "srt"
            filters = "Subtitle Files (*.srt *.ass *.vtt);;Text Files (*.txt);;JSON Files (*.json)"
            
        if not file_path:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "保存建议译文", f"suggestions.{default_ext}", filters
            )
            
        if file_path:
            # 智能判断时间轴基准
            time_base = getattr(self, 'anchor_mode', 'source')
            # 如果是 auto，默认跟随 source，除非特别指定
            if time_base == 'auto': time_base = 'source'
            
            success, msg = DataExporter.export_suggestions(self.subtitle_data, file_path, time_base=time_base)
            if success:
                QMessageBox.information(self, self.tr("成功"), self.tr(msg))
                self.log(f"✅ {msg}")
            else:
                QMessageBox.warning(self, self.tr("错误"), self.tr("导出失败: {}").format(msg))
    
    # _write_srt 已移至 DataExporter
    
    def _export_csv(self, file_path):
        """导出CSV格式"""
        success, msg = DataExporter.export_csv(self.subtitle_data, file_path)
        if success:
            QMessageBox.information(self, self.tr("成功"), self.tr("CSV已导出"))
            self.log(f"✅ {msg}")
        else:
            QMessageBox.warning(self, self.tr("错误"), self.tr("导出失败: {}").format(msg))

    def export_source(self):
        """导出原文"""
        if not self.subtitle_data:
            return
        
        # 智能判断默认格式
        default_ext = "txt"
        filters = "Text Files (*.txt);;JSON Files (*.json)"
        if getattr(self, 'has_timestamps', False):
            default_ext = "srt"
            filters = "Subtitle Files (*.srt *.ass *.vtt);;Text Files (*.txt);;JSON Files (*.json)"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, self.tr("导出原文"), f"source_export.{default_ext}", filters
        )
        if file_path:
            # 智能判断时间轴基准
            time_base = getattr(self, 'anchor_mode', 'source')
            if time_base == 'auto': time_base = 'source'

            success, msg = DataExporter.export_content(self.subtitle_data, file_path, side='source', time_base=time_base)
            if success:
                self.log(f"✅ {msg}")
            else:
                QMessageBox.warning(self, self.tr("错误"), self.tr("导出失败: {}").format(msg))

    def export_target(self):
        """导出译文"""
        if not self.subtitle_data:
            return
            
        # 智能判断默认格式
        default_ext = "txt"
        filters = "Text Files (*.txt);;JSON Files (*.json)"
        if getattr(self, 'has_timestamps', False):
            default_ext = "srt"
            filters = "Subtitle Files (*.srt *.ass *.vtt);;Text Files (*.txt);;JSON Files (*.json)"
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, self.tr("导出译文"), f"target_export.{default_ext}", filters
        )
        if file_path:
            # 智能判断时间轴基准
            time_base = getattr(self, 'anchor_mode', 'source')
            if time_base == 'auto': time_base = 'source'

            success, msg = DataExporter.export_content(self.subtitle_data, file_path, side='target', time_base=time_base)
            if success:
                self.log(f"✅ {msg}")
            else:
                QMessageBox.warning(self, self.tr("错误"), self.tr("导出失败: {}").format(msg))

    def export_suggestions_menu(self):
        """菜单调用的导出建议入口"""
        # 调用重构后的 export_suggestions，参数为空会让其自行弹出文件选择
        self.export_suggestions()
    
    def edit_translation(self, row):
        """编辑译文"""
        if row < 0 or row >= len(self.subtitle_data):
            return
        
        item = self.subtitle_data[row]
        source = item.get('source', {})
        target = item.get('target', {})
        
        # 提取文本
        source_text = source.get('text', '') if isinstance(source, dict) else str(source)
        target_text = target.get('text', '') if isinstance(target, dict) else str(target)
        
 # 创建编辑对话框
        dialog = QDialog(self)
        dialog.setWindowTitle(f"编辑字幕 - 第{row+1}行")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(400)
        
        layout = QVBoxLayout(dialog)
        
        # 原文编辑区
        layout.addWidget(QLabel("原文:"))
        source_edit = QTextEdit()
        source_edit.setPlainText(source_text)
        source_edit.setMaximumHeight(120)
        layout.addWidget(source_edit)
        
        # 译文编辑区
        layout.addWidget(QLabel("译文:"))
        target_edit = QTextEdit()
        target_edit.setPlainText(target_text)
        target_edit.setMaximumHeight(120)
        layout.addWidget(target_edit)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 保存修改
            new_source = source_edit.toPlainText()
            new_target = target_edit.toPlainText()
            
            # 更新数据
            if isinstance(self.subtitle_data[row]['source'], dict):
                self.subtitle_data[row]['source']['text'] = new_source
            else:
                self.subtitle_data[row]['source'] = {'text': new_source}
            
            if isinstance(self.subtitle_data[row]['target'], dict):
                self.subtitle_data[row]['target']['text'] = new_target
            else:
                self.subtitle_data[row]['target'] = {'text': new_target}
            
            # 刷新表格
            self.populate_table()
            self.log(f"✏️ 已更新第{row+1}行")
    
    def copy_text(self, row, text_type):
        """复制文本到剪贴板"""
        if row < 0 or row >= len(self.subtitle_data):
            return
        
        item = self.subtitle_data[row]
        
        if text_type == 'source':
            source = item.get('source', {})
            text = source.get('text', '') if isinstance(source, dict) else str(source)
        else:  # target
            target = item.get('target', {})
            text = target.get('text', '') if isinstance(target, dict) else str(target)
        
        # 复制到剪贴板
        QApplication.clipboard().setText(text)
        self.log(f"📋 已复制{'原文' if text_type == 'source' else '译文'}")
    
    def on_cell_double_clicked(self, row, col):
        """双击单元格处理 - 编辑译文"""
        # 只在译文列（第4列）双击时编辑
        if col == 4:
            self.edit_translation(row)
    
    def delete_row(self, row):
        """删除行"""
        if row < 0 or row >= len(self.subtitle_data):
            return
        
        # 确认删除
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除第{row+1}行吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 删除数据
            if self.project_model.delete_row(row):
                # 刷新表格
                self.populate_table()
                self.log(f"🗑️ 已删除第{row+1}行")
    
    def merge_rows(self, row, direction):
        """合并行"""
        success, merge_to = self.project_model.merge_rows(row, direction)
        if success:
            self.populate_table()
            self.log(f"🔗 已合并第{row+1}行到第{merge_to+1}行")
        else:
            QMessageBox.warning(self, "错误", "无法合并行")
    
    def insert_row(self, row, position):
        """插入新行"""
        # Determine index
        if position == 'above':
            insert_index = row
        else:
            insert_index = row + 1
            
        if self.project_model.insert_row(insert_index):
            self.populate_table()
            self.log(f"➕ 已在第{insert_index+1}行插入新行")

    def add_row_justification(self, row):
        """添加辩解"""
        if row < 0 or row >= len(self.subtitle_data):
            return
            
        item = self.subtitle_data[row]
        source = item.get('source', {})
        target = item.get('target', {})
        
        source_text = source.get('text', '') if isinstance(source, dict) else str(source)
        target_text = target.get('text', '') if isinstance(target, dict) else str(target)
        current_justification = item.get('justification', '')
        
        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle(f"添加辩解 - 第{row+1}行")
        dialog.setMinimumWidth(500)
        
        layout = QVBoxLayout(dialog)
        
        ref_label = QLabel(f"原文: {source_text}\n译文: {target_text}")
        ref_label.setStyleSheet("background: #f0f0f0; padding: 8px; border-radius: 4px;")
        ref_label.setWordWrap(True)
        layout.addWidget(ref_label)
        
        # 辩解输入区
        layout.addWidget(QLabel("辩解说明:"))
        text_edit = QTextEdit()
        text_edit.setPlainText(current_justification)
        text_edit.setPlaceholderText("例如：'此处使用意译以符合目标语言习惯' 或 '专有名词保持原文'")
        layout.addWidget(text_edit)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        
        # 添加清除按钮
        clear_button = button_box.addButton("清除", QDialogButtonBox.ButtonRole.ResetRole)
        clear_button.clicked.connect(lambda: text_edit.clear())
        
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            justification = text_edit.toPlainText()
            self.subtitle_data[row]['justification'] = justification
            
            if justification:
                self.log(f"💬 已为第{row+1}行添加辩解（{len(justification)}字）")
            else:
                self.log(f"ℹ️ 已清除第{row+1}行的辩解")
            return
        
        # self.log(f"🔍 单独检查第{row+1}行...")
        # QMessageBox.information(self, "提示", "单独检查功能待实现")
    
    def open_settings(self):
        """打开设置"""
        
        from ui.dialogs.settings_dialog import SettingsDialog
        
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.log("⚙️ 设置已更新")
    
    def open_global_context_dialog(self):
        """打开全局说明对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("全局说明")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(300)
        
        layout = QVBoxLayout(dialog)
        
        # 说明标签
        info_label = QLabel("为整个文件提供背景信息或说明，AI在分析时会参考此信息。")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 示例
        example_label = QLabel("示例：'这是儿童动画，译文需要简化' 或 '专业技术文档，保持术语准确性'")
        example_label.setStyleSheet("color: gray; font-style: italic;")
        example_label.setWordWrap(True)
        layout.addWidget(example_label)
        
        # 文本编辑区
        text_edit = QTextEdit()
        text_edit.setPlainText(self.global_context)
        text_edit.setPlaceholderText("输入全局说明...")
        layout.addWidget(text_edit)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # 显示对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.global_context = text_edit.toPlainText()
            if self.global_context:
                self.log(f"✅ 已设置全局说明: {self.global_context[:50]}...")
            else:
                self.log("ℹ️ 已清空全局说明")
    
    def show_about(self):
        """关于对话框"""
        from ui.dialogs.about_dialog import AboutDialog
        dialog = AboutDialog(self)
        dialog.exec()
    
    def get_api_client(self):
        """获取API客户端"""
        from core.utils.config_manager import get_config_manager
        cm = get_config_manager()
        config = cm.load()
        
        try:
            from core.api.api_client import APIClient, load_providers_config
            
            providers = load_providers_config()
            provider_id = config.get('api', {}).get('provider')
            provider_config = providers.get(provider_id)
            
            if not provider_config:
                QMessageBox.warning(self, self.tr("错误"), self.tr("找不到提供商: {}").format(provider_id))
                return None
            
            # 使用 ConfigManager 获取 API Key（处理解密）
            # 尝试使用内存缓存的密码
            api_key = cm.get_api_key(cm.password)
            
            # 如果加载失败且启用了加密，提示输入密码
            if not api_key and config.get('encryption', {}).get('enabled', False):
                password, ok = QInputDialog.getText(
                    self, self.tr("解密所需"), 
                    self.tr("API密钥已加密，请输入主密码:"), 
                    QLineEdit.EchoMode.Password
                )
                if ok and password:
                    api_key = cm.get_api_key(password)
                    if api_key:
                        cm.password = password  # 缓存密码
                    else:
                        QMessageBox.warning(self, self.tr("错误"), self.tr("密码错误"))
                        return None
                else:
                    return None
            
            if not api_key:
                QMessageBox.warning(self, self.tr("警告"), self.tr("请在设置中配置API密钥"))
                return None
            
            model = config.get('api', {}).get('model', provider_config['default_model'])
            return APIClient(provider_config, api_key, model)
            
        except Exception as e:
            logger.error(f"创建API客户端失败: {e}")
            return None
    
    def load_prompt_template(self):
        """加载Prompt模板"""
        prompt_file = 'config/prompts/lqa_strict.txt'
        
        if os.path.exists(prompt_file):
            with open(prompt_file, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            return "请分析以下字幕的翻译质量并评分。"
    
    def log(self, message: str):
        """记录状态日志"""
        logger.info(message)
        self.log_panel.append_log(message)
    
    # ========== 视频播放器相关方法 ==========
    
    def show_video_panel(self):
        """显示视频面板"""
        self.video_group.setVisible(True)
        # 调整右侧分割器比例，给视频播放器空间
        # 父组件是 right_splitters (VLayout)
        # 视频, LQA, Log
    
    def load_video(self):
        """加载视频文件"""
        # 确保播放器可见
        self.show_video_panel()
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择视频文件",
            self._get_last_dir("last_video_dir"),
            "Video Files (*.mp4 *.mkv *.avi);;All Files (*.*)"
        )
        
        if file_path:
            self._set_last_dir("last_video_dir", file_path)
            if self.video_player.load_video(file_path):
                self.log(f"✅ 视频加载成功: {os.path.basename(file_path)}")
                # 自动同步当前译文为字幕
                self._sync_video_subtitles()
            else:
                QMessageBox.warning(self, "错误", "视频加载失败，请检查是否安装了VLC播放器")
    
    def _sync_video_subtitles(self):
        """生成临时字幕文件并由播放器加载（使用当前译文）"""
        if not self.subtitle_data:
            # 尝试直接加载文件（针对未对齐的单文件情况）
            if self.target_file and os.path.exists(self.target_file) and self.target_file.lower().endswith('.ass'):
                self.log(f"直接加载原有ASS字幕: {os.path.basename(self.target_file)}")
                self._load_subtitle_delayed(self.target_file)
                return
            elif self.source_file and os.path.exists(self.source_file) and self.source_file.lower().endswith('.ass'):
                self.log(f"直接加载原有ASS字幕: {os.path.basename(self.source_file)}")
                self._load_subtitle_delayed(self.source_file)
                return
                
            self.log("⚠️ 无可用字幕数据")
            return
            
        # 优先策略：如果由文件加载且未经过大量修改，且是ASS格式，优先使用原文件以保留特效
        # 这里简化判断：如果有target_file且是ass，直接用原文件
        # (注：这会导致表格修改无法实时同步到视频，直到保存。但在播放预览时用户通常更看重特效)
        if self.target_file and os.path.exists(self.target_file) and self.target_file.lower().endswith('.ass'):
             # 简单的检查：行数是否一致？如果一致则认为是原文件
             # 更严格的检查比较耗时，这里响应用户需求"按原样显示"
             self.log(f"使用原始ASS文件以保留特效: {os.path.basename(self.target_file)}")
             self._load_subtitle_delayed(self.target_file)
             return
            
        # 使用 PreviewGenerator 生成预览
        project_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
        
        temp_path = PreviewGenerator.generate_preview(self.subtitle_data, project_root)
        
        if temp_path:
            self.log(f"生成预览字幕: {os.path.basename(temp_path)}")
            # 稍微延迟一下确保文件已写入
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, lambda: self._load_subtitle_delayed(temp_path))
        else:
            self.log(self.tr("❌ 生成预览失败，可能缺少 pysubs2 库"))

    def _load_subtitle_delayed(self, path):
        """延迟加载字幕"""
        if self.video_player.load_subtitle(path):
            self.log("✅ 已自动加载当前译文作为视频字幕")
        else:
            self.log("❌ 播放器加载字幕失败")
    
    def on_video_time_changed(self, current_time_ms):
        """
        视频时间变化 → 同步表格高亮 (单向同步，不回传跳转)
        """
        if not self.subtitle_data:
            return
        
        current_time_seconds = current_time_ms / 1000.0
        self.subtitle_table.select_row_at_time(current_time_seconds)
    
    def on_subtitle_row_clicked(self, row):
        """
        表格行点击 → 视频跳转
        """
        if row < 0 or row >= len(self.subtitle_data):
            return
        
        item = self.subtitle_data[row]
        source = item.get('source', {})
        
        if isinstance(source, dict) and source.get('start') is not None:
            start_time_ms = int(source['start'] * 1000)
            self.video_player.seek_to_time(start_time_ms)
            
            # 可选：自动播放
            if hasattr(self.video_player, 'player') and self.video_player.player:
                if not self.video_player.player.is_playing():
                    self.video_player.play()

    # ============ 布局与状态持久化 ============
    
    def get_mode_prefix(self):
        """获取当前模式的前缀"""
        return "mode_sub" if self.has_timestamps else "mode_text"

    def save_window_state(self):
        """保存当前窗口状态和模式特定布局"""
        settings = QSettings("Kaoche", "KaochePro")
        
        # 1. 通用状态
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        
        # 2. 模式特定布局 (分割器)
        prefix = self.get_mode_prefix()
        settings.setValue(f"{prefix}/main_splitter", self.main_splitter.saveState())
        settings.setValue(f"{prefix}/right_splitter", self.right_splitter.saveState())
        
        # 3. 表格列宽
        column_widths = [self.subtitle_table.columnWidth(i) for i in range(self.subtitle_table.columnCount())]
        settings.setValue(f"{prefix}/column_widths", column_widths)
        
        logger.info(f"已保存模式 {prefix} 的布局")

    def load_window_state(self):
        """加载窗口状态 (仅限通用状态)"""
        settings = QSettings("Kaoche", "KaochePro")
        geom = settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)
        state = settings.value("windowState")
        if state:
            self.restoreState(state)

    def apply_layout_for_mode(self):
        """切换模式时应用特定的布局记忆"""
        settings = QSettings("Kaoche", "KaochePro")
        prefix = self.get_mode_prefix()
        
        # 1. 恢复分割器状态
        main_state = settings.value(f"{prefix}/main_splitter")
        if main_state:
            self.main_splitter.restoreState(main_state)
            
        right_state = settings.value(f"{prefix}/right_splitter")
        if right_state:
            self.right_splitter.restoreState(right_state)
            
        # 2. 恢复表格列宽
        widths = settings.value(f"{prefix}/column_widths")
        if widths and isinstance(widths, list):
            for i, w in enumerate(widths):
                if i < self.subtitle_table.columnCount():
                    self.subtitle_table.setColumnWidth(i, int(w))
        
        logger.info(f"已应用模式 {prefix} 的布局记忆")

    def closeEvent(self, event):
        """关闭窗口时保存设置"""
        self.save_window_state()
        super().closeEvent(event)
