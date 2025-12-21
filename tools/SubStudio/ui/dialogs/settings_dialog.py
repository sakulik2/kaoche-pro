from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, 
    QGroupBox, QRadioButton, QLabel, QLineEdit, QPushButton, 
    QComboBox, QFileDialog, QMessageBox, QTableWidget, 
    QHeaderView, QTableWidgetItem, QCheckBox
)
from PyQt6.QtCore import Qt
from ...core.model_manager import ModelManager 

class SubStudioSettingsDialog(QDialog):
    """
    SubStudio 全局设置对话框
    包含: 常规, AI 配置 (Model Manager), 快捷键等
    """
    def __init__(self, model_manager: ModelManager, parent=None):
        super().__init__(parent)
        self.manager = model_manager
        self.setWindowTitle("设置 (Settings) - SubStudio")
        self.resize(800, 500)
        
        self.init_ui()
        
        # 信号
        self.manager.download_progress.connect(self.on_download_progress)
        self.manager.download_finished.connect(self.on_download_finished)
        self.manager.model_list_changed.connect(self.refresh_model_list)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # 1. 常规设置 (General)
        self.tab_general = QWidget()
        self._init_general_tab()
        self.tabs.addTab(self.tab_general, "常规 (General)")
        
        # 2. AI 配置 (AI Strategy)
        self.tab_ai = QWidget()
        self._init_ai_tab()
        self.tabs.addTab(self.tab_ai, "AI 引擎 (AI Strategy)")
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_close = QPushButton("关闭 (Close)")
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_close)
        
        main_layout.addLayout(btn_layout)

    def _init_general_tab(self):
        layout = QVBoxLayout(self.tab_general)
        layout.addWidget(QLabel("常规设置暂未开放 (Coming Soon)"))
        layout.addStretch()

    def _init_ai_tab(self):
        layout = QVBoxLayout(self.tab_ai)
        
        # A. 模型来源策略 (Model Loading Strategy)
        group_strategy = QGroupBox("转写配置 (Transcription Settings)")
        strat_layout = QVBoxLayout(group_strategy)
        
        # A1. 模型选择
        strat_layout.addWidget(QLabel("AI 模型 (Select AI Model):"))
        source_layout = QHBoxLayout()
        self.combo_source = QComboBox()
        self.combo_source.setMinimumWidth(300)
        self.combo_source.currentIndexChanged.connect(self.on_source_changed)
        source_layout.addWidget(self.combo_source)
        
        self.btn_refresh = QPushButton("刷新 (Refresh)")
        self.btn_refresh.clicked.connect(self.refresh_model_sources)
        source_layout.addWidget(self.btn_refresh)
        strat_layout.addLayout(source_layout)
        
        self.lbl_path_info = QLabel("当前路径: <Auto>")
        self.lbl_path_info.setStyleSheet("color: gray; font-size: 11px;")
        strat_layout.addWidget(self.lbl_path_info)
        
        strat_layout.addSpacing(10)
        
        # A2. 语言选择
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("识别语言 (Language):"))
        self.combo_lang = QComboBox()
        self.combo_lang.addItem("自动检测 (Auto)", None)
        self.combo_lang.addItem("简体中文 (Chinese)", "zh")
        self.combo_lang.addItem("英语 (English)", "en")
        self.combo_lang.addItem("日语 (Japanese)", "ja")
        self.combo_lang.addItem("韩语 (Korean)", "ko")
        self.combo_lang.addItem("粤语 (Cantonese)", "yue")
        self.combo_lang.addItem("法语 (French)", "fr")
        self.combo_lang.addItem("德语 (German)", "de")
        self.combo_lang.addItem("西班牙语 (Spanish)", "es")
        self.combo_lang.addItem("俄语 (Russian)", "ru")
        
        # 加载保存的设置
        from PyQt6.QtCore import QSettings
        settings = QSettings("KaochePro", "SubStudio")
        saved_lang = settings.value("transcription_lang", None)
        for i in range(self.combo_lang.count()):
            if self.combo_lang.itemData(i) == saved_lang:
                self.combo_lang.setCurrentIndex(i)
                break
        
        self.combo_lang.currentIndexChanged.connect(self.on_lang_changed)
        lang_layout.addWidget(self.combo_lang)
        lang_layout.addStretch()
        strat_layout.addLayout(lang_layout)
        
        strat_layout.addSpacing(5)
        
        # A3. 自定义提示词 (Custom Prompt)
        prompt_layout = QVBoxLayout()
        lbl_prompt = QLabel("引导提示词 (Initial Prompt - 可选):")
        lbl_prompt.setToolTip("输入一句话来引导 AI 的风格或指定话题。\n例如：'这是一段关于医学的中英双语对话。'")
        prompt_layout.addWidget(lbl_prompt)
        
        self.edit_prompt = QLineEdit()
        self.edit_prompt.setPlaceholderText("例如: English and German conversation. (留空则自动优化标点)")
        self.edit_prompt.setText(settings.value("transcription_prompt", ""))
        self.edit_prompt.textChanged.connect(self.on_prompt_changed)
        prompt_layout.addWidget(self.edit_prompt)
        strat_layout.addLayout(prompt_layout)

        layout.addWidget(group_strategy)
        
        # B. 内置模型下载管理
        group_download = QGroupBox("内置模型下载 (Download Built-in Models)")
        dl_layout = QVBoxLayout(group_download)
        
        # 源选择
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("下载源 (Download Source):"))
        self.radio_official = QRadioButton("官方源 (Hugging Face) [默认]") # 用户要求优先
        self.radio_mirror = QRadioButton("国内镜像 (hf-mirror)")
        self.radio_official.setChecked(True)
        
        source_layout.addWidget(self.radio_official)
        source_layout.addWidget(self.radio_mirror)
        source_layout.addStretch()
        dl_layout.addLayout(source_layout)
        
        # 模型列表
        self.model_table = QTableWidget()
        self.model_table.setColumnCount(4)
        self.model_table.setHorizontalHeaderLabels(["模型", "大小", "说明", "状态"])
        header = self.model_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.model_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.model_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.model_table.itemSelectionChanged.connect(self.update_dl_buttons)
        
        dl_layout.addWidget(self.model_table)
        
        # 下载动作
        act_layout = QHBoxLayout()
        self.lbl_status = QLabel("就绪")
        
        self.btn_download = QPushButton("下载选中模型")
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self.start_download)
        
        act_layout.addWidget(self.lbl_status)
        act_layout.addStretch()
        act_layout.addWidget(self.btn_download)
        dl_layout.addLayout(act_layout)
        
        layout.addWidget(group_download)
        
        # 初始化列表
        self.refresh_model_list()
        self.refresh_model_sources()

    def refresh_model_sources(self):
        """刷新下拉框：自动 + 扫描到的本地模型 + 浏览"""
        current_selection = self.manager._custom_model_path
        
        self.combo_source.blockSignals(True)
        self.combo_source.clear()
        
        # 1. 默认项
        self.combo_source.addItem("自动管理 (Auto-managed Download)", None)
        
        # 2. 扫描本地模型
        local_models = self.manager.scan_local_models()
        for name, path in local_models:
            display_text = f"本地: {name}"
            self.combo_source.addItem(display_text, path)
            
        # 3. 如果当前选中的路径不在扫描列表中 (e.g. 外部路径)，添加它
        if current_selection:
            found = False
            for i in range(self.combo_source.count()):
                if self.combo_source.itemData(i) == current_selection:
                    self.combo_source.setCurrentIndex(i)
                    found = True
                    break
            
            if not found:
                self.combo_source.addItem(f"自定义: {current_selection}", current_selection)
                self.combo_source.setCurrentIndex(self.combo_source.count() - 1)
        else:
            self.combo_source.setCurrentIndex(0)

        # 4. 浏览选项
        self.combo_source.addItem("浏览其他路径 (Browse Custom Path)...", "BROWSE")
        
        self.combo_source.blockSignals(False)
        self.update_path_info()

    def on_source_changed(self, index):
        data = self.combo_source.itemData(index)
        
        if data == "BROWSE":
            # 触发浏览，如果取消则回滚
            dir_path = QFileDialog.getExistingDirectory(self, "选择模型文件夹 (包含 model.bin)")
            if dir_path:
                self.manager.set_custom_model_path(dir_path)
                self.refresh_model_sources() # 重新排版
            else:
                # 回滚到之前
                self.refresh_model_sources()
        else:
            # 设置路径 (None or path)
            self.manager.set_custom_model_path(data)
            self.update_path_info()
            
    def update_path_info(self):
        path = self.manager.get_model_path() # 获取最终生效路径
        if not path:
             self.lbl_path_info.setText("当前路径: <未就绪 - 请先下载或选择模型>")
        else:
             self.lbl_path_info.setText(f"当前路径: {path}")

    # Remove old toggle/browse methods
    # toggle_custom_path, browse_model_path removed

    def refresh_model_list(self):
        self.model_table.setRowCount(0)
        models = self.manager.get_supported_models()
        self.model_table.setRowCount(len(models))
        
        for row, model in enumerate(models):
            self.model_table.setItem(row, 0, QTableWidgetItem(model["name"]))
            self.model_table.setItem(row, 1, QTableWidgetItem(model["size"]))
            self.model_table.setItem(row, 2, QTableWidgetItem(model["desc"]))
            
            is_ready = self.manager.is_model_ready(model["id"])
            status = QTableWidgetItem("已下载" if is_ready else "未下载")
            status.setForeground(Qt.GlobalColor.darkGreen if is_ready else Qt.GlobalColor.gray)
            self.model_table.setItem(row, 3, status)
            
            self.model_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, model["id"])

    def update_dl_buttons(self):
        self.btn_download.setEnabled(len(self.model_table.selectedItems()) > 0)

    def start_download(self):
        items = self.model_table.selectedItems()
        if not items: return
        
        model_id = self.model_table.item(items[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        mirror_url = "https://hf-mirror.com" if self.radio_mirror.isChecked() else None
        
        # Lock UI
        self.btn_download.setEnabled(False)
        self.model_table.setEnabled(False)
        
        self.manager.download_model(model_id, mirror_url)

    def on_download_progress(self, msg):
        self.lbl_status.setText(msg)

    def on_download_finished(self, success, msg):
        self.model_table.setEnabled(True)
        self.update_dl_buttons()
        self.refresh_model_list()
        
        if success:
            QMessageBox.information(self, "成功", "下载完成")
            self.lbl_status.setText("下载完成")
        else:
            QMessageBox.critical(self, "失败", f"下载出错: {msg}")
    def on_lang_changed(self, index):
        lang = self.combo_lang.itemData(index)
        from PyQt6.QtCore import QSettings
        settings = QSettings("KaochePro", "SubStudio")
        settings.setValue("transcription_lang", lang)
        logger.info(f"Transcription language set to: {lang}")

    def on_prompt_changed(self, text):
        from PyQt6.QtCore import QSettings
        settings = QSettings("KaochePro", "SubStudio")
        settings.setValue("transcription_prompt", text)
