from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsItem, QInputDialog, QMenu
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QColor, QPen, QBrush, QFont, QLinearGradient, QPainter, QAction

TRACK_HEIGHT = 32 
SNAP_THRESHOLD_PX = 15 # 扩大磁吸范围
HANDLE_WIDTH = 8      # 边缘操作把手宽度

class SubtitleItem(QGraphicsRectItem):
    def __init__(self, event_idx, store, parent_view):
        super().__init__()
        self.event_idx = event_idx
        self.store = store
        self.parent_view = parent_view
        
        # 默认调色盘
        self.color_list = [
            "#3498db", "#e74c3c", "#2ecc71", "#f1c40f", 
            "#9b59b6", "#e67e22", "#1abc9c", "#34495e"
        ]
        
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True) 
        
        # 交互状态
        self.is_resizing_left = False
        self.is_resizing_right = False
        self.is_moving = False
        
        self.mouse_press_scene_x = 0
        self.original_item_pos_x = 0
        self.original_start_ms = 0
        self.original_end_ms = 0
        self.original_track = 0
        
        # 初始刷新
        self.update_from_store()

    def update_from_store(self):
        event = self.store.get_event(self.event_idx)
        if not event: return
        
        self.start_ms = event.start
        self.end_ms = event.end
        self.text = event.plaintext
        
        try:
            if event.effect and event.effect.isdigit():
                self.track_idx = int(event.effect)
            elif event.name and event.name.isdigit():
                self.track_idx = int(event.name)
            else:
                self.track_idx = 0
        except:
            self.track_idx = 0
            
        self.update_appearance()
        self.update_rect()

    def update_appearance(self):
        # 颜色逻辑：优先从分组获取颜色，否则使用轨道颜色
        group_info = self.store.get_group_info(self.store.get_event(self.event_idx).name)
        if group_info and "color" in group_info:
            base_color = QColor(group_info["color"])
        else:
            base_color = QColor(self.color_list[self.track_idx % len(self.color_list)])
        
        self.update_brush(base_color)

    def update_brush(self, base_color):
        """根据当前轨道和选中状态更新颜色"""
        self.base_color = base_color
        self.setBrush(QBrush(base_color))
        self.setPen(QPen(QColor(0, 0, 0, 40), 1))

    def update_rect(self):
        pps = self.parent_view.container.pps
        w = (self.end_ms - self.start_ms) * pps
        self.setRect(0, 0, max(w, 2.0), TRACK_HEIGHT - 6)
        self.setPos(self.start_ms * pps, self.track_idx * TRACK_HEIGHT + 3)

    def itemChange(self, change, value):
        # 禁用原生的位置改变逻辑，使用自定义 mouseMove 以完全消除跳变
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        pos = event.pos()
        rect = self.rect()
        
        # 判定点击区域
        if pos.x() < HANDLE_WIDTH:
            self.is_resizing_left = True
        elif pos.x() > rect.width() - HANDLE_WIDTH:
            self.is_resizing_right = True
        else:
            self.is_moving = True
            
        self.mouse_press_scene_x = event.scenePos().x()
        self.original_item_pos_x = self.pos().x()
        self.original_start_ms = self.start_ms
        self.original_end_ms = self.end_ms
        self.original_track = self.track_idx
        
        # 强制置顶
        self.setZValue(100)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        container = self.parent_view.container
        pps = container.pps
        delta_x = event.scenePos().x() - self.mouse_press_scene_x
        
        if self.is_moving:
            # 1. 计算新位置 (绝对稳定，无跳变)
            new_x = self.original_item_pos_x + delta_x
            new_ms = new_x / pps
            duration = self.original_end_ms - self.original_start_ms
            
            # 轨道检测
            new_y = event.scenePos().y() if event.scenePos().y() > 0 else 0
            new_track = round((new_y - 3) / TRACK_HEIGHT)
            new_track = max(0, min(new_track, container.max_tracks - 1))
            
            snapped_ms = new_ms
            best_dist_ms = SNAP_THRESHOLD_PX / pps
            
            # 扩大搜索域：针对超长字幕块或快速移动，雷达范围提升至 1000px
            search_rect = QRectF(new_x - 500, new_track * TRACK_HEIGHT, 1000, TRACK_HEIGHT)
            nearby = self.scene().items(search_rect)
            
            # 优先级：播放头 > 其它块
            playhead_ms = container.play_time_ms
            if abs(new_ms - playhead_ms) < best_dist_ms:
                snapped_ms = playhead_ms
            elif abs((new_ms + duration) - playhead_ms) < best_dist_ms:
                snapped_ms = playhead_ms - duration
            # B. 磁吸其它块
            if snapped_ms == new_ms: # 如果还没吸到播放头
                # 按照距离排序，优先吸附更近的
                items_with_dist = []
                for item in nearby:
                    if isinstance(item, SubtitleItem) and item != self and item.track_idx == new_track:
                        # 计算各种可能的对齐距离
                        dists = [
                            (abs(new_ms - item.end_ms), item.end_ms), # 当前块起始点吸附前一个块结束点
                            (abs((new_ms + duration) - item.start_ms), item.start_ms - duration) # 当前块结束点吸附后一个块起始点
                        ]
                        for d, val in dists:
                            if d < best_dist_ms:
                                items_with_dist.append((d, val))
                
                if items_with_dist:
                    items_with_dist.sort() # 距离最小优先
                    snapped_ms = items_with_dist[0][1]
            
            # 3. 更新内存
            self.start_ms = max(0, snapped_ms)
            self.end_ms = self.start_ms + duration
            self.track_idx = new_track
            self.update_rect()
            
        elif self.is_resizing_left or self.is_resizing_right:
            delta_ms = delta_x / pps
            snapped_delta_ms = delta_ms # 默认不吸附
            playhead_ms = container.play_time_ms
            
            if self.is_resizing_right:
                new_end = self.original_end_ms + delta_ms
                # 磁吸检测
                if abs(new_end - playhead_ms) < (SNAP_THRESHOLD_PX / pps):
                    new_end = playhead_ms
                
                if new_end > self.start_ms + 20:
                    self.end_ms = new_end
            else:
                new_start = self.original_start_ms + delta_ms
                if abs(new_start - playhead_ms) < (SNAP_THRESHOLD_PX / pps):
                    new_start = playhead_ms
                    
                if new_start < self.end_ms - 20:
                    self.start_ms = max(0, new_start)
            
            self.update_rect()
            
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """双击编辑文字"""
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(None, "修改字幕文本", "文本内容:", text=self.text)
        if ok:
            # 修改时保留现有所有标签，仅替换文本部分
            # 这是一次简单的追加/替换
            event_obj = self.store.get_event(self.event_idx)
            import re
            tags = "".join(re.findall(r"\{.*?\}", event_obj.text))
            new_raw = tags + text
            self.store.update_event(self.event_idx, text=new_raw)
            self.update_from_store()
            self.update()

    def mouseReleaseEvent(self, event):
        self.is_moving = False
        self.is_resizing_left = False
        self.is_resizing_right = False
        self.setZValue(1)
        
        self.store.update_event(self.event_idx, 
                                start=int(self.start_ms), 
                                end=int(self.end_ms),
                                effect=str(self.track_idx))
        super().mouseReleaseEvent(event)

    def hoverMoveEvent(self, event):
        pos = event.pos()
        rect = self.rect()
        if pos.x() < HANDLE_WIDTH or pos.x() > rect.width() - HANDLE_WIDTH:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor) # 使用常规箭头
        super().hoverMoveEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        
        # 快速对齐子菜单 (Sync with List)
        align_label_map = {
            1: "左下 (an1)", 2: "中下 (an2)", 3: "右下 (an3)",
            4: "左中 (an4)", 5: "正中 (an5)", 6: "右中 (an6)",
            7: "左上 (an7)", 8: "中上 (an8)", 9: "右上 (an9)"
        }
        align_menu = menu.addMenu("快速对齐 (Alignment)")
        for val, label in align_label_map.items():
            act = align_menu.addAction(label)
            act.triggered.connect(lambda checked, v=val: self.apply_alignment(v))
        
        menu.addSeparator()

        groups_menu = menu.addMenu("设定分组")
        groups = self.store.get_all_groups()
        for g_name in sorted(groups.keys()):
            action = groups_menu.addAction(g_name)
            action.triggered.connect(lambda checked, n=g_name: self.store.assign_group_to_events([self.event_idx], n))
            
        styles_menu = menu.addMenu("覆盖样式")
        if self.store.subs:
            for s_name in sorted(self.store.subs.styles.keys()):
                action = styles_menu.addAction(s_name)
                action.triggered.connect(lambda checked, s=s_name: self.store.update_event(self.event_idx, style=s))
        
        menu.addSeparator()
        action_del = menu.addAction("删除")
        action_del.triggered.connect(lambda: self.store.delete_events([self.event_idx]))
        menu.exec(event.screenPos())

    def apply_alignment(self, align_val):
        """批量应用对齐标签"""
        import re
        ev = self.store.get_event(self.event_idx)
        if not ev: return
        
        tag = f"\\an{align_val}"
        if "{" in ev.text:
            if re.search(r"\{\\an\d", ev.text):
                    new_text = re.sub(r"(\\an\d)", tag, ev.text)
            else:
                    new_text = ev.text.replace("{", f"{{{tag}", 1)
        else:
            new_text = f"{{{tag}}}{ev.text}"
        
        self.store.update_event(self.event_idx, text=new_text)

    def paint(self, painter, option, widget):
        rect = self.rect()
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        is_small = (rect.width() * lod) < 15
        
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        color = self.base_color
        if self.isSelected():
            painter.setBrush(QBrush(color.lighter(120)))
            # 回归专业蓝色风格，移除橙色
            painter.setPen(QPen(QColor("#3498db"), 2))
        else:
            painter.setBrush(QBrush(color))
            if is_small:
                painter.setPen(Qt.PenStyle.NoPen)
            else:
                painter.setPen(QPen(color.darker(130), 1))
            
        painter.drawRoundedRect(rect, 2, 2)
        
        # 绘制极简把手 (仅在高亮或悬停时隐约可见)
        if not is_small and rect.width() > HANDLE_WIDTH * 2:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 30)))
            # 极简线条感把手
            painter.drawRect(QRectF(2, 4, 2, rect.height() - 8))
            painter.drawRect(QRectF(rect.width() - 4, 4, 2, rect.height() - 8))
        
        if not is_small and rect.width() > 20:
            painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
            painter.drawLine(int(rect.left()+1), int(rect.top()+1), int(rect.right()-1), int(rect.top()+1))
            
            painter.setPen(QColor("#FFFFFF"))
            font = QFont("Segoe UI", 9)
            if not font.exactMatch(): font = QFont("Microsoft YaHei UI", 9)
            painter.setFont(font)
            
            text_rect = rect.adjusted(HANDLE_WIDTH + 2, 0, -HANDLE_WIDTH - 2, 0)
            metrics = painter.fontMetrics()
            elided_text = metrics.elidedText(self.text, Qt.TextElideMode.ElideRight, int(text_rect.width()))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_text)
