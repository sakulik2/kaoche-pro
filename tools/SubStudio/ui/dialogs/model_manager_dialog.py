from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QComboBox, QHeaderView, QMessageBox, QGroupBox, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt, QTimer
from ..core.model_manager import ModelManager

class ModelManagerDialog(QDialog):
    def __init__(self, model_manager: ModelManager, parent=None):
        super().__init__(parent)
        self.manager = model_manager
        self.setWindowTitle("AI 模型管理 (AI Model Manager)")
        self.resize(700, 450)
        
        self.init_ui()
        self.refresh_list()
        
        # 信号连接
        self.manager.download_progress.connect(self.on_download_progress)
        self.manager.download_finished.connect(self.on_download_finished)
        self.manager.model_list_changed.connect(self.refresh_list)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. 顶部：下载源选择
        source_group = QGroupBox("下载源设置 (Download Source)")
        source_layout = QHBoxLayout(source_group)
        
        self.btn_mirror = QRadioButton("使用国内镜像 (hf-mirror.com) - 推荐")
        self.btn_official = QRadioButton("使用官方源 (Hugging Face) - 需代理")
        self.btn_mirror.setChecked(True)
        
        source_layout.addWidget(self.btn_mirror)
        source_layout.addWidget(self.btn_official)
        source_layout.addStretch()
        
        layout.addWidget(source_group)
        
        # 2. 中部：模型列表
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["模型名称 (Name)", "大小 (Size)", "说明 (Description)", "状态 (Status)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self.update_buttons)
        
        layout.addWidget(self.table)
        
        # 3. 底部：操作栏
        action_layout = QHBoxLayout()
        
        self.lbl_status = QLabel("就绪")
        action_layout.addWidget(self.lbl_status)
        action_layout.addStretch()
        
        self.btn_download = QPushButton("下载选定模型 (Download)")
        self.btn_download.clicked.connect(self.start_download)
        self.btn_download.setEnabled(False)
        action_layout.addWidget(self.btn_download)
        
        self.btn_close = QPushButton("关闭 (Close)")
        self.btn_close.clicked.connect(self.accept)
        action_layout.addWidget(self.btn_close)
        
        layout.addLayout(action_layout)

    def refresh_list(self):
        """刷新模型列表状态"""
        self.table.setRowCount(0)
        models = self.manager.get_supported_models()
        self.table.setRowCount(len(models))
        
        for row, model in enumerate(models):
            # Name
            self.table.setItem(row, 0, QTableWidgetItem(model["name"]))
            # Size
            self.table.setItem(row, 1, QTableWidgetItem(model["size"]))
            # Desc
            self.table.setItem(row, 2, QTableWidgetItem(model["desc"]))
            
            # Status
            is_ready = self.manager.is_model_ready(model["id"])
            status_text = "✅ 已下载 (Ready)" if is_ready else "未下载"
            status_item = QTableWidgetItem(status_text)
            if is_ready:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                status_item.setForeground(Qt.GlobalColor.gray)
            self.table.setItem(row, 3, status_item)
            
            # 存储 model_id 到第一列 item 的 data
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, model["id"])
            
    def update_buttons(self):
        selected = self.table.selectedItems()
        self.btn_download.setEnabled(len(selected) > 0)

    def start_download(self):
        row = self.table.currentRow()
        if row < 0: return
        
        model_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        model_name = self.table.item(row, 0).text()
        
        if self.manager.is_model_ready(model_id):
            # TODO: 允许重新下载或删除？
            reply = QMessageBox.question(self, "确认", f"模型 '{model_name}' 已存在，是否重新下载？", 
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                return

        # 确定源
        mirror_url = "https://hf-mirror.com" if self.btn_mirror.isChecked() else None
        
        self.lbl_status.setText(f"正在准备下载 {model_name}...")
        self.table.setEnabled(False) # 锁定 UI
        self.btn_download.setEnabled(False)
        self.btn_mirror.setEnabled(False)
        self.btn_official.setEnabled(False)
        
        success = self.manager.download_model(model_id, mirror_url)
        if not success:
            QMessageBox.warning(self, "警告", "已有下载任务正在进行中")
            self.unlock_ui()

    def on_download_progress(self, msg):
        self.lbl_status.setText(msg)

    def on_download_finished(self, success, result):
        self.unlock_ui()
        self.refresh_list()
        
        if success:
            QMessageBox.information(self, "下载成功", f"模型下载完成！\n路径: {result}")
        else:
            QMessageBox.critical(self, "下载失败", f"错误: {result}")
            self.lbl_status.setText("下载失败")

    def unlock_ui(self):
        self.table.setEnabled(True)
        self.btn_mirror.setEnabled(True)
        self.btn_official.setEnabled(True)
        self.update_buttons()
