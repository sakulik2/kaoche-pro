import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QGroupBox, QTextEdit, 
    QFileDialog, QMessageBox, QProgressBar,
    QInputDialog, QLineEdit, QRadioButton, QButtonGroup,
    QDialogButtonBox, QApplication
)
from PyQt6.QtCore import Qt, QSettings, QDir, QTimer
from PyQt6.QtGui import QIcon
import shutil

# ============ 共享核心模块 ============
from core.shared.project_model import ProjectModel
from core.shared.api_client import APIClient, load_providers_config
from core.shared.input_handler import InputOrchestrator, SuggestedAction
from ui.shared.video_player import VideoPlayerWidget

# ============ LQA 专用 UI ============
from .subtitle_table import SubtitleTable
from .lqa_details_panel import LQADetailsPanel
from .log_panel import LogPanel

# ============ 其他核心 ============
from core.workers import AlignmentWorker, LQAWorker
from core.parsers.bilingual_parser import parse_bilingual_file
from core.parsers.subtitle_parser import parse_subtitle_file
from core.utils.exporters import DataExporter
from core.utils.preview_generator import PreviewGenerator
from core.utils.utils import detect_source_language

logger = logging.getLogger(__name__)

class LqaMainView(QWidget):
    """LQA 工具的主视图"""
    def __init__(self, hub, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.setAcceptDrops(True)
        
        # 数据模型 (从 hub 或新建)
        self.project_model = ProjectModel()
        self.input_orchestrator = InputOrchestrator()
        
        # 状态
        self.has_timestamps = False
        self.lqa_worker = None
        self.alignment_worker = None
        self._single_workers = {}
        
        self.setup_ui()
        self.load_state()

    @property
    def subtitle_data(self): return self.project_model.subtitle_data
    @subtitle_data.setter
    def subtitle_data(self, v): self.project_model.subtitle_data = v
    @property
    def source_file(self): return self.project_model.source_file
    @source_file.setter
    def source_file(self, v): self.project_model.source_file = v
    @property
    def target_file(self): return self.project_model.target_file
    @target_file.setter
    def target_file(self, v): self.project_model.target_file = v
    @property
    def global_context(self): return self.project_model.global_context
    @global_context.setter
    def global_context(self, v): self.project_model.global_context = v
    @property
    def video_file(self): return self.project_model.video_file
    @video_file.setter
    def video_file(self, v): self.project_model.video_file = v

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)
        
        # 专业工具栏 (扁平风格)
        self.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: 500;
                color: #374151;
            }
            QPushButton:hover {
                background-color: #f9fafb;
                border: 1px solid #9ca3af;
                color: #111827;
            }
            QGroupBox {
                font-weight: 700;
                border: 1px solid #e5e7eb;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
                color: #111827;
            }
        """)

        self.op_bar = QHBoxLayout()
        btn_load = QPushButton("加载文件...")
        btn_load.clicked.connect(self.smart_load_file)
        self.op_bar.addWidget(btn_load)
        
        btn_analyze = QPushButton("开始 AI 分析")
        btn_analyze.clicked.connect(self.start_lqa_analysis)
        self.op_bar.addWidget(btn_analyze)
        
        btn_context = QPushButton("项目说明")
        btn_context.clicked.connect(self.open_global_context_dialog)
        self.op_bar.addWidget(btn_context)
        
        self.op_bar.addStretch()
        main_layout.addLayout(self.op_bar)
        
        # 主分割器
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(2)
        
        # 1. 左侧：字幕表格
        self.subtitle_table = SubtitleTable()
        self.main_splitter.addWidget(self.subtitle_table)
        
        # 2. 右侧面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setHandleWidth(2)
        
        # 视频
        self.video_group = QGroupBox("视频预览")
        v_layout = QVBoxLayout(self.video_group)
        v_layout.setContentsMargins(2, 8, 2, 2)
        self.video_player = VideoPlayerWidget()
        v_layout.addWidget(self.video_player)
        self.video_group.setVisible(False)
        
        # LQA详情
        self.lqa_details_panel = LQADetailsPanel()
        
        # 日志
        self.log_panel = LogPanel()
        
        self.right_splitter.addWidget(self.video_group)
        self.right_splitter.addWidget(self.lqa_details_panel)
        self.right_splitter.addWidget(self.log_panel)
        
        self.right_splitter.setStretchFactor(0, 3)
        self.right_splitter.setStretchFactor(1, 2)
        self.right_splitter.setStretchFactor(2, 1)
        
        right_layout.addWidget(self.right_splitter)
        self.main_splitter.addWidget(right_panel)
        self.main_splitter.setStretchFactor(0, 8)
        self.main_splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(self.main_splitter)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # 信号连接
        self.subtitle_table.row_selected.connect(self.on_row_selected)
        self.subtitle_table.time_jump_requested.connect(self.video_player.seek_to_time)
        self.subtitle_table.request_delete.connect(self.delete_row)
        self.subtitle_table.request_insert.connect(self.insert_row)
        self.subtitle_table.request_merge.connect(self.merge_rows)
        self.subtitle_table.request_ai_check.connect(self.ai_check_row)
        self.subtitle_table.request_justify.connect(self.add_row_justification)
        self.video_player.time_changed.connect(self.on_video_time_changed)

    def log(self, message):
        self.log_panel.append_log(message)

    # --- 拖放与加载逻辑 (从 MainWindow 复制并适配) ---
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.accept()
        else: event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for f in files:
            if os.path.isfile(f): self.process_file_input(f)

    def process_file_input(self, file_path):
        decision = self.input_orchestrator.decide_action(
            file_path,
            has_video=bool(hasattr(self.video_player, 'current_video') and self.video_player.current_video),
            has_subtitle_data=bool(self.subtitle_data),
            has_source_file=bool(self.source_file),
            has_target_file=bool(self.target_file)
        )
        action = decision['action']
        if action == SuggestedAction.LOAD_VIDEO:
            self.load_video_file(file_path)
        elif action == SuggestedAction.LOAD_BILINGUAL:
            self._confirm_and_load_bilingual(file_path, decision['format_hint'])
        elif action == SuggestedAction.ASK_TYPE:
            items = ["原文 Source", "译文 Target"]
            item, ok = QInputDialog.getItem(self, "文件类型", f"请选择类型: {os.path.basename(file_path)}", items, 0, False)
            if ok and item:
                if "原文" in item: self._load_as_source(file_path)
                else: self._load_as_target(file_path)
        elif action == SuggestedAction.SUGGEST_TARGET:
            self._load_as_target(file_path)
        elif action == SuggestedAction.SUGGEST_SOURCE:
            self._load_as_source(file_path)
        elif action == SuggestedAction.FULL_CONFLICT:
            reply = QMessageBox.question(
                self, "文件冲突",
                "当前已加载数据。是否在新窗口中打开此文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # 调用 Hub 中的 MainWindow 实例创建新窗口
                if self.hub.main_window:
                    self.hub.main_window.create_new_instance("lqa")
                    # 这里新窗口启动后会自动加载吗？
                    # 简单起见，这里只负责开窗口，用户再拖一次。
                    # 或者更高级点：传递路径给新实例。

    def _confirm_and_load_bilingual(self, file_path, format_hint):
        """确认并加载双语文件"""
        reply = QMessageBox.question(
            self, "检测到双语文件",
            f"是否按双语文件加载？\n{os.path.basename(file_path)} {format_hint}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            pairs = parse_bilingual_file(file_path)
            if pairs:
                self.subtitle_data = [
                    {'source': {'text': src}, 'target': {'text': tgt}, 'lqa_result': None}
                    for src, tgt in pairs
                ]
                self.update_table_columns(False)
                self.populate_table()
                self.log(f"✅ 加载双语文件: {len(pairs)} 对")
                self._sync_video_subtitles()

    def load_video_file(self, file_path):
        self.video_group.setVisible(True)
        if self.video_player.load_video(file_path):
            self.video_file = file_path
            self.log(f"✅ 视频加载成功: {os.path.basename(file_path)}")
            self._sync_video_subtitles()
        else:
            QMessageBox.warning(self, "错误", "视频加载失败")

    def _sync_video_subtitles(self):
        """同步字幕到视频播放器"""
        if not self.subtitle_data: return
        
        project_root = os.getcwd()
        temp_dir = os.path.join(project_root, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, 'preview_subtitles.ass')
        
        # 强制使用源 .ass 文件策略：
        # 如果目标文件本身就是 .ass，我们直接复制它到临时目录，以保留所有原始样式和层级
        if self.target_file and self.target_file.lower().endswith('.ass') and os.path.exists(self.target_file):
            try:
                shutil.copy2(self.target_file, temp_path)
                logger.info(f"✅ 强制使用原始 .ass 文件副本: {self.target_file}")
            except Exception as e:
                logger.error(f"复制原始 .ass 失败，回退到生成模式: {e}")
                temp_path = PreviewGenerator.generate_preview(self.subtitle_data, project_root)
        else:
            # 否则（SRT, VTT 或表格编辑状态），由生成器生成预览
            temp_path = PreviewGenerator.generate_preview(self.subtitle_data, project_root)
            
        if temp_path and os.path.exists(temp_path):
            # 给文件系统一点写入稳定的时间
            QTimer.singleShot(100, lambda: self.video_player.load_subtitle(temp_path))

    def smart_load_file(self):
        last_dir = ""
        if self.hub and self.hub.history:
            last_dir = self.hub.history.get_last_dir('subtitle')

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择文件", last_dir, "Supported Files (*.srt *.ass *.vtt *.mp4 *.mkv *.avi *.txt)"
        )
        if file_path:
            if self.hub and self.hub.history:
                self.hub.history.set_last_dir('subtitle', file_path)
            self.process_file_input(file_path)

    def _load_as_source(self, path):
        self.source_file = path
        self.log(f"✅ 加载原文: {os.path.basename(path)}")
        if self.target_file: self.auto_align()

    def _load_as_target(self, path):
        self.target_file = path
        self.log(f"✅ 加载译文: {os.path.basename(path)}")
        if self.source_file: self.auto_align()

    def auto_align(self):
        # 简化版
        source_data = parse_subtitle_file(self.source_file)
        target_data = parse_subtitle_file(self.target_file)
        if not source_data or not target_data: return
        
        self.alignment_worker = AlignmentWorker(
            source_data, target_data, anchor_mode='source', 
            api_client=self.get_api_client()
        )
        self.alignment_worker.alignment_complete.connect(self.on_alignment_complete)
        self.alignment_worker.start()

    def on_alignment_complete(self, pairs):
        self.subtitle_data = [{'source': s, 'target': t, 'lqa_result': None} for s, t in pairs]
        self.update_table_columns(True)
        self.populate_table()
        self.log(f"✅ 对齐完成: {len(pairs)} 对")
        self._sync_video_subtitles()

    def populate_table(self):
        self.subtitle_table.set_data(self.subtitle_data, self.has_timestamps)

    def update_table_columns(self, has_ts):
        self.has_timestamps = has_ts
        self.subtitle_table.has_timestamps = has_ts
        self.video_group.setVisible(has_ts)

    def start_lqa_analysis(self):
        pairs = self.project_model.get_lqa_pairs()
        if not pairs:
            QMessageBox.warning(self, "完成", "没有可分析的内容")
            return
            
        self.log("🚀 开始 LQA 分析...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # 加载配置和 prompt
        config = self.hub.get_service("config") or {}
        prompt = self.load_prompt_template()
        
        self.lqa_worker = LQAWorker(
            pairs, 
            self.get_api_client(), 
            prompt, 
            self.global_context,
            batch_size=config.get('api', {}).get('batch_size_lqa', 5)
        )
        self.lqa_worker.progress.connect(self.on_lqa_progress)
        self.lqa_worker.result_ready.connect(self.on_lqa_result)
        self.lqa_worker.finished.connect(self.on_lqa_finished)
        self.lqa_worker.start()

    def on_lqa_progress(self, current, total):
        self.progress_bar.setValue(int(current / total * 100))

    def on_lqa_finished(self):
        self.progress_bar.setVisible(False)
        self.log("✅ LQA 分析完成")

    def get_api_client(self):
        # 尝试从 Hub 获取共享示例
        client = self.hub.get_service("api_client")
        if client: return client
        
        # 如果没有，根据配置创建 (简化实现)
        from core.utils.config_manager import get_config_manager
        cm = get_config_manager()
        config = cm.load()
        api_key = cm.get_api_key(cm.password)
        if not api_key: return None
        
        provider = config.get('api', {}).get('provider', 'openai')
        providers = load_providers_config()
        p_cfg = providers.get(provider)
        if not p_cfg: return None
        
        model = config.get('api', {}).get('model', p_cfg['default_model'])
        client = APIClient(p_cfg, api_key, model)
        self.hub.register_service("api_client", client) # 存入 Hub 共享
        return client

    def load_prompt_template(self):
        path = 'config/prompts/lqa_strict.txt'
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f: return f.read()
        return "请分析以下字幕的翻译质量并评分。"

    def open_global_context_dialog(self):
        text, ok = QInputDialog.getMultiLineText(self, "全局说明", "输入背景信息:", self.global_context)
        if ok: self.global_context = text

    # --- 各种删除合并接口 (转发给 Model) ---
    def delete_row(self, row):
        if self.project_model.delete_row(row): self.populate_table()
    def on_row_selected(self, row, data=None):
        """行选择变化时同步 LQA 详情"""
        if 0 <= row < len(self.subtitle_data):
            item = self.subtitle_data[row]
            lqa_result = item.get('lqa_result')
            
            if lqa_result:
                # 简单格式化 LQA 结果
                details = f"评价: {lqa_result.get('feedback', '无')}\n"
                details += f"得分: {lqa_result.get('score', 0)}\n"
                details += f"修改建议: {lqa_result.get('suggestion', '无')}"
                self.lqa_details_panel.set_details(details)
            else:
                self.lqa_details_panel.set_details("尚未分析")

    def on_lqa_result(self, row_index, lqa_result):
        """单行 LQA 结果处理"""
        if row_index < len(self.subtitle_data):
            self.subtitle_data[row_index]['lqa_result'] = lqa_result
            self.populate_table()

    def merge_rows(self, row, direction):
        """合并行接口"""
        success, merge_to = self.project_model.merge_rows(row, direction)
        if success:
            self.populate_table()
            self.log(f"🔗 已合并第 {row+1} 行到第 {merge_to+1} 行")

    def ai_check_row(self, row):
        """对单行进行 AI 复查"""
        if row < 0 or row >= len(self.subtitle_data): return
        self.log(f"🚀 正在复查第 {row+1} 行...")
        
        client = self.get_api_client()
        if not client: return
        
        item = self.subtitle_data[row]
        src = item.get('source', '')
        tgt = item.get('target', '')
        src_text = src.get('text', '') if isinstance(src, dict) else str(src)
        tgt_text = tgt.get('text', '') if isinstance(tgt, dict) else str(tgt)

        single_worker = LQAWorker(
            subtitle_pairs=[(src_text, tgt_text)],
            api_client=client,
            prompt_template=self.load_prompt_template(),
            context=self.global_context,
            batch_size=1
        )
        single_worker.result_ready.connect(lambda idx, res: self.on_lqa_result(row, res))
        single_worker.start()

    def insert_row(self, row, pos):
        """插入新行接口"""
        idx = row if pos == 'above' else row + 1
        if self.project_model.insert_row(idx):
            self.populate_table()
            self.log(f"➕ 已在第 {idx+1} 行插入新行")

    def add_row_justification(self, row):
        """添加辩解接口"""
        if row < 0 or row >= len(self.subtitle_data): return
        text, ok = QInputDialog.getMultiLineText(
            self, f"辩解说明 - 第 {row+1} 行", 
            "请输入对此翻译的解释（AI 分析时将参考）：",
            self.subtitle_data[row].get('justification', '')
        )
        if ok:
            self.subtitle_data[row]['justification'] = text
            self.log(f"💬 已为第 {row+1} 行添加辩解")

    def on_video_time_changed(self, ms):
        self.subtitle_table.select_row_at_time(ms / 1000.0)

    # --- 状态与项目持久化 ---
    def save_state(self):
        """保存 UI 状态 (Splitters 等)"""
        settings = QSettings("Kaoche", "KaochePro")
        settings.setValue("lqa/main_splitter", self.main_splitter.saveState())
        settings.setValue("lqa/right_splitter", self.right_splitter.saveState())

    def load_state(self):
        """加载 UI 状态"""
        settings = QSettings("Kaoche", "KaochePro")
        ms = settings.value("lqa/main_splitter")
        if ms: self.main_splitter.restoreState(ms)
        rs = settings.value("lqa/right_splitter")
        if rs: self.right_splitter.restoreState(rs)

    def get_project_data(self) -> dict:
        """获取当前项目的完整数据包（用于保存为 .kcp）"""
        return {
            "source_file": self.source_file,
            "target_file": self.target_file,
            "video_file": self.video_file,
            "global_context": self.global_context,
            "subtitle_data": self.subtitle_data,
            "has_timestamps": self.has_timestamps
        }

    def load_project_data(self, data: dict):
        """从数据包恢复项目（用于从 .kcp 加载）"""
        self.source_file = data.get("source_file", "")
        self.target_file = data.get("target_file", "")
        self.video_file = data.get("video_file", "")
        self.global_context = data.get("global_context", "")
        self.subtitle_data = data.get("subtitle_data", [])
        self.has_timestamps = data.get("has_timestamps", False)
        
        # UI 更新
        self.context_edit.setText(self.global_context)
        self.populate_table()
        if self.video_file and os.path.exists(self.video_file):
            self.video_player.load_video(self.video_file)
        
        self.log(f"📁 项目数据已重载")
