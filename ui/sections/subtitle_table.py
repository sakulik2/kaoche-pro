"""
字幕表格组件
"""

from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, 
    QAbstractItemView, QMenu, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QColor, QAction
import logging

logger = logging.getLogger(__name__)

class SubtitleTable(QTableWidget):
    """字幕表格组件"""
    
    # 信号
    row_selected = pyqtSignal(int, dict)  # 行索引, 行数据
    cell_edited = pyqtSignal(int, int, str)  # 行, 列, 新内容
    request_reanalyze = pyqtSignal(int)  # 请求重新分析行
    request_delete = pyqtSignal(int)  # 请求删除行
    request_insert = pyqtSignal(int, str)  # 请求插入行 (index, position)
    request_merge = pyqtSignal(int, str)  # 请求合并行 (index, direction)
    request_ai_check = pyqtSignal(int)    # 请求 AI 精查 (row_index)
    request_justify = pyqtSignal(int)     # 请求添加辩解/说明
    time_jump_requested = pyqtSignal(int)  # 请求跳转到时间 (ms)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.subtitle_data = []
        self.has_timestamps = True
        
    def setup_ui(self):
        """初始化表格设置"""
        self.setColumnCount(7)
        self.setHorizontalHeaderLabels([
            "#", self.tr("开始时间"), self.tr("结束时间"), 
            self.tr("原文 (Source)"), self.tr("译文 (Target)"), 
            self.tr("得分"), self.tr("主要问题")
        ])
        
        # 表格外观
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.verticalHeader().setVisible(False)
        
        # 设置列宽
        self.setColumnWidth(0, 50)   # ID
        self.setColumnWidth(1, 120)  # Start (增加宽度以完整显示 00:00:00,000)
        self.setColumnWidth(2, 120)  # End
        self.setColumnWidth(3, 350)  # Source
        self.setColumnWidth(4, 350)  # Target
        self.setColumnWidth(5, 60)   # Score
        
        # 右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        # 信号连接
        self.cellDoubleClicked.connect(self.on_double_clicked)
        self.itemSelectionChanged.connect(self.on_selection_changed)

    def set_data(self, data, has_timestamps=True):
        """设置并显示数据"""
        self.subtitle_data = data
        self.has_timestamps = has_timestamps
        self.populate_table()
        
    def populate_table(self):
        """填充表格数据"""
        self.setRowCount(len(self.subtitle_data))
        
        # 根据是否有时间戳隐藏列
        self.setColumnHidden(1, not self.has_timestamps)
        self.setColumnHidden(2, not self.has_timestamps)
        
        for i, item in enumerate(self.subtitle_data):
            # 1. ID
            self.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            
            # 2. 时间戳 (如果有)
            source = item.get('source', {})
            if self.has_timestamps:
                start = source.get('start', 0)
                end = source.get('end', 0)
                self.setItem(i, 1, QTableWidgetItem(self._format_timestamp(start)))
                self.setItem(i, 2, QTableWidgetItem(self._format_timestamp(end)))
            
            # 3. 文本
            src_text = source.get('text', '') if isinstance(source, dict) else str(source)
            target = item.get('target', {})
            tgt_text = target.get('text', '') if isinstance(target, dict) else str(target)
            
            self.setItem(i, 3, QTableWidgetItem(src_text))
            self.setItem(i, 4, QTableWidgetItem(tgt_text))
            
            # 4. LQA结果
            lqa = item.get('lqa_result')
            if lqa:
                self._update_lqa_items(i, lqa)
            else:
                self.setItem(i, 5, QTableWidgetItem(""))
                self.setItem(i, 6, QTableWidgetItem(""))
                
        # 恢复由于 populate 可能导致丢失的选择状态（可选）

    def _update_lqa_items(self, row, lqa_result):
        """更新单行的 LQA 显示项"""
        score = lqa_result.get('score', 0)
        issues = ', '.join(lqa_result.get('issues', []))
        
        score_item = QTableWidgetItem(str(score))
        score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 评分颜色
        if score >= 8:
            score_item.setBackground(QColor(200, 255, 200))
        elif score >= 5:
            score_item.setBackground(QColor(255, 255, 200))
        else:
            score_item.setBackground(QColor(255, 200, 200))
            
        self.setItem(row, 5, score_item)
        self.setItem(row, 6, QTableWidgetItem(issues))

    def _format_timestamp(self, seconds):
        """格式化秒数为 00:00:00,000"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def on_selection_changed(self):
        """处理选择变化"""
        row = self.currentRow()
        if 0 <= row < len(self.subtitle_data):
            self.row_selected.emit(row, self.subtitle_data[row])
            
            # 如果有时间戳，发出跳转信号
            if self.has_timestamps:
                source = self.subtitle_data[row].get('source', {})
                if isinstance(source, dict) and source.get('start') is not None:
                    start_ms = int(source.get('start', 0) * 1000)
                    self.time_jump_requested.emit(start_ms)

    def select_row_at_time(self, seconds):
        """
        根据时间戳选择并滚动到指定行 (安全同步: 屏蔽信号)
        """
        if not self.subtitle_data or not self.has_timestamps:
            return

        target_row = -1
        for i, item in enumerate(self.subtitle_data):
            source = item.get('source', {})
            if not isinstance(source, dict): continue
            
            start = source.get('start', 0)
            end = source.get('end', 0)
            
            if start <= seconds <= end:
                target_row = i
                break
        
        if target_row != -1 and target_row != self.currentRow():
            # 暂时关闭信号发送，防止触发跳转反馈环
            self.blockSignals(True)
            self.selectRow(target_row)
            
            # 滚动（居中显示）
            self.scrollToItem(
                self.item(target_row, 0),
                QAbstractItemView.ScrollHint.PositionAtCenter
            )
            self.blockSignals(False)
            return True
        return False

    def on_double_clicked(self, row, col):
        """双击处理"""
        if col == 4: # 译文列
            # 交给 MainWindow 处理（通常弹出对话框）
            pass 

    def show_context_menu(self, pos: QPoint):
        """显示右键菜单"""
        row = self.rowAt(pos.y())
        if row < 0: return
        
        menu = QMenu(self)
        
        
        # 2. 编辑
        edit_act = QAction(self.tr("✏️ 编辑"), self)
        edit_act.triggered.connect(lambda: self.on_double_clicked(row, 4))
        menu.addAction(edit_act)
        
        menu.addSeparator()
        
        # 2. 复制
        copy_menu = menu.addMenu(self.tr("📋 复制"))
        copy_src = QAction(self.tr("复制原文"), self)
        copy_src.triggered.connect(lambda: self.copy_text(row, 'source'))
        copy_menu.addAction(copy_src)
        
        copy_tgt = QAction(self.tr("复制译文"), self)
        copy_tgt.triggered.connect(lambda: self.copy_text(row, 'target'))
        copy_menu.addAction(copy_tgt)
        
        menu.addSeparator()
        
        # 3. 插入
        insert_menu = menu.addMenu(self.tr("➕ 插入"))
        ins_above = QAction(self.tr("在上方插入"), self)
        ins_above.triggered.connect(lambda: self.request_insert.emit(row, 'above'))
        insert_menu.addAction(ins_above)
        
        ins_below = QAction(self.tr("在下方插入"), self)
        ins_below.triggered.connect(lambda: self.request_insert.emit(row, 'below'))
        insert_menu.addAction(ins_below)
        
        menu.addSeparator()
        
        # 4. 合并
        merge_menu = menu.addMenu(self.tr("🔗 合并"))
        merge_up = QAction(self.tr("与上方合并"), self)
        merge_up.triggered.connect(lambda: self.request_merge.emit(row, 'up'))
        merge_menu.addAction(merge_up)
        
        merge_down = QAction(self.tr("与下方合并"), self)
        merge_down.triggered.connect(lambda: self.request_merge.emit(row, 'down'))
        merge_menu.addAction(merge_down)
        
        menu.addSeparator()
        
        # 5. 辩解/说明
        justify_act = QAction(self.tr("💬 添加说明"), self)
        justify_act.triggered.connect(lambda: self.request_justify.emit(row))
        menu.addAction(justify_act)
        
        menu.addSeparator()

        # 1. 单句复查 (移到底部)
        ai_act = QAction(self.tr("🚀 单句复查"), self)
        ai_act.triggered.connect(lambda: self.request_ai_check.emit(row))
        menu.addAction(ai_act)
        menu.addAction(justify_act)
        
        menu.addSeparator()
        
        # 6. 删除
        del_act = QAction(self.tr("🗑️ 删除行"), self)
        del_act.triggered.connect(lambda: self.request_delete.emit(row))
        menu.addAction(del_act)
        
        menu.exec(self.viewport().mapToGlobal(pos))

    def copy_text(self, row, mode):
        """复制文本"""
        item = self.subtitle_data[row]
        key = mode # 'source' or 'target'
        data_obj = item.get(key, {})
        text = data_obj.get('text', '') if isinstance(data_obj, dict) else str(data_obj)
        QApplication.clipboard().setText(text)

    def select_row_at_time(self, seconds):
        """根据视频时间选中行（供外部同步调用）"""
        if not self.subtitle_data or not self.has_timestamps:
            return
            
        for i, item in enumerate(self.subtitle_data):
            source = item.get('source', {})
            if not isinstance(source, dict): continue
            
            if source.get('start', 0) <= seconds <= source.get('end', 0):
                # 如果当前已经是这行，就不重复选（避免死循环或闪烁）
                if self.currentRow() != i:
                    self.blockSignals(True) # 避免触发跳转循环
                    self.selectRow(i)
                    self.scrollToItem(self.item(i, 0), QAbstractItemView.ScrollHint.PositionAtCenter)
                    self.blockSignals(False)
                break
