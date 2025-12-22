from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QFontComboBox, QSpinBox, 
    QDoubleSpinBox, QPushButton, QColorDialog, QHBoxLayout, 
    QLabel, QComboBox, QMessageBox, QGroupBox, QInputDialog,
    QSizePolicy, QScrollArea, QMenu, QFrame, QListWidget, QListWidgetItem, QCheckBox
)
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QBrush, QFontDatabase, QIcon, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from ...core.style_manager import StylePresetManager
from pysubs2 import Color

class StyleEditorWidget(QWidget):
    """
    高密度样式编辑器
    采用垂直列表布局，舍弃占空间的本地预览框，改为通过信号触发视频实时预览
    """
    previewRequested = pyqtSignal(object) # 样式实时预览信号 (SSAStyle)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.preset_manager = StylePresetManager()
        self._current_style_name = "Default"
        self._is_loading = False # 状态锁，防止同步数据时触发冗余信号
        
        self._is_compact = False # 紧凑模式标志
        
        self.init_ui()
        self.load_from_store()
        self.store.dataChanged.connect(self.load_from_store)

    def set_compact_mode(self, enabled: bool):
        """
        开启紧凑模式 (嵌入到分组编辑器中使用)
        隐藏列表、标题、预设管理，强制显示参数面板
        """
        self._is_compact = enabled
        
        # 隐藏/显示 头部区域
        self.list_header_widget.setVisible(not enabled)
        self.style_list.setVisible(not enabled)
        self.quick_action_widget.setVisible(not enabled)
        
        # 强制显示高级参数区
        self.advanced_area.setVisible(True)
        # 移除底部的伸缩弹簧 (在 main_layout 最后一个)
        if enabled:
            # 移除 Stretch
            pass 
        
    def set_target_style(self, style_name):
        """外部驱动接口：设置要编辑的样式"""
        if style_name not in self.store.subs.styles:
            return
        self._current_style_name = style_name
        self.load_from_store()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(6)
        
        # 1. 样式列表 (竖排，高密度)
        # 1. 样式列表 (竖排，高密度)
        self.list_header_widget = QWidget()
        lhw_layout = QHBoxLayout(self.list_header_widget)
        lhw_layout.setContentsMargins(0,0,0,0)
        
        lhw_layout.addWidget(QLabel("<b>样式库</b>"))
        lhw_layout.addStretch()
        btn_add = QPushButton("+")
        btn_add.setFixedSize(22, 22)
        btn_add.clicked.connect(self.add_new_style)
        lhw_layout.addWidget(btn_add)
        self.main_layout.addWidget(self.list_header_widget)
        
        self.style_list = QListWidget()
        self.style_list.setFixedHeight(120)
        self.style_list.setStyleSheet("""
            QListWidget { background: transparent; border: 1px solid #333; border-radius: 2px; }
            QListWidget::item { padding: 4px; border-bottom: 1px solid #2A2A2A; color: #AAA; }
            QListWidget::item:selected { background-color: #3B82F6; color: white; font-weight: bold; }
        """)
        self.style_list.currentTextChanged.connect(self.on_style_selected_by_list)
        self.main_layout.addWidget(self.style_list)
        
        # 2. 核心控制行 (移除原有预览窗)
        # 2. 核心控制行 (移除原有预览窗)
        self.quick_action_widget = QWidget()
        qaw_layout = QHBoxLayout(self.quick_action_widget)
        qaw_layout.setContentsMargins(0,0,0,0)
        
        self.btn_toggle_adv = QPushButton("参数调节 >>")
        self.btn_toggle_adv.setCheckable(True)
        self.btn_toggle_adv.setFixedHeight(24)
        self.btn_toggle_adv.clicked.connect(self.toggle_advanced)
        qaw_layout.addWidget(self.btn_toggle_adv)
        
        btn_preset = QPushButton("载入...")
        btn_preset.setFixedSize(50, 24)
        self.preset_menu = QMenu(self)
        btn_preset.setMenu(self.preset_menu)
        qaw_layout.addWidget(btn_preset)
        self.main_layout.addWidget(self.quick_action_widget)
        
        # 3. 高级参数 (默认隐藏)
        self.advanced_area = QWidget()
        self.adv_layout = QVBoxLayout(self.advanced_area)
        self.adv_layout.setContentsMargins(0, 0, 0, 0)
        self.adv_layout.setSpacing(6)
        
        # 字体
        f_box = QGroupBox("字体")
        f_form = QFormLayout(f_box)
        f_form.setContentsMargins(5, 5, 5, 5)
        self.font_combo = QFontComboBox()
        self.font_combo.currentFontChanged.connect(self.on_font_family_changed)
        f_form.addRow(self.font_combo)
        
        s_row = QHBoxLayout()
        self.combo_f_style = QComboBox()
        self.combo_f_style.currentIndexChanged.connect(self.on_font_style_changed)
        s_row.addWidget(self.combo_f_style, 1)
        self.spin_size = QDoubleSpinBox()
        self.spin_size.setRange(8, 300); self.spin_size.setSuffix("pt")
        self.spin_size.valueChanged.connect(lambda v: self.update_style("fontsize", v))
        s_row.addWidget(self.spin_size, 1)
        f_form.addRow(s_row)
        self.adv_layout.addWidget(f_box)
        
        # 视觉组：主要颜色与特效
        v_box = QGroupBox("视觉")
        v_main = QVBoxLayout(v_box)
        v_main.setContentsMargins(2, 6, 2, 2) # 更紧凑的边距
        v_main.setSpacing(4)
        
        # 颜色行
        c_row = QHBoxLayout()
        c_row.setSpacing(4) # 紧凑间距
        
        self.btn_c_pri = self._create_color_btn("T", "primarycolor", "主文本色")
        self.btn_c_out = self._create_color_btn("O", "outlinecolor", "描边颜色")
        self.btn_c_sha = self._create_color_btn("S", "backcolor", "阴影颜色")
        
        c_row.addWidget(self.btn_c_pri)
        c_row.addWidget(self.btn_c_out)
        c_row.addWidget(self.btn_c_sha)
        
        # 渐变控制 (紧凑)
        self.grad_container = QWidget()
        grad_layout = QHBoxLayout(self.grad_container)
        grad_layout.setContentsMargins(0, 0, 0, 0)
        grad_layout.setSpacing(2)
        
        # 使用 Icon 代替文字 "渐" 以节省空间，或者使用更窄的 Button
        self.chk_gradient = QCheckBox("渐")
        self.chk_gradient.setToolTip("开启水平渐变 (Gradient)")
        self.chk_gradient.setFixedWidth(32) 
        self.chk_gradient.toggled.connect(lambda c: self.update_style("gradient_enabled", c))
        
        self.btn_c_grad = self._create_color_btn("E", "gradient_end", "渐变终点色")
        self.btn_c_grad.setEnabled(False) 
        
        grad_layout.addWidget(self.chk_gradient)
        grad_layout.addWidget(self.btn_c_grad)
        
        # 添加分隔线视觉效果
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setFixedHeight(20)
        
        c_row.addSpacing(4)
        c_row.addWidget(line)
        c_row.addSpacing(4)
        c_row.addWidget(self.grad_container)
        c_row.addStretch()
        
        v_main.addLayout(c_row)
        
        p_form = QFormLayout()
        self.spin_out = QDoubleSpinBox(); self.spin_out.setRange(0, 100); self.spin_out.setDecimals(1)
        self.spin_out.valueChanged.connect(lambda v: self.update_style("outline", v))
        p_form.addRow("描边大小:", self.spin_out)
        self.spin_sha = QDoubleSpinBox(); self.spin_sha.setRange(0, 100); self.spin_sha.setDecimals(1)
        self.spin_sha.valueChanged.connect(lambda v: self.update_style("shadow", v))
        p_form.addRow("阴影深度:", self.spin_sha)
        v_main.addLayout(p_form)
        self.adv_layout.addWidget(v_box)

        # 位置调节
        pos_box = QGroupBox("位置")
        pos_form = QFormLayout(pos_box)
        pos_form.setContentsMargins(5, 5, 5, 5)
        pos_form.setSpacing(4)
        
        self.combo_align = QComboBox()
        # 九宫格映射
        self.combo_align.addItems(["左上(7)", "中上(8)", "右上(9)", 
                                   "左中(4)", "正中(5)", "右中(6)", 
                                   "左下(1)", "下中(2)", "右下(3)"])
        self.align_map = [7, 8, 9, 4, 5, 6, 1, 2, 3]
        self.combo_align.currentIndexChanged.connect(self.on_align_changed)
        pos_form.addRow("对齐方式:", self.combo_align)
        
        self.spin_margin_v = QSpinBox()
        self.spin_margin_v.setRange(0, 2000); self.spin_margin_v.setSuffix("px")
        self.spin_margin_v.valueChanged.connect(lambda v: self.update_style("marginv", v))
        pos_form.addRow("垂直偏移:", self.spin_margin_v)
        self.adv_layout.addWidget(pos_box)
        
        # 动作
        act_row = QHBoxLayout()
        btn_save = QPushButton("存预设")
        btn_save.clicked.connect(self.save_preset)
        self.btn_del = QPushButton("删除")
        self.btn_del.setStyleSheet("color: #F87171;")
        self.btn_del.clicked.connect(self.delete_current_style)
        act_row.addWidget(btn_save); act_row.addStretch(); act_row.addWidget(self.btn_del)
        self.adv_layout.addLayout(act_row)
        
        self.main_layout.addWidget(self.advanced_area)
        self.advanced_area.setVisible(False)
        self.main_layout.addStretch()

    def _create_color_btn(self, text, attr, tip):
        btn = QPushButton(text)
        btn.setToolTip(tip)
        btn.setFixedSize(28, 28)
        btn.clicked.connect(lambda: self.pick_color(attr, btn))
        return btn

    def toggle_advanced(self, checked):
        if self._is_compact:
            # 紧凑模式下不允许折叠
            self.advanced_area.setVisible(True)
            return

        self.advanced_area.setVisible(checked)
        self.btn_toggle_adv.setText("收起参数 <<" if checked else "参数调节 >>")
        if not checked:
            self.previewRequested.emit(None) # 关闭预览层

    def pick_color(self, attr_name, btn):
        style = self.get_current_style()
        c = getattr(style, attr_name)
        qt_color = QColor(c.r, c.g, c.b, 255-c.a)
        new_color = QColorDialog.getColor(qt_color, self, "颜色", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if new_color.isValid():
            p_color = Color(new_color.red(), new_color.green(), new_color.blue(), 255-new_color.alpha())
            self.update_style(attr_name, p_color)
            self._update_color_btn_visual(btn, new_color)

    def _update_color_btn_visual(self, btn, qc):
        btn.setStyleSheet(f"background-color: {qc.name()}; border: 1px solid #555; border-radius: 2px;")

    def get_current_style(self):
        name = self._current_style_name
        if name not in self.store.subs.styles:
            from pysubs2 import SSAStyle
            self.store.subs.styles[name] = SSAStyle()
        return self.store.subs.styles[name]

    def load_from_store(self):
        # 即使没有 subtitle 文件主体，也允许进行样式管理（以便预设起效）
        self._is_loading = True
        self.style_list.blockSignals(True)
        self.style_list.clear()
        
        # 保护性获取样式表，如果 subs 不存在（虽然初始化时已创建），则提供默认容器
        styles_map = self.store.subs.styles if self.store.subs else {}
        styles = sorted(styles_map.keys())
        
        self.style_list.addItems(styles)
        if self._current_style_name in styles:
            items = self.style_list.findItems(self._current_style_name, Qt.MatchFlag.MatchExactly)
            if items: self.style_list.setCurrentItem(items[0])
        elif styles:
            self._current_style_name = styles[0]
            self.style_list.setCurrentRow(0)
            
        self.style_list.blockSignals(False)
        self._update_fields_from_style()
        self.refresh_presets()
        self._is_loading = False

    def on_style_selected_by_list(self, name):
        if self._is_loading or not name: return
        self._current_style_name = name
        self._is_loading = True
        self._update_fields_from_style()
        self._is_loading = False
        # 切换时如果展开了面板，触发一次真机预览
        if self.btn_toggle_adv.isChecked():
            self.previewRequested.emit(self.get_current_style())

    def _update_fields_from_style(self):
        style = self.get_current_style()
        self.btn_del.setEnabled(self._current_style_name != "Default")
        self.blockSignals(True)
        self.font_combo.setCurrentFont(QFont(style.fontname))
        self.spin_size.setValue(style.fontsize)
        self.spin_out.setValue(style.outline)
        self.spin_sha.setValue(style.shadow)
        def to_qc(c): return QColor(c.r, c.g, c.b, 255-c.a)
        self._update_color_btn_visual(self.btn_c_pri, to_qc(style.primarycolor))
        self._update_color_btn_visual(self.btn_c_out, to_qc(style.outlinecolor))
        self._update_color_btn_visual(self.btn_c_sha, to_qc(style.backcolor))
        
        # 提取渐变数据
        g_meta = self.store.extra_style_data.get(self._current_style_name, {})
        is_grad = g_meta.get("gradient_enabled", False)
        self.chk_gradient.setChecked(is_grad)
        self.btn_c_grad.setEnabled(is_grad)
        grad_end_c = g_meta.get("gradient_end", QColor("#FF0000"))
        self._update_color_btn_visual(self.btn_c_grad, grad_end_c)
        
        self._populate_font_styles(style.fontname)

        # 刷新位置属性
        self.spin_margin_v.setValue(style.marginv)
        try:
            val = style.alignment
            idx = self.align_map.index(val)
            self.combo_align.setCurrentIndex(idx)
        except:
            self.combo_align.setCurrentIndex(7)

        # 还原 VF 细选样式
        style_name = g_meta.get("font_style")
        if style_name:
            idx = self.combo_f_style.findText(style_name)
            if idx >= 0:
                self.combo_f_style.blockSignals(True)
                self.combo_f_style.setCurrentIndex(idx)
                self.combo_f_style.blockSignals(False)

        self.blockSignals(False)

    def update_style(self, attr, value):
        if self._is_loading: return
        style = self.get_current_style()
        
        # 处理扩展属性 (Gradient)
        if attr.startswith("gradient_"):
            if self._current_style_name not in self.store.extra_style_data:
                self.store.extra_style_data[self._current_style_name] = {}
            
            meta = self.store.extra_style_data[self._current_style_name]
            
            if attr == "gradient_enabled":
                meta["gradient_enabled"] = value
                self.btn_c_grad.setEnabled(value)
            elif attr == "gradient_end":
                # value 是 pysubs2.Color (来自 pick_color)，转回 QColor
                qc = QColor(value.r, value.g, value.b, 255-value.a)
                meta["gradient_end"] = qc
                
            self.store.extra_style_data[self._current_style_name] = meta
        else:
            # 标准属性
            setattr(style, attr, value)
            # 如果修改了 primary color，也作为 gradient start 更新一下
            if attr == "primarycolor":
                 if self._current_style_name not in self.store.extra_style_data:
                    self.store.extra_style_data[self._current_style_name] = {}
                 qc = QColor(value.r, value.g, value.b, 255-value.a)
                 self.store.extra_style_data[self._current_style_name]["gradient_start"] = qc

        self.store._mark_dirty(); self.store.dataChanged.emit()
        # 实时映射给覆盖层
        self.previewRequested.emit(style)

    def pick_color(self, attr_name, btn):
        style = self.get_current_style()
        
        # 获取初始颜色
        if attr_name == "gradient_end":
            g_meta = self.store.extra_style_data.get(self._current_style_name, {})
            # 必须用 get 默认值
            qt_color = g_meta.get("gradient_end", QColor("#FF0000"))
        else:
            c = getattr(style, attr_name)
            qt_color = QColor(c.r, c.g, c.b, 255-c.a)
            
        new_color = QColorDialog.getColor(qt_color, self, "颜色", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if new_color.isValid():
            p_color = Color(new_color.red(), new_color.green(), new_color.blue(), 255-new_color.alpha())
            self.update_style(attr_name, p_color)
            self._update_color_btn_visual(btn, new_color)
            self.update_style(attr_name, p_color)
            self._update_color_btn_visual(btn, new_color)

    def _populate_font_styles(self, family):
        styles = QFontDatabase.styles(family)
        self.combo_f_style.blockSignals(True); self.combo_f_style.clear()
        if len(styles) > 1 or (styles and styles[0] not in ["Normal", "Regular"]):
            self.combo_f_style.setVisible(True)
            for s in styles: self.combo_f_style.addItem(s)
        else: self.combo_f_style.setVisible(False)
        style = self.get_current_style(); cur = "Normal"
        if style.bold and style.italic: cur = "Bold Italic"
        elif style.bold: cur = "Bold"
        elif style.italic: cur = "Italic"
        idx = self.combo_f_style.findText(cur, Qt.MatchFlag.MatchContains)
        self.combo_f_style.setCurrentIndex(max(0, idx)); self.combo_f_style.blockSignals(False)

    def on_font_style_changed(self, index):
        if self._is_loading: return
        txt = self.combo_f_style.currentText(); style = self.get_current_style()
        style.bold = any(kw in txt for kw in ["Bold", "Black", "Heavy"])
        style.italic = any(kw in txt for kw in ["Italic", "Oblique"])
        style._qt_style_name = txt
        
        # 记录 VF 细选样式名
        if self._current_style_name not in self.store.extra_style_data:
            self.store.extra_style_data[self._current_style_name] = {}
        self.store.extra_style_data[self._current_style_name]["font_style"] = txt
        
        self.update_style("fontname", style.fontname)

    def on_font_family_changed(self, font):
        if self._is_loading: return
        self.update_style("fontname", font.family()); self._populate_font_styles(font.family())

    def add_new_style(self):
        name, ok = QInputDialog.getText(self, "新样式", "名称:")
        if ok and name:
            if name in self.store.subs.styles: return
            from pysubs2 import SSAStyle
            self.store.subs.styles[name] = SSAStyle()
            self._current_style_name = name; self.store._mark_dirty(); self.load_from_store()

    def delete_current_style(self):
        if self._current_style_name == "Default": return
        if QMessageBox.question(self, "删除", f"删除 '{self._current_style_name}'？") == QMessageBox.StandardButton.Yes:
            del self.store.subs.styles[self._current_style_name]; self._current_style_name = "Default"
            self.store._mark_dirty(); self.load_from_store()

    def refresh_presets(self):
        self.preset_menu.clear()
        for p in self.preset_manager.get_presets(): self.preset_menu.addAction(p).triggered.connect(lambda checked, n=p: self.on_preset_selected(n))

    def on_preset_selected(self, name):
        data = self.preset_manager.load_preset(name)
        if data:
            # 应用到【当前正在编辑】的样式，而不是以预设名新建样式
            target_name = self._current_style_name
            style = self.get_current_style() # 确保样式存在
            
            for k, v in data.items():
                if k != "extra_data" and hasattr(style, k):
                    setattr(style, k, v)
            
            # 恢复扩展数据到当前样式
            self.store.extra_style_data[target_name] = data.get("extra_data", {})
            self.store._mark_dirty()
            self.store.dataChanged.emit()
            self._update_fields_from_style()

    def on_align_changed(self, index):
        if self._is_loading: return
        val = self.align_map[index]
        self.update_style("alignment", val)

    def save_preset(self):
        name, ok = QInputDialog.getText(self, "存预设", "名称:")
        if ok and name: 
            style = self.get_current_style()
            extra = self.store.extra_style_data.get(self._current_style_name, {})
            self.preset_manager.save_preset(name, style, extra)
            self.refresh_presets()
