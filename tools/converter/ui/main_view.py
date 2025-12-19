import os
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QComboBox, QCheckBox, QProgressBar,
    QFileDialog, QMessageBox, QFrame, QAbstractItemView
)
from PyQt6.QtCore import Qt, QMimeData
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

logger = logging.getLogger(__name__)

class ConverterMainView(QWidget):
    """字幕格式转换器主视图"""
    def __init__(self, hub, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.setAcceptDrops(True)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 头部操作栏
        self.setStyleSheet("""
            QPushButton {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 6px 15px;
                font-size: 13px;
                font-weight: 500;
                color: #374151;
            }
            QPushButton:hover {
                background-color: #f9fafb;
                border: 1px solid #9ca3af;
            }
            QPushButton#PrimaryBtn {
                background-color: #2563eb;
                color: white;
                border: 1px solid #1d4ed8;
            }
            QPushButton#PrimaryBtn:hover {
                background-color: #1d4ed8;
            }
            QListWidget {
                border: 1px solid #d1d5db;
                border-radius: 4px;
                background-color: #ffffff;
            }
            #ParamGroup {
                background-color: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 4px;
                padding: 10px;
            }
        """)

        top_bt_layout = QHBoxLayout()
        self.btn_add = QPushButton("添加文件...")
        self.btn_add.clicked.connect(self.on_add_files)
        top_bt_layout.addWidget(self.btn_add)
        
        self.btn_clear = QPushButton("清空列表")
        self.btn_clear.clicked.connect(lambda: self.file_list.clear())
        top_bt_layout.addWidget(self.btn_clear)
        
        top_bt_layout.addStretch()
        layout.addLayout(top_bt_layout)

        # 文件列表
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.file_list, 1)

        # 参数配置栏
        param_widget = QFrame()
        param_widget.setObjectName("ParamGroup")
        param_layout = QVBoxLayout(param_widget)
        param_layout.setSpacing(12)
        
        # 行 1: 格式与编码
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("目标格式:"))
        self.target_ext = QComboBox()
        self.target_ext.addItems([".srt", ".ass", ".vtt", ".xlsx", ".txt"])
        row1.addWidget(self.target_ext)
        
        row1.addSpacing(20)
        row1.addWidget(QLabel("输出编码:"))
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(["UTF-8", "GB18030", "UTF-16", "Big5"])
        row1.addWidget(self.encoding_combo)
        
        row1.addSpacing(20)
        self.chk_strip = QCheckBox("清除 ASS 样式")
        self.chk_strip.setChecked(True)
        row1.addWidget(self.chk_strip)
        row1.addStretch()
        param_layout.addLayout(row1)

        # 行 2: 保存位置
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("保存位置:"))
        self.output_mode = QComboBox()
        self.output_mode.addItems(["与源文件相同", "自定义目录..."])
        self.output_mode.currentIndexChanged.connect(self.on_output_mode_changed)
        row2.addWidget(self.output_mode)
        
        self.custom_path_label = QLabel("")
        self.custom_path_label.setStyleSheet("color: #64748b; font-size: 11px;")
        self.custom_path_label.setVisible(False)
        row2.addWidget(self.custom_path_label)
        
        row2.addStretch()
        
        self.btn_open_folder = QPushButton("📂 打开输出文件夹")
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self.on_open_output_folder)
        row2.addWidget(self.btn_open_folder)
        
        self.btn_start = QPushButton("🚀 开始批量转换")
        self.btn_start.setObjectName("PrimaryBtn")
        self.btn_start.clicked.connect(self.start_conversion)
        row2.addWidget(self.btn_start)
        
        param_layout.addLayout(row2)
        layout.addWidget(param_widget)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        for url in urls:
            path = url.toLocalFile()
            if os.path.isfile(path):
                self.add_file_item(path)

    def on_add_files(self):
        last_dir = ""
        if self.hub and self.hub.history:
            last_dir = self.hub.history.get_last_dir('subtitle')

        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择字幕文件", last_dir, "Subtitle Files (*.srt *.ass *.vtt *.txt *.xlsx);;All Files (*)"
        )
        for p in paths:
            if self.hub and self.hub.history:
                self.hub.history.set_last_dir('subtitle', p)
            self.add_file_item(p)

    def add_file_item(self, path):
        # 简单避免重复
        for i in range(self.file_list.count()):
            if self.file_list.item(i).data(Qt.ItemDataRole.UserRole) == path:
                return
        
        item = QListWidgetItem(os.path.basename(path))
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        self.file_list.addItem(item)

    def on_output_mode_changed(self, index):
        if index == 1: # 自定义目录
            last_dir = ""
            if self.hub and self.hub.history:
                last_dir = self.hub.history.get_last_dir('output')
                
            path = QFileDialog.getExistingDirectory(self, "选择输出目录", last_dir)
            if path:
                if self.hub and self.hub.history:
                    self.hub.history.set_last_dir('output', path)
                self.custom_path_label.setText(path)
                self.custom_path_label.setVisible(True)
            else:
                self.output_mode.setCurrentIndex(0)
        else:
            self.custom_path_label.setVisible(False)

    def on_open_output_folder(self):
        folder = ""
        if self.output_mode.currentIndex() == 1:
            folder = self.custom_path_label.text()
        elif self.file_list.count() > 0:
            first_path = self.file_list.item(0).data(Qt.ItemDataRole.UserRole)
            folder = os.path.dirname(first_path)
            
        if folder and os.path.exists(folder):
            import subprocess
            if os.name == 'nt':
                os.startfile(folder)
            else:
                subprocess.run(['xdg-open', folder])

    def start_conversion(self):
        count = self.file_list.count()
        if count == 0:
            QMessageBox.warning(self, "提示", "请先添加文件")
            return

        target_ext = self.target_ext.currentText()
        encoding = self.encoding_combo.currentText()
        strip_styles = self.chk_strip.isChecked()
        
        custom_dir = self.custom_path_label.text() if self.output_mode.currentIndex() == 1 else None

        self.progress_bar.setMaximum(count)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.btn_start.setEnabled(False)
        
        success = 0
        errors = []
        
        for i in range(count):
            src_path = self.file_list.item(i).data(Qt.ItemDataRole.UserRole)
            try:
                # 计算输出路径
                if custom_dir:
                    base = os.path.splitext(os.path.basename(src_path))[0]
                    dst_path = os.path.join(custom_dir, base + target_ext)
                else:
                    base = os.path.splitext(src_path)[0]
                    dst_path = base + target_ext
                
                self.convert_one(src_path, dst_path, encoding, strip_styles)
                success += 1
            except Exception as e:
                errors.append(f"{os.path.basename(src_path)}: {str(e)}")
            self.progress_bar.setValue(i + 1)
        
        self.progress_bar.setVisible(False)
        self.btn_start.setEnabled(True)
        self.btn_open_folder.setVisible(True)
        
        if errors:
            err_msg = "\n".join(errors[:5]) + ("\n..." if len(errors) > 5 else "")
            QMessageBox.warning(self, "转换完成", f"成功: {success}\n失败: {len(errors)}\n\n错误详情:\n{err_msg}")
        else:
            QMessageBox.information(self, "转换完成", f"已成功处理 {success} 个文件")

    def convert_one(self, src_path, dst_path, encoding, strip_styles):
        """核心转换逻辑"""
        from ..logic.engine import convert_subtitle
        convert_subtitle(src_path, dst_path, encoding, strip_styles)
