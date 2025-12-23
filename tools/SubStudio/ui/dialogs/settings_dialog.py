from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, 
    QGroupBox, QRadioButton, QLabel, QLineEdit, QPushButton, 
    QComboBox, QFileDialog, QMessageBox, QTableWidget, 
    QHeaderView, QTableWidgetItem, QCheckBox, QFormLayout, QSpinBox,
    QListWidget, QTextEdit
)
from PyQt6.QtCore import Qt
import os
import logging
from ...core.model_manager import ModelManager 
from core.utils.config_manager import get_config_manager

class SubStudioSettingsDialog(QDialog):
    """
    SubStudio 全局设置对话框
    包含: 常规, AI 配置 (Model Manager), 快捷键等
    """
    def __init__(self, model_manager: ModelManager, parent=None):
        super().__init__(parent)
        self.manager = model_manager
        self.setWindowTitle("设置 - SubStudio")
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
        
        # 1. 语音生成
        self.tab_ai = QWidget()
        self._init_ai_tab()
        self.tabs.addTab(self.tab_ai, "语音生成")
        
        # 2. 文本翻译
        self.tab_translate = self._init_translate_tab()
        self.tabs.addTab(self.tab_translate, "文本翻译")
        
        # 3. 提示词管理 (LQA 同款)
        self.tab_prompt = self._init_prompt_tab()
        self.tabs.addTab(self.tab_prompt, "提示词管理")
        
        # 4. 常规设置
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_close)
        
        main_layout.addLayout(btn_layout)

    def _init_translate_tab(self):
        """文本翻译设置页"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 15, 20, 15)
        
        group = QGroupBox("AI 翻译引擎配置")
        form = QFormLayout(group)
        
        # API 服务商
        prov_layout = QHBoxLayout()
        self.combo_trans_provider = QComboBox()
        self.trans_providers = {}
        try:
            from core.api.api_client import load_providers_config
            self.trans_providers = load_providers_config()
            for pid, cfg in self.trans_providers.items():
                self.combo_trans_provider.addItem(cfg.get('display_name', pid), pid)
        except:
            pass
            
        prov_layout.addWidget(self.combo_trans_provider, 1)
        self.btn_manage_prov = QPushButton("管理...")
        self.btn_manage_prov.clicked.connect(self.on_provider_manage)
        prov_layout.addWidget(self.btn_manage_prov)
        form.addRow("API 服务商", prov_layout)
        
        # API 密钥
        self.edit_trans_key = QLineEdit()
        self.edit_trans_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_trans_key.setPlaceholderText("输入 API Key")
        self.edit_trans_key.editingFinished.connect(self.on_trans_key_edited)
        form.addRow("API 密钥", self.edit_trans_key)
        
        # 模型选择
        model_layout = QHBoxLayout()
        self.combo_trans_model = QComboBox()
        self.combo_trans_model.setEditable(True)
        self.combo_trans_model.currentTextChanged.connect(self.on_trans_model_changed)
        model_layout.addWidget(self.combo_trans_model, 1)
        
        self.btn_refresh_models = QPushButton("🔄 刷新")
        self.btn_refresh_models.clicked.connect(self.refresh_trans_models)
        model_layout.addWidget(self.btn_refresh_models)
        form.addRow("模型名称", model_layout)
        
        # 接口地址
        self.edit_trans_base = QLineEdit()
        self.edit_trans_base.setPlaceholderText("默认地址")
        self.edit_trans_base.editingFinished.connect(self.on_trans_base_edited)
        form.addRow("接口地址", self.edit_trans_base)
        
        # 目标语言
        self.combo_trans_target = QComboBox()
        lang_opts = [("简体中文", "zh"), ("英语", "en"), ("日语", "ja"), ("德语", "de"), ("法语", "fr")]
        for text, val in lang_opts:
            self.combo_trans_target.addItem(text, val)
        self.combo_trans_target.currentIndexChanged.connect(self.on_trans_target_changed)
        form.addRow("目标语言", self.combo_trans_target)
        
        # 批处理数量
        self.spin_trans_batch = QSpinBox()
        self.spin_trans_batch.setRange(1, 100)
        self.spin_trans_batch.setValue(12)
        self.spin_trans_batch.valueChanged.connect(self.on_trans_batch_changed)
        form.addRow("每批翻译条数", self.spin_trans_batch)

        layout.addWidget(group)
        
        # 测试按钮
        test_btn_layout = QHBoxLayout()
        test_btn_layout.addStretch()
        
        self.btn_test_trans = QPushButton("测试 API 连接")
        self.btn_test_trans.setObjectName("primaryButton")
        self.btn_test_trans.clicked.connect(self.on_test_translation)
        test_btn_layout.addWidget(self.btn_test_trans)
        
        layout.addLayout(test_btn_layout)
        layout.addStretch()
        
        # 初始化监听
        self.combo_trans_provider.currentIndexChanged.connect(self.on_trans_provider_changed)
        
        # 初始化值
        self._load_trans_settings()
        
        return page

    def _load_trans_settings(self):
        cm = get_config_manager()
        config = cm.load()
        
        # 1. 优先设置 Provider
        api_cfg = config.get('api', {})
        provider = api_cfg.get("provider", "openai")
        idx = self.combo_trans_provider.findData(provider)
        if idx >= 0:
            self.combo_trans_provider.blockSignals(True)
            self.combo_trans_provider.setCurrentIndex(idx)
            self.on_trans_provider_changed(idx, is_loading=True) # 传入 loading 标记
            self.combo_trans_provider.blockSignals(False)
        
        # 2. 回填持久化数据 (如有)
        # API Key (针对当前 Provider 进行加载，符合 LQA 逻辑)
        self.edit_trans_key.setText(cm.get_api_key(cm.password, provider_id=provider) or "")
        
        # Base URL
        self.edit_trans_base.setText(api_cfg.get("base_url", ""))
        
        # Model
        saved_model = api_cfg.get("model", "")
        if saved_model: self.combo_trans_model.setCurrentText(saved_model)
        
        # Target Lang
        ui_cfg = config.get('ui', {})
        target = ui_cfg.get("target_language", "zh")
        for i in range(self.combo_trans_target.count()):
            if self.combo_trans_target.itemData(i) == target:
                self.combo_trans_target.setCurrentIndex(i)
                break
                
        # Batch Size
        trans_cfg = config.get('translation', {})
        self.spin_trans_batch.setValue(int(trans_cfg.get("batch_size", 12)))

    def on_trans_provider_changed(self, index, is_loading=False):
        pid = self.combo_trans_provider.itemData(index)
        cfg = self.trans_providers.get(pid, {})
        
        # A. 联动更新模型列表
        self.combo_trans_model.blockSignals(True)
        self.combo_trans_model.clear()
        self.combo_trans_model.addItems(cfg.get('models', []))
        self.combo_trans_model.blockSignals(False)
        
        # B. 联动更新地址与密钥 (LQA 逻辑)
        cm = get_config_manager()
        if not is_loading:
            # 自动切换为官方推荐地址
            self.edit_trans_base.setText(cfg.get('base_url', ""))
            # 自动加载该服务商对应的 API Key
            self.edit_trans_key.setText(cm.get_api_key(cm.password, provider_id=pid) or "")
            
            # 保存服务商选择
            config = cm.load()
            if 'api' not in config: config['api'] = {}
            config['api']['provider'] = pid
            config['api']['base_url'] = cfg.get('base_url', "")
            cm.save(config)
        else:
            # 即使是加载，也要确保 Key 是针对该 Provider 的
            self.edit_trans_key.setText(cm.get_api_key(cm.password, provider_id=pid) or "")

    # --- 翻译页具体保存槽函数 (参考 LQA) ---
    def on_trans_key_edited(self):
        cm = get_config_manager()
        pid = self.combo_trans_provider.itemData(self.combo_trans_provider.currentIndex())
        cm.set_api_key(self.edit_trans_key.text(), cm.password, provider_id=pid)
        cm.save(cm.config)

    def on_provider_manage(self):
        try:
            from ui.shared.settings_dialog import ProviderManagerDialog
            dialog = ProviderManagerDialog(self)
            dialog.exec()
            # 管理完可能影响了模型列表，刷新一下配置
            from core.api.api_client import load_providers_config
            self.trans_providers = load_providers_config()
            # 触发一次刷新
            self.on_trans_provider_changed(self.combo_trans_provider.currentIndex())
        except Exception as e:
            QMessageBox.warning(self, "出错", f"无法打开管理对话框: {e}")

    def refresh_trans_models(self):
        provider_id = self.combo_trans_provider.itemData(self.combo_trans_provider.currentIndex())
        api_key = self.edit_trans_key.text().strip()
        if not api_key:
            QMessageBox.warning(self, "错误", "请先输入 API Key。")
            return
            
        self.btn_refresh_models.setEnabled(False)
        self.btn_refresh_models.setText("刷新中...")
        
        def do_refresh():
            try:
                from core.api.api_client import get_models_with_cache
                config = self.trans_providers.get(provider_id, {})
                models = get_models_with_cache(provider_id, config, api_key)
                return True, models
            except Exception as e:
                return False, str(e)

        from PyQt6.QtCore import QThread, pyqtSignal
        class RefreshThread(QThread):
            finished = pyqtSignal(bool, object)
            def run(self):
                ok, res = do_refresh()
                self.finished.emit(ok, res)

        self._refresh_thread = RefreshThread()
        def on_done(ok, res):
            self.btn_refresh_models.setEnabled(True)
            self.btn_refresh_models.setText("🔄 刷新")
            if ok:
                self.combo_trans_model.clear()
                self.combo_trans_model.addItems(res)
                
                # 持久化抓取到的模型列表
                try:
                    from core.api.api_client import save_providers_config
                    if provider_id in self.trans_providers:
                        self.trans_providers[provider_id]['models'] = res
                        save_providers_config(self.trans_providers)
                except Exception as e:
                    logger.error(f"保存抓取的模型列表失败: {e}")

                QMessageBox.information(self, "刷新成功", f"已从服务器获取并同步 {len(res)} 个可用模型。")
            else:
                QMessageBox.warning(self, "刷新失败", f"无法获取模型列表: {res}")
        
        self._refresh_thread.finished.connect(on_done)
        self._refresh_thread.start()

    def on_trans_base_edited(self):
        cm = get_config_manager()
        config = cm.load()
        if 'api' not in config: config['api'] = {}
        config['api']['base_url'] = self.edit_trans_base.text()
        cm.save(config)

    def on_trans_model_changed(self, text):
        cm = get_config_manager()
        config = cm.load()
        if 'api' not in config: config['api'] = {}
        config['api']['model'] = text
        cm.save(config)

    def on_trans_target_changed(self, index):
        cm = get_config_manager()
        config = cm.load()
        if 'ui' not in config: config['ui'] = {}
        val = self.combo_trans_target.itemData(index)
        config['ui']['target_language'] = val
        cm.save(config)

    def on_trans_batch_changed(self, val):
        cm = get_config_manager()
        config = cm.load()
        if 'translation' not in config: config['translation'] = {}
        config['translation']['batch_size'] = val
        cm.save(config)

    def on_test_translation(self):
        # 1. 获取当前临时配置 (确保未保存的内容也能测试)
        cm = get_config_manager()
        config = cm.load()
        api_cfg = config.get('api', {}).copy() # 拷贝一份
        
        # 覆盖为当前 UI 上的值
        prov_id = self.combo_trans_provider.itemData(self.combo_trans_provider.currentIndex())
        from core.api.api_client import load_providers_config, APIClient
        providers = load_providers_config()
        p_cfg = providers.get(prov_id, {"id": prov_id, "api_type": "openai"}).copy()
        
        key = self.edit_trans_key.text()
        model = self.combo_trans_model.currentText()
        base = self.edit_trans_base.text()
        target_lang = self.combo_trans_target.currentText()
        
        if not key:
            QMessageBox.warning(self, "测试失败", "请输入 API 密钥。")
            return
            
        if base: p_cfg['base_url'] = base
        
        client = APIClient(p_cfg, key, model)
        
        # 2. 模拟请求
        self.btn_test_trans.setEnabled(False)
        self.btn_test_trans.setText("测试中...")
        
        test_text = "Hello! This is a translation test for SubStudio."
        
        # 构建一个极简 prompt (剥离自 Worker)
        import os, json
        from core.utils.utils import get_project_root
        prompt_path = os.path.join(get_project_root(), 'config', 'prompts', 'substudio_translate_en.txt')
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_tpl = f.read()
        except:
            prompt_tpl = "Translate to {target_lang}: {lines_json}"

        prompt = prompt_tpl.format(
            target_lang=target_lang,
            lines_json=json.dumps([test_text], ensure_ascii=False),
            context_text="(None)"
        )
        
        def do_test():
            try:
                # 兼容 System/User 隔离
                response = client.generate_content(
                    system_prompt="你是一个翻译助手。",
                    user_prompt=prompt,
                    json_mode=True
                )
                
                # 鲁棒解析
                from core.utils.llm_utils import parse_json_from_response
                data = parse_json_from_response(response['text'])
                
                if data and isinstance(data, dict):
                    result = data.get("translated", ["无内容"])[0]
                elif isinstance(data, list) and data:
                    result = data[0]
                else:
                    result = "解析失败"
                return True, result
            except Exception as e:
                return False, str(e)

        # 简单的线程执行 (防止阻塞 UI)
        from PyQt6.QtCore import QThread, pyqtSignal
        class TestThread(QThread):
            finished = pyqtSignal(bool, str)
            def run(self):
                ok, res = do_test()
                self.finished.emit(ok, res)
        
        self._test_thread = TestThread()
        def on_test_done(ok, res):
            self.btn_test_trans.setEnabled(True)
            self.btn_test_trans.setText("测试 API 连接")
            if ok:
                QMessageBox.information(self, "测试成功", f"原文: {test_text}\n\n译文: {res}")
            else:
                QMessageBox.critical(self, "测试失败", f"错误详情:\n{res}")
        
        self._test_thread.finished.connect(on_test_done)
        self._test_thread.start()

    def _init_general_tab(self):
        layout = QVBoxLayout(self.tab_general)
        layout.addWidget(QLabel("常规设置暂未开放 (Coming Soon)"))
        layout.addStretch()

    def _init_ai_tab(self):
        layout = QVBoxLayout(self.tab_ai)
        
        # A. 模型来源策略
        group_strategy = QGroupBox("转写配置")
        strat_layout = QVBoxLayout(group_strategy)
        
        # A0. 推理引擎
        strat_layout.addWidget(QLabel("推理引擎"))
        self.combo_engine = QComboBox()
        self.combo_engine.addItem("WhisperX (Faster-Whisper)", "whisper")
        self.combo_engine.addItem("Sherpa-ONNX (Parakeet)", "sherpa")
        
        # Load engine config
        cm = get_config_manager()
        config = cm.load()
        transcription_cfg = config.get('transcription', {})
        current_engine = transcription_cfg.get('engine', 'whisper')
        
        idx = self.combo_engine.findData(current_engine)
        if idx >= 0: self.combo_engine.setCurrentIndex(idx)
        
        self.combo_engine.currentIndexChanged.connect(self.on_engine_changed)
        strat_layout.addWidget(self.combo_engine)
        
        strat_layout.addSpacing(5)

        # A1. 模型选择
        strat_layout.addWidget(QLabel("AI 模型"))
        source_layout = QHBoxLayout()
        self.combo_source = QComboBox()
        self.combo_source.setMinimumWidth(300)
        self.combo_source.currentIndexChanged.connect(self.on_source_changed)
        source_layout.addWidget(self.combo_source)
        
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh_model_sources)
        source_layout.addWidget(self.btn_refresh)
        strat_layout.addLayout(source_layout)
        
        self.lbl_path_info = QLabel("当前路径: <Auto>")
        self.lbl_path_info.setStyleSheet("color: gray; font-size: 11px;")
        strat_layout.addWidget(self.lbl_path_info)
        
        strat_layout.addSpacing(10)
        
        # A2. 语言选择
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("识别语言"))
        self.combo_lang = QComboBox()
        self.combo_lang.addItem("自动检测", None)
        self.combo_lang.addItem("简体中文", "zh")
        self.combo_lang.addItem("英语", "en")
        self.combo_lang.addItem("日语", "ja")
        self.combo_lang.addItem("韩语", "ko")
        self.combo_lang.addItem("粤语", "yue")
        self.combo_lang.addItem("法语", "fr")
        self.combo_lang.addItem("德语", "de")
        self.combo_lang.addItem("西班牙语", "es")
        self.combo_lang.addItem("俄语", "ru")
        
        # 加载保存的设置
        cm = get_config_manager()
        config = cm.load()
        transcription_cfg = config.get('transcription', {})
        
        saved_lang = transcription_cfg.get("language", None)
        for i in range(self.combo_lang.count()):
            if self.combo_lang.itemData(i) == saved_lang:
                self.combo_lang.setCurrentIndex(i)
                break
        
        self.combo_lang.currentIndexChanged.connect(self.on_lang_changed)
        lang_layout.addWidget(self.combo_lang)
        
        self.chk_vad = QCheckBox("语音活动检测")
        self.chk_vad.setToolTip("使用 WhisperX 优化的 VAD 流程（基于 Silero/Pyannote），在转写前自动过滤静音片段，大幅提升准确率并减少幻听。")
        self.chk_vad.setChecked(transcription_cfg.get("vad_filter", True))
        self.chk_vad.stateChanged.connect(self.on_vad_changed)
        lang_layout.addSpacing(15)
        lang_layout.addWidget(self.chk_vad)
        
        lang_layout.addStretch()
        strat_layout.addLayout(lang_layout)
        
        strat_layout.addSpacing(5)
        
        # A3. 自定义提示词
        prompt_layout = QVBoxLayout()
        lbl_prompt = QLabel("引导提示词")
        lbl_prompt.setToolTip("输入一句话来引导 AI 的风格或指定话题。\n例如：'这是一段关于医学的中英双语对话。'")
        prompt_layout.addWidget(lbl_prompt)
        
        self.edit_prompt = QLineEdit()
        self.edit_prompt.setPlaceholderText("例如: English and German conversation. (留空则自动优化标点)")
        self.edit_prompt.setText(transcription_cfg.get("prompt", ""))
        self.edit_prompt.editingFinished.connect(self.on_prompt_edited) # 改用 edited 减少保存频率
        prompt_layout.addWidget(self.edit_prompt)
        strat_layout.addLayout(prompt_layout)

        layout.addWidget(group_strategy)
        
        # B. 内置模型下载管理
        group_download = QGroupBox("内置模型下载")
        dl_layout = QVBoxLayout(group_download)
        
        # 源选择
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("下载源"))
        self.radio_official = QRadioButton("官方源") # 用户要求优先
        self.radio_mirror = QRadioButton("国内镜像")
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
        self.combo_source.addItem("自动管理", None)
        
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
        self.combo_source.addItem("浏览其他路径...", "BROWSE")
        
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
             
    def on_engine_changed(self, index):
        engine = self.combo_engine.itemData(index)
        # Save config
        cm = get_config_manager()
        cm.update_config("transcription", {"engine": engine})
        
        # Refresh lists
        self.refresh_model_sources()
        self.refresh_model_list()

    # Remove old toggle/browse methods
    # toggle_custom_path, browse_model_path removed

    def refresh_model_list(self):
        self.model_table.setRowCount(0)
        all_models = self.manager.get_supported_models()
        
        # Filter by current engine
        current_engine = self.combo_engine.currentData()
        models = [m for m in all_models if m.get("type", "whisper") == current_engine]
        
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
        
        # Init Queue
        self._download_queue = [model_id]
        
        # If Sherpa model, also queue punctuation model if not ready
        if "sherpa" in model_id.lower() or "parakeet" in model_id.lower():
            PUNCT_ID = "sherpa-onnx-punct-ct-transformer-zh-en-vocabulary-2023-04-12"
            if not self.manager.is_model_ready(PUNCT_ID):
                 self._download_queue.append(PUNCT_ID)
                 
        self.process_download_queue()
        
    def process_download_queue(self):
        if not hasattr(self, '_download_queue') or not self._download_queue:
            return

        next_id = self._download_queue[0] # Peek
        mirror_url = "https://hf-mirror.com" if self.radio_mirror.isChecked() else None
        
        # Lock UI
        self.btn_download.setEnabled(False)
        self.model_table.setEnabled(False)
        self.lbl_status.setText(f"准备下载: {next_id} ...")
        
        self.manager.download_model(next_id, mirror_url)

    def on_download_progress(self, msg):
        self.lbl_status.setText(msg)

    def on_download_finished(self, success, msg):
        # Pop current
        if hasattr(self, '_download_queue') and self._download_queue:
            finished_id = self._download_queue.pop(0)
            
            if not success:
                 QMessageBox.warning(self, "下载失败", f"模型 {finished_id} 下载失败:\n{msg}")
                 self._download_queue = [] # Clear queue on error
            
             # Process next
            if self._download_queue:
                 self.lbl_status.setText("正在下载关联模型 (标点)...")
                 self.process_download_queue()
                 return

        self.model_table.setEnabled(True)
        self.update_dl_buttons()
        self.refresh_model_list()
        
        if success:
            QMessageBox.information(self, "成功", "下载完成")
            self.lbl_status.setText("下载完成")
        else:
             self.lbl_status.setText("下载失败")
    def on_lang_changed(self, index):
        lang = self.combo_lang.itemData(index)
        cm = get_config_manager()
        config = cm.load()
        if 'transcription' not in config: config['transcription'] = {}
        config['transcription']['language'] = lang
        cm.save(config)

    def on_prompt_edited(self):
        cm = get_config_manager()
        config = cm.load()
        if 'transcription' not in config: config['transcription'] = {}
        config['transcription']['prompt'] = self.edit_prompt.text()
        cm.save(config)

    def on_vad_changed(self, state):
        cm = get_config_manager()
        config = cm.load()
        if 'transcription' not in config: config['transcription'] = {}
        val = (state == Qt.CheckState.Checked or state == 2) # Handle both enum and int
        config['transcription']['vad_filter'] = val
        cm.save(config)

    def _init_prompt_tab(self):
        """提示词管理页 (LQA 同款)"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 15, 20, 15)
        
        # 列表
        list_group = QGroupBox("提示词预设 (Presets)")
        list_layout = QVBoxLayout(list_group)
        
        self.prompt_list = QListWidget()
        self.prompt_list.currentRowChanged.connect(self.on_prompt_selected)
        list_layout.addWidget(self.prompt_list)
        
        btn_layout = QHBoxLayout()
        self.btn_prompt_new = QPushButton("➕ 新建")
        self.btn_prompt_new.clicked.connect(self.on_prompt_add)
        btn_layout.addWidget(self.btn_prompt_new)
        
        self.btn_prompt_edit = QPushButton("✏️ 编辑")
        self.btn_prompt_edit.clicked.connect(self.on_prompt_modify)
        btn_layout.addWidget(self.btn_prompt_edit)
        
        self.btn_prompt_delete = QPushButton("🗑️ 删除")
        self.btn_prompt_delete.clicked.connect(self.on_prompt_remove)
        btn_layout.addWidget(self.btn_prompt_delete)
        
        self.btn_prompt_import = QPushButton("📂 导入")
        self.btn_prompt_import.clicked.connect(self.on_prompt_import_file)
        btn_layout.addWidget(self.btn_prompt_import)
        list_layout.addLayout(btn_layout)
        layout.addWidget(list_group)
        
        # 预览
        preview_group = QGroupBox("选中预览")
        prev_layout = QVBoxLayout(preview_group)
        self.prompt_preview = QTextEdit()
        self.prompt_preview.setReadOnly(True)
        self.prompt_preview.setPlaceholderText("选择左侧列表查看详情...")
        prev_layout.addWidget(self.prompt_preview)
        layout.addWidget(preview_group)
        
        # 加载数据
        self.load_prompt_list()
        
        return page

    def load_prompt_list(self):
        self.prompt_list.clear()
        from core.utils.utils import get_project_root
        prompt_dir = os.path.join(get_project_root(), 'config', 'prompts')
        if not os.path.exists(prompt_dir): return
        
        # 隐藏系统级指令
        system_masks = ['alignment', '.translate_en', '.alignment', '.meta_prompt_generator']
        
        for fname in os.listdir(prompt_dir):
            if fname.endswith('.txt'):
                name = fname[:-4]
                if name not in system_masks and not name.startswith('.'):
                    self.prompt_list.addItem(name)

    def on_prompt_selected(self, row):
        if row < 0:
            self.prompt_preview.clear()
            return
        name = self.prompt_list.item(row).text()
        from core.utils.utils import get_project_root
        path = os.path.join(get_project_root(), 'config', 'prompts', f"{name}.txt")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.prompt_preview.setPlainText(f.read())
            except:
                self.prompt_preview.setPlainText("加载失败")

    def on_prompt_add(self):
        from ui.dialogs.prompt_editor import PromptEditorDialog
        dialog = PromptEditorDialog(parent=self)
        if dialog.exec():
            self.load_prompt_list()

    def on_prompt_modify(self):
        row = self.prompt_list.currentRow()
        if row < 0: return
        name = self.prompt_list.item(row).text()
        from ui.dialogs.prompt_editor import PromptEditorDialog
        dialog = PromptEditorDialog(prompt_name=name, parent=self)
        if dialog.exec():
            # 刷新预览
            self.on_prompt_selected(row)

    def on_prompt_remove(self):
        row = self.prompt_list.currentRow()
        if row < 0: return
        name = self.prompt_list.item(row).text()
        
        reply = QMessageBox.question(self, "确认删除", f"确定要永久删除提示词预设 '{name}' 吗？", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            from core.utils.utils import get_project_root
            path = os.path.join(get_project_root(), 'config', 'prompts', f"{name}.txt")
            try:
                if os.path.exists(path): os.remove(path)
                self.load_prompt_list()
                self.prompt_preview.clear()
            except Exception as e:
                QMessageBox.warning(self, "失败", f"删除失败: {e}")

    def on_prompt_import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择提示词文件", "", "Text Files (*.txt)")
        if path:
            try:
                import shutil
                from core.utils.utils import get_project_root
                dest_dir = os.path.join(get_project_root(), 'config', 'prompts')
                shutil.copy(path, dest_dir)
                self.load_prompt_list()
                QMessageBox.information(self, "成功", "导入成功")
            except Exception as e:
                QMessageBox.warning(self, "失败", f"导入失败: {e}")
