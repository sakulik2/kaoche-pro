import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QComboBox, QLineEdit, QProgressBar,
    QFileDialog, QMessageBox, QFrame, QScrollArea, QGroupBox,
    QGridLayout, QSpinBox, QTabWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from ..logic.engine import SRTToolbox

logger = logging.getLogger(__name__)

class SrtToolboxMainView(QWidget):
    """字幕工具箱主视图 - 重构为选项卡式布局以减少拥挤"""
    def __init__(self, hub, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.toolbox = SRTToolbox()
        self.setAcceptDrops(True)
        self.setup_ui()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # 1. 左侧：文件列表管理 (队列区)
        left_panel = QFrame()
        left_panel.setFixedWidth(280)
        left_panel.setObjectName("SidePanel")
        left_panel.setStyleSheet("#SidePanel { border-right: 1px solid #e5e7eb; }")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 15, 0)
        
        lbl_queue = QLabel("📂 待处理队列")
        lbl_queue.setStyleSheet("font-weight: bold; color: #374151; font-size: 13px;")
        left_layout.addWidget(lbl_queue)

        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget { border: 1px solid #d1d5db; border-radius: 4px; background: white; }
            QListWidget::item { padding: 6px; border-bottom: 1px solid #f3f4f6; }
        """)
        left_layout.addWidget(self.file_list)
        
        btn_row = QHBoxLayout()
        self.btn_add = QPushButton("➕ 添加文件")
        self.btn_add.clicked.connect(self.on_add_files)
        btn_row.addWidget(self.btn_add)
        
        self.btn_clear = QPushButton("🗑 清空")
        self.btn_clear.clicked.connect(lambda: self.file_list.clear())
        btn_row.addWidget(self.btn_clear)
        left_layout.addLayout(btn_row)
        
        main_layout.addWidget(left_panel)

        # 2. 右侧：功能分类选项卡
        right_panel = QVBoxLayout()
        
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #e5e7eb; top: -1px; background: white; border-radius: 4px; }
            QTabBar::tab { padding: 10px 20px; font-weight: 500; color: #6b7280; }
            QTabBar::tab:selected { color: #2563eb; border-bottom: 2px solid #2563eb; background: #eff6ff; }
        """)

        # --- 选项卡 1: 时间轴 (Timeline) ---
        time_tab = QWidget()
        time_layout = QVBoxLayout(time_tab)
        time_layout.setContentsMargins(20, 20, 20, 20)
        
        desc_time = QLabel("调整字幕全局时间偏移，支持正负数。")
        desc_time.setStyleSheet("color: #6b7280; font-style: italic; margin-bottom: 10px;")
        time_layout.addWidget(desc_time)

        time_grid = QGridLayout()
        time_grid.setSpacing(15)
        time_grid.addWidget(QLabel("偏移时长 (ms):"), 0, 0)
        self.shift_ms = QSpinBox()
        self.shift_ms.setRange(-999999, 999999)
        self.shift_ms.setSingleStep(100)
        self.shift_ms.setFixedHeight(30)
        time_grid.addWidget(self.shift_ms, 0, 1)
        
        self.btn_shift = QPushButton("⚡ 执行批量平移")
        self.btn_shift.setFixedHeight(32)
        self.btn_shift.clicked.connect(lambda: self.batch_process('shift'))
        time_grid.addWidget(self.btn_shift, 0, 2)
        
        time_layout.addLayout(time_grid)
        time_layout.addStretch()
        self.tabs.addTab(time_tab, "🕒 时间轴调整")

        # --- 选项卡 2: 双语与合并 (Merge/Split) ---
        bilingual_tab = QWidget()
        bi_layout = QVBoxLayout(bilingual_tab)
        bi_layout.setContentsMargins(20, 20, 20, 20)
        
        desc_bi = QLabel("处理多语言字幕的合并与智控分离。")
        desc_bi.setStyleSheet("color: #6b7280; font-style: italic; margin-bottom: 10px;")
        bi_layout.addWidget(desc_bi)

        bi_grid = QGridLayout()
        bi_grid.setSpacing(15)
        
        self.btn_concat = QPushButton("🔗 对队列内所有 SRT 进行首尾串联")
        self.btn_concat.clicked.connect(self.on_concat_files)
        bi_grid.addWidget(self.btn_concat, 0, 0, 1, 2)
        
        self.btn_split = QPushButton("✂️ 智控分离双语字幕")
        self.btn_split.clicked.connect(lambda: self.batch_process('split'))
        bi_grid.addWidget(self.btn_split, 1, 0, 1, 2)
        
        bi_layout.addLayout(bi_grid)
        bi_layout.addStretch()
        self.tabs.addTab(bilingual_tab, "🔗 合并与拆分")

        # --- 选项卡 3: 内容修复 (Fix/Content) ---
        fix_tab = QWidget()
        fix_layout = QVBoxLayout(fix_tab)
        fix_layout.setContentsMargins(20, 20, 20, 20)

        desc_fix = QLabel("智能处理超长句断裂及 TXT 快速转 SRT。")
        desc_fix.setStyleSheet("color: #6b7280; font-style: italic; margin-bottom: 10px;")
        fix_layout.addWidget(desc_fix)

        fix_grid = QGridLayout()
        fix_grid.setSpacing(15)
        
        fix_grid.addWidget(QLabel("单行上限字符:"), 0, 0)
        self.max_chars = QSpinBox()
        self.max_chars.setValue(40)
        self.max_chars.setFixedHeight(30)
        fix_grid.addWidget(self.max_chars, 0, 1)
        
        self.btn_fix_long = QPushButton("🪄 执行智能断句")
        self.btn_fix_long.clicked.connect(lambda: self.batch_process('fix_long'))
        fix_grid.addWidget(self.btn_fix_long, 0, 2)
        
        self.btn_txt_to_srt = QPushButton("📄 将剪贴板 TXT 智能转为 SRT 基础流")
        self.btn_txt_to_srt.clicked.connect(self.on_txt_to_srt)
        fix_grid.addWidget(self.btn_txt_to_srt, 1, 0, 1, 3)

        self.btn_regroup = QPushButton("🚀 Whisper 语义重组按标点")
        self.btn_regroup.setStyleSheet("background-color: #f0fdf4; border-color: #22c55e; color: #166534;")
        self.btn_regroup.clicked.connect(lambda: self.batch_process('regroup'))
        fix_grid.addWidget(self.btn_regroup, 2, 0, 1, 3)

        fix_layout.addLayout(fix_grid)
        fix_layout.addStretch()
        self.tabs.addTab(fix_tab, "🪄 智能修复")

        # --- 选项卡 4: 清洗提取 (Clean/Extract) ---
        clean_tab = QWidget()
        clean_layout = QVBoxLayout(clean_tab)
        clean_layout.setContentsMargins(20, 20, 20, 20)

        desc_clean = QLabel("针对字幕文本进行正则过滤或纯文本提取。")
        desc_clean.setStyleSheet("color: #6b7280; font-style: italic; margin-bottom: 10px;")
        clean_layout.addWidget(desc_clean)

        clean_grid = QGridLayout()
        clean_grid.setSpacing(15)
        
        self.btn_chinese = QPushButton("🇨🇳 仅保留中文字符")
        self.btn_chinese.clicked.connect(lambda: self.batch_process('zh_only'))
        clean_grid.addWidget(self.btn_chinese, 0, 0)
        
        self.btn_english = QPushButton("🇺🇸 仅保留英文字符")
        self.btn_english.clicked.connect(lambda: self.batch_process('en_only'))
        clean_grid.addWidget(self.btn_english, 0, 1)

        self.btn_strip = QPushButton("📖 提取为纯文本 txt")
        self.btn_strip.setFixedHeight(35)
        self.btn_strip.clicked.connect(self.on_strip_text)
        clean_grid.addWidget(self.btn_strip, 1, 0, 1, 2)

        clean_layout.addLayout(clean_grid)
        clean_layout.addStretch()
        self.tabs.addTab(clean_tab, "🧹 清洗与提取")

        right_panel.addWidget(self.tabs)
        main_layout.addLayout(right_panel, 1)

        # 全局样式抛光
        self.setStyleSheet(self.styleSheet() + """
            QPushButton { padding: 8px 15px; background: #ffffff; border: 1px solid #d1d5db; border-radius: 4px; color: #374151; font-weight: 500; }
            QPushButton:hover { background: #f9fafb; border-color: #2563eb; color: #2563eb; }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path) and path.lower().endswith('.srt'):
                self.add_file_item(path)

    def on_add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "添加 SRT 文件", "", "SRT Files (*.srt)")
        for p in paths: self.add_file_item(p)

    def add_file_item(self, path):
        item = QListWidgetItem(os.path.basename(path))
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        self.file_list.addItem(item)

    def batch_process(self, action):
        count = self.file_list.count()
        if count == 0:
            QMessageBox.warning(self, "提示", "请先添加文件到队列")
            return
            
        success = 0
        for i in range(count):
            path = self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            if self.toolbox.load_file(path):
                if action == 'shift':
                    self.toolbox.shift_timeline(self.shift_ms.value())
                elif action == 'fix_long':
                    self.toolbox.fix_long_sentences(self.max_chars.value())
                elif action == 'zh_only':
                    self.toolbox.filter_text('chinese_only')
                elif action == 'en_only':
                    self.toolbox.filter_text('english_only')
                elif action == 'regroup':
                    self.toolbox.regroup_by_punctuation()
                elif action == 'split':
                    fa, fb = self.toolbox.split_bilingual_smart()
                    fa.save(path.replace('.srt', '_v1.srt'))
                    fb.save(path.replace('.srt', '_v2.srt'))
                    success += 1
                    continue # split 自己存了
                
                # 默认保存回原文件 (带后缀)
                out_path = path.replace('.srt', '_processed.srt')
                self.toolbox.save_file(out_path)
                success += 1
        
        QMessageBox.information(self, "处理完成", f"成功处理 {success} 个文件。结果已存至原目录。")

    def on_concat_files(self):
        count = self.file_list.count()
        if count < 2:
            QMessageBox.warning(self, "提示", "串联至少需要两个文件")
            return
        
        paths = [self.file_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(count)]
        combined = self.toolbox.concat_srts(paths)
        
        save_path, _ = QFileDialog.getSaveFileName(self, "保存串联结果", "", "SRT Files (*.srt)")
        if save_path:
            combined.save(save_path)
            QMessageBox.information(self, "提示", "串联保存成功")

    def on_strip_text(self):
        count = self.file_list.count()
        if count == 0: return
        
        path = self.file_list.item(0).data(Qt.ItemDataRole.UserRole)
        if self.toolbox.load_file(path):
            full_text = self.toolbox.strip_timeline()
            # 简单展示摘要
            summary = full_text[:500] + "..." if len(full_text) > 500 else full_text
            QMessageBox.information(self, "提取成功前500字", summary)
            
            # 同时提供保存选项
            save_path, _ = QFileDialog.getSaveFileName(self, "保存纯文本", "", "Text Files (*.txt)")
            if save_path:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(full_text)

    def on_txt_to_srt(self):
        from PyQt6.QtWidgets import QApplication
        text = QApplication.clipboard().text()
        if not text:
            QMessageBox.warning(self, "提示", "剪贴板为空")
            return
        
        self.toolbox.txt_to_srt_smart(text)
        save_path, _ = QFileDialog.getSaveFileName(self, "保存生成结果", "", "SRT Files (*.srt)")
        if save_path:
            self.toolbox.save_file(save_path)
            QMessageBox.information(self, "提示", "转换保存成功")
