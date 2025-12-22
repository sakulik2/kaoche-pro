from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QVBoxLayout, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal

class SubtitleListWidget(QWidget):
    """
    字幕列表组件
    显示 Start, End, Text，并支持点击跳转
    """
    request_seek = pyqtSignal(int) # ms
    
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.init_ui()
        
        # 信号连接
        self.store.dataChanged.connect(self.refresh_list)
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["开始时间", "结束时间", "文本内容"])
        
        # 样式调整
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(True)
        
        # 点击跳转
        self.table.itemClicked.connect(self.on_item_clicked)
        
        # 右键菜单
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        layout.addWidget(self.table)
        
        # 选择同步
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.store.selectionChanged.connect(self._on_store_selection_changed)
        
        # 初始加载
        self.refresh_list()

    def _on_table_selection_changed(self):
        """当下层表格选中项变化时，同步给 Store"""
        if getattr(self, "_is_refreshing", False):
            return
        
        selected_rows = list(set(item.row() for item in self.table.selectedItems()))
        self.store.set_selection(selected_rows)

    def _on_store_selection_changed(self, indices):
        """当外部（如时间轴）改变选中项时，同步高亮表格"""
        if getattr(self, "_is_refreshing", False):
            return
            
        self.table.blockSignals(True)
        self.table.clearSelection()
        for idx in indices:
            if idx < self.table.rowCount():
                self.table.selectRow(idx)
        self.table.blockSignals(False)
    
    def show_context_menu(self, pos):
        """显示右键菜单"""
        from PyQt6.QtWidgets import QMenu
        
        # 获取选中的行
        selected_rows = list(set(item.row() for item in self.table.selectedItems()))
        if not selected_rows:
            return
        
        # 对齐位置子菜单
        align_label_map = {
            1: "左下 (an1)", 2: "中下 (an2)", 3: "右下 (an3)",
            4: "左中 (an4)", 5: "正中 (an5)", 6: "右中 (an6)",
            7: "左上 (an7)", 8: "中上 (an8)", 9: "右上 (an9)"
        }
        align_menu = menu.addMenu("快速对齐 (Alignment)")
        for val, label in align_label_map.items():
            act = align_menu.addAction(label)
            act.triggered.connect(lambda checked, v=val, rows=selected_rows: self.apply_alignment(rows, v))

        menu.addSeparator()

        # 分组菜单
        group_menu = menu.addMenu("分配到分组")
        
        # 获取所有分组
        groups = self.store.get_all_groups()
        for group_name in sorted(groups.keys()):
            action = group_menu.addAction(group_name)
            # 使用 lambda 捕获参数
            action.triggered.connect(
                lambda checked=False, g=group_name, rows=selected_rows: 
                self.assign_to_group(rows, g)
            )
        
        # 在鼠标位置显示菜单
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def apply_alignment(self, rows, align_val):
        """批量应用对齐标签"""
        import re
        for row in rows:
            ev = self.store.get_event(row)
            if not ev: continue
            
            # 使用正则表达式替换现有的 \an 标签，或者在开头插入
            tag = f"\\an{align_val}"
            if "{" in ev.text:
                # 寻找第一个大括号内的内容
                if re.search(r"\{\\an\d", ev.text):
                     new_text = re.sub(r"(\\an\d)", tag, ev.text)
                else:
                     new_text = ev.text.replace("{", f"{{{tag}", 1)
            else:
                new_text = f"{{{tag}}}{ev.text}"
            
            self.store.update_event(row, text=new_text)
    
    def assign_to_group(self, rows, group_name):
        """将选中行分配到分组"""
        self.store.assign_group_to_events(rows, group_name)
        
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self, 
            "成功", 
            f"已将 {len(rows)} 条字幕分配到分组: {group_name}"
        )

    def format_time(self, ms):
        """ms -> HH:MM:SS.ms"""
        s = ms / 1000.0
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = s % 60
        return f"{h:02d}:{m:02d}:{sec:06.3f}"

    def refresh_list(self):
        if getattr(self, "_is_refreshing", False):
            return
        self._is_refreshing = True
        
        try:
            self.table.setRowCount(0)
            if not self.store.subs:
                return
                
            events = self.store.subs.events
            self.table.setRowCount(len(events))
        
            for row, ev in enumerate(events):
                # Start
                t_start = self.format_time(ev.start)
                item_start = QTableWidgetItem(t_start)
                item_start.setFlags(item_start.flags() & ~Qt.ItemFlag.ItemIsEditable) # 禁止编辑时间
                item_start.setData(Qt.ItemDataRole.UserRole, ev.start) # 存储实际 ms
                self.table.setItem(row, 0, item_start)
                
                # End
                t_end = self.format_time(ev.end)
                item_end = QTableWidgetItem(t_end)
                item_end.setFlags(item_end.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, 1, item_end)
                
                # Text
                # 简单处理：显示纯文本，但在编辑时显示带标签的原文
                import re
                raw_text = ev.text.replace(r"\N", " ").replace("\n", " ")
                clean_text = re.sub(r"\{.*?\}", "", raw_text)
                
                item_text = QTableWidgetItem(clean_text)
                item_text.setData(Qt.ItemDataRole.UserRole, ev.text) # 存原文
                item_text.setToolTip(ev.text)
                self.table.setItem(row, 2, item_text)
            
            # 监听改动
            self.table.itemChanged.connect(self.on_item_changed)
        finally:
            self.table.blockSignals(False)
            self._is_refreshing = False

    def on_item_changed(self, item):
        """捕捉手动编辑"""
        if getattr(self, "_is_refreshing", False) or item.column() != 2:
            return
        
        row = item.row()
        new_text = item.text()
        
        # 如果用户修改的是纯文本，尝试保留原有标签 (简单策略)
        # 这里为了防止误伤，如果原文本包含复杂标签，我们可能更倾向于让用户直接修改原文
        # 但既然是“便捷编辑”，我们直接更新 Store 即可。
        old_raw = item.data(Qt.ItemDataRole.UserRole)
        import re
        if "{" in old_raw:
            # 提取所有标签
            tags = "".join(re.findall(r"\{.*?\}", old_raw))
            final_text = tags + new_text
        else:
            final_text = new_text
            
        self.store.update_event(row, text=final_text)

    def on_item_clicked(self, item):
        row = item.row()
        start_item = self.table.item(row, 0)
        if start_item:
            ms = start_item.data(Qt.ItemDataRole.UserRole)
            self.request_seek.emit(ms)
