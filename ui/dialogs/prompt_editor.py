"""
Prompt编辑器

支持手动编辑和AI辅助生成
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QLineEdit, QMessageBox, QTabWidget, QWidget, QGroupBox
)
from PyQt6.QtCore import Qt
import os
import logging

logger = logging.getLogger(__name__)


class PromptEditorDialog(QDialog):
    """Prompt编辑器对话框"""
    
    def __init__(self, prompt_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Prompt 编辑器"))
        self.setModal(True)
        self.resize(800, 600)
        
        self.prompt_name = prompt_name
        self.prompt_content = ""
        
        # 如果是编辑现有prompt，加载内容
        if prompt_name:
            self.load_prompt(prompt_name)
        
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        
        # Prompt名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel(self.tr("Prompt名称:")))
        self.name_input = QLineEdit()
        self.name_input.setText(self.prompt_name)
        self.name_input.setPlaceholderText(self.tr("例如: lqa_custom"))
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)
        
        # 标签页
        tabs = QTabWidget()
        
        # Tab 1: 手动编辑
        manual_tab = self.create_manual_tab()
        tabs.addTab(manual_tab, self.tr("✍️ 手动编辑"))
        
        # Tab 2: AI辅助生成
        ai_tab = self.create_ai_tab()
        tabs.addTab(ai_tab, self.tr("🤖 AI辅助生成"))
        
        layout.addWidget(tabs)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        btn_save = QPushButton(self.tr("💾 保存"))
        btn_save.clicked.connect(self.save_prompt)
        button_layout.addWidget(btn_save)
        
        btn_cancel = QPushButton(self.tr("❌ 取消"))
        btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(btn_cancel)
        
        layout.addLayout(button_layout)
    
    def create_manual_tab(self):
        """创建手动编辑标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 说明
        info = QLabel(self.tr("编辑Prompt内容。可使用变量: {context}, {source}, {target}"))
        info.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(info)
        
        # 编辑器
        self.manual_editor = QTextEdit()
        self.manual_editor.setPlaceholderText(self.tr("在此输入Prompt内容...\n\n支持的变量:\n{context} - 用户提供的上下文\n{source} - 原文\n{target} - 译文"))
        
        if self.prompt_content:
            self.manual_editor.setPlainText(self.prompt_content)
        
        layout.addWidget(self.manual_editor)
        
        return widget
    
    def create_ai_tab(self):
        """创建AI辅助生成标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 说明
        info_group = QGroupBox(self.tr("💡 使用说明"))
        info_layout = QVBoxLayout()
        info_label = QLabel(
            self.tr("描述你需要的Prompt功能，AI将帮你生成专业的Prompt模板。\n\n"
            "示例：\n"
            "- 我需要一个严格的翻译质量检查prompt，重点关注术语准确性\n"
            "- 生成一个温和的LQA prompt，适用于创意翻译\n"
            "- 创建一个prompt来检查字幕的时间轴同步问题")
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        info_layout.addWidget(info_label)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # 需求描述
        desc_label = QLabel(self.tr("描述你的需求:"))
        layout.addWidget(desc_label)
        
        self.ai_description = QTextEdit()
        self.ai_description.setPlaceholderText(
            self.tr("例如: 我需要一个用于动画字幕翻译的LQA prompt，要求：\n"
            "1. 关注儿童友好的语言\n"
            "2. 检查文化适应性\n"
            "3. 确保简洁易懂")
        )
        self.ai_description.setMaximumHeight(150)
        layout.addWidget(self.ai_description)
        
        # 生成按钮
        btn_generate = QPushButton(self.tr("🚀 生成Prompt"))
        btn_generate.clicked.connect(self.generate_with_ai)
        layout.addWidget(btn_generate)
        
        # 生成结果
        result_label = QLabel(self.tr("生成的Prompt:"))
        layout.addWidget(result_label)
        
        self.ai_result = QTextEdit()
        self.ai_result.setReadOnly(False)  # 允许编辑生成的结果
        layout.addWidget(self.ai_result)
        
        # 应用按钮
        btn_apply = QPushButton(self.tr("✅ 应用到编辑器"))
        btn_apply.clicked.connect(self.apply_ai_result)
        layout.addWidget(btn_apply)
        
        return widget
    
    def load_prompt(self, prompt_name: str):
        """加载现有prompt"""
        prompt_file = f'config/prompts/{prompt_name}.txt'
        
        if os.path.exists(prompt_file):
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    self.prompt_content = f.read()
            except Exception as e:
                logger.error(f"加载prompt失败: {e}")
    
    def generate_with_ai(self):
        """使用AI生成prompt"""
        description = self.ai_description.toPlainText().strip()
        
        if not description:
            QMessageBox.warning(self, self.tr("提示"), self.tr("请先描述你的需求"))
            return
        
        try:
            # 获取API客户端
            from core.api.api_client import APIClient, load_providers_config
            import json
            
            # 加载设置
            settings_file = 'config/settings.json'
            if os.path.exists(settings_file):
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
            else:
                QMessageBox.warning(self, self.tr("错误"), self.tr("请先在设置中配置API"))
                return
            
            providers = load_providers_config()
            provider_id = settings.get('api', {}).get('provider', 'openai')
            provider_config = providers.get(provider_id)
            
            if not provider_config:
                QMessageBox.warning(self, self.tr("错误"), self.tr("找不到提供商: {}").format(provider_id))
                return
            
            api_key = settings.get('api', {}).get('api_key', '')
            model = settings.get('api', {}).get('model', provider_config['default_model'])
            
            if not api_key:
                QMessageBox.warning(self, self.tr("警告"), self.tr("请在设置中配置API密钥"))
                return
            
            # 加载meta-prompt
            meta_prompt = self.load_meta_prompt()
            
            # 创建API客户端
            client = APIClient(provider_config, api_key, model)
            
            # 调用AI
            self.ai_result.setPlainText(self.tr("生成中..."))
            
            response = client.generate_content(
                system_prompt=meta_prompt,
                user_prompt=description,
                json_mode=False,
                temperature=0.7
            )
            
            generated_prompt = response.get('text', '')
            
            if generated_prompt:
                self.ai_result.setPlainText(generated_prompt)
                QMessageBox.information(self, self.tr("成功"), self.tr("Prompt已生成！你可以编辑后再应用。"))
            else:
                QMessageBox.warning(self, self.tr("错误"), self.tr("生成失败，请重试"))
                
        except Exception as e:
            QMessageBox.warning(self, self.tr("错误"), self.tr("生成失败: {}").format(str(e)))
            logger.error(f"AI生成prompt失败: {e}", exc_info=True)
    
    def load_meta_prompt(self) -> str:
        """加载用于生成prompt的meta-prompt"""
        meta_prompt_file = 'config/prompts/.meta_prompt_generator.txt'
        
        if os.path.exists(meta_prompt_file):
            try:
                with open(meta_prompt_file, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                logger.error(f"加载meta-prompt失败: {e}")
        
        # 默认meta-prompt
        return """你是一个专业的Prompt工程师，专门为翻译质量评估(LQA)系统创建高质量的prompt模板。

用户会描述他们需要的prompt功能和要求，你需要生成一个完整、专业的prompt模板。

生成的prompt应该：
1. 清晰定义角色和任务
2. 提供具体的评判标准
3. 包含必要的变量占位符：{context}, {source}, {target}
4. 使用专业但易懂的语言
5. 结构清晰，易于阅读

请直接输出prompt内容，不要包含额外的解释。"""
    
    def apply_ai_result(self):
        """将AI生成的结果应用到手动编辑器"""
        ai_content = self.ai_result.toPlainText().strip()
        
        if not ai_content:
            QMessageBox.warning(self, self.tr("提示"), self.tr("没有可应用的内容"))
            return
        
        self.manual_editor.setPlainText(ai_content)
        QMessageBox.information(self, self.tr("成功"), self.tr("已应用到编辑器，你可以继续手动编辑"))
    
    def save_prompt(self):
        """保存prompt"""
        name = self.name_input.text().strip()
        content = self.manual_editor.toPlainText().strip()
        
        if not name:
            QMessageBox.warning(self, self.tr("错误"), self.tr("请输入Prompt名称"))
            return
        
        if not content:
            QMessageBox.warning(self, self.tr("错误"), self.tr("Prompt内容不能为空"))
            return
        
        # 确保不覆盖系统prompt
        system_prompts = ['alignment', '.meta_prompt_generator']
        if name in system_prompts:
            QMessageBox.warning(self, self.tr("错误"), self.tr("'{}' 是系统保留名称，请使用其他名称").format(name))
            return
        
        try:
            prompt_file = f'config/prompts/{name}.txt'
            os.makedirs(os.path.dirname(prompt_file), exist_ok=True)
            
            with open(prompt_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            QMessageBox.information(self, self.tr("成功"), self.tr("Prompt '{}' 已保存").format(name))
            self.accept()
            
        except Exception as e:
            QMessageBox.warning(self, self.tr("错误"), self.tr("保存失败: {}").format(str(e)))
    
    def get_prompt_name(self) -> str:
        """获取prompt名称"""
        return self.name_input.text().strip()
