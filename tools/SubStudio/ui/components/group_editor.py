from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, 
    QListWidgetItem, QLabel, QComboBox, QColorDialog, QInputDialog,
    QMessageBox, QGroupBox, QFormLayout
)
from PyQt6.QtGui import QColor, QPixmap, QPainter, QIcon
from PyQt6.QtCore import Qt
from .style_editor import StyleEditorWidget

class GroupEditorWidget(QWidget):
    """
    精简版分组管理编辑器
    极致压缩占用空间，与样式编辑器保持风格一致
    """
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.init_ui()
        self.load_groups()
        self.store.groupsChanged.connect(self.load_groups)
        self.store.dataChanged.connect(self._refresh_styles)
    
    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(6)
        
        # 1. 分组列表 (紧凑型)
        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("<b>分组库</b>"))
        list_header.addStretch()
        btn_add = QPushButton("+")
        btn_add.setFixedSize(22, 22)
        btn_add.clicked.connect(self.add_group)
        list_header.addWidget(btn_add)
        self.main_layout.addLayout(list_header)
        
        self.list_groups = QListWidget()
        self.list_groups.setFixedHeight(120)
        self.list_groups.setStyleSheet("""
            QListWidget { background: transparent; border: 1px solid #333; border-radius: 2px; }
            QListWidget::item { padding: 4px; border-bottom: 1px solid #2A2A2A; color: #AAA; }
            QListWidget::item:selected { background-color: #10B981; color: white; font-weight: bold; }
        """)
        self.list_groups.currentItemChanged.connect(self.on_group_selected)
        self.main_layout.addWidget(self.list_groups)
        
        # 2. 快速属性调节 (默认收起)
        quick_action = QHBoxLayout()
        self.btn_toggle_prop = QPushButton("配置属性 >>")
        self.btn_toggle_prop.setCheckable(True)
        self.btn_toggle_prop.setFixedHeight(24)
        self.btn_toggle_prop.clicked.connect(self.toggle_properties)
        quick_action.addWidget(self.btn_toggle_prop)
        
        self.btn_del = QPushButton("-")
        self.btn_del.setFixedSize(22, 24)
        self.btn_del.setStyleSheet("color: #F87171;")
        self.btn_del.clicked.connect(self.delete_group)
        quick_action.addWidget(self.btn_del)
        self.main_layout.addLayout(quick_action)
        
        # 3. 属性编辑区 (默认隐藏)
        self.prop_area = QWidget()
        self.prop_layout = QFormLayout(self.prop_area)
        self.prop_layout.setContentsMargins(0, 0, 0, 0)
        self.prop_layout.setSpacing(6)
        
        self.combo_style = QComboBox()
        self.combo_style.currentTextChanged.connect(self.on_style_changed)
        self.prop_layout.addRow("关联样式:", self.combo_style)
        
        color_row = QHBoxLayout()
        self.color_prev = QLabel()
        self.color_prev.setFixedSize(22, 22)
        self.color_prev.setStyleSheet("border: 1px solid #555; border-radius: 2px;")
        btn_pick = QPushButton("色")
        btn_pick.setFixedSize(22, 22)
        btn_pick.clicked.connect(self.pick_color)
        color_row.addWidget(self.color_prev); color_row.addWidget(btn_pick); color_row.addStretch()
        self.prop_layout.addRow("轨道颜色:", color_row)
        
        # 4. 嵌入式样式编辑器 (核心重构)
        self.prop_layout.addRow(QLabel("<b>样式微调:</b>"))
        self.embedded_style_editor = StyleEditorWidget(self.store)
        self.embedded_style_editor.set_compact_mode(True)
        # 将样式编辑器直接加入布局
        self.prop_layout.addRow(self.embedded_style_editor)
        
        self.main_layout.addWidget(self.prop_area)
        self.prop_area.setVisible(False)
        self.main_layout.addStretch()

    def toggle_properties(self, checked):
        self.prop_area.setVisible(checked)
        self.btn_toggle_prop.setText("收起配置 <<" if checked else "配置属性 >>")

    def load_groups(self):
        self.list_groups.blockSignals(True); self.list_groups.clear()
        groups = self.store.get_all_groups()
        for name in sorted(groups.keys()):
            item = QListWidgetItem(name); item.setData(Qt.ItemDataRole.UserRole, groups[name])
            color = groups[name].get("color", "#3498db")
            item.setIcon(self._create_color_icon(color))
            self.list_groups.addItem(item)
        self.list_groups.blockSignals(False); self._refresh_styles()
    
    def _refresh_styles(self):
        cur = self.combo_style.currentText()
        self.combo_style.blockSignals(True); self.combo_style.clear()
        if self.store.subs and self.store.subs.styles:
            self.combo_style.addItems(sorted(self.store.subs.styles.keys()))
            if cur:
                idx = self.combo_style.findText(cur)
                if idx >= 0: self.combo_style.setCurrentIndex(idx)
        else: self.combo_style.addItem("Default")
        self.combo_style.blockSignals(False)
    
    def _create_color_icon(self, color_hex):
        pix = QPixmap(14, 14); pix.fill(QColor(color_hex))
        p = QPainter(pix); p.setPen(QColor("#555")); p.drawRect(0, 0, 13, 13); p.end()
        return QIcon(pix)
    
    def on_group_selected(self, current, previous):
        if not current:
            self.prop_area.setEnabled(False); return
        self.prop_area.setEnabled(True); g_data = current.data(Qt.ItemDataRole.UserRole)
        style_name = g_data.get("style", "Default"); idx = self.combo_style.findText(style_name)
        if idx >= 0:
            self.combo_style.blockSignals(True); self.combo_style.setCurrentIndex(idx); self.combo_style.blockSignals(False)
        self.current_color = g_data.get("color", "#3498db"); self._update_color_preview(self.current_color)
        
        # 联动嵌入式编辑器
        self.embedded_style_editor.set_target_style(style_name)

    def _update_color_preview(self, hex):
        self.color_prev.setStyleSheet(f"background-color: {hex}; border: 1px solid #555; border-radius: 2px;")
    
    def on_style_changed(self, style_name):
        cur = self.list_groups.currentItem()
        if style_name and cur:
            self.store.update_group(cur.text(), style=style_name)
            # 同时也更新下面编辑器的指向
            self.embedded_style_editor.set_target_style(style_name)
    
    def pick_color(self):
        cur = self.list_groups.currentItem()
        if not cur: return
        new_c = QColorDialog.getColor(QColor(self.current_color), self, "选择颜色")
        if new_c.isValid():
            hex = new_c.name(); self.current_color = hex; self._update_color_preview(hex)
            self.store.update_group(cur.text(), color=hex); self.load_groups()
            self.store.update_group(cur.text(), color=hex); self.load_groups()
            
    def add_group(self):
        name, ok = QInputDialog.getText(self, "新分组", "分组名称:")
        if ok and name:
            if not self.store.add_group(name):
                QMessageBox.warning(self, "错误", f"分组 '{name}' 已存在或非法。")

    def delete_group(self):
        cur = self.list_groups.currentItem()
        if not cur: return
        name = cur.text()
        if name == "Default":
            QMessageBox.information(self, "提示", "默认分组不能删除。")
            return
            
        if QMessageBox.question(self, "删除", f"确定删除分组 '{name}' 吗？\n该分组下的字幕将归入 Default 改组。") == QMessageBox.StandardButton.Yes:
            self.store.delete_group(name)
