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
        
        menu = QMenu(self)
        
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
        
            self.table.blockSignals(True)
            for row, ev in enumerate(events):
                # Start
                t_start = self.format_time(ev.start)
                item_start = QTableWidgetItem(t_start)
                item_start.setData(Qt.ItemDataRole.UserRole, ev.start) # 存储实际 ms
                self.table.setItem(row, 0, item_start)
                
                # End
                t_end = self.format_time(ev.end)
                self.table.setItem(row, 1, QTableWidgetItem(t_end))
                
                # Text
                # 简单处理：移除换行符并清洗 ASS标签用于显示
                # 使用简单的 regex 去除 {} 包裹的内容
                import re
                raw_text = ev.text.replace(r"\N", " ").replace("\n", " ")
                clean_text = re.sub(r"\{.*?\}", "", raw_text)
                
                item_text = QTableWidgetItem(clean_text)
                item_text.setToolTip(raw_text) # 鼠标悬停显示原始带标签文本
                self.table.setItem(row, 2, item_text)
            
        finally:
            self.table.blockSignals(False)
            self._is_refreshing = False

    def on_item_clicked(self, item):
        row = item.row()
        start_item = self.table.item(row, 0)
        if start_item:
            ms = start_item.data(Qt.ItemDataRole.UserRole)
            self.request_seek.emit(ms)
