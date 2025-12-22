from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, QTimer, QElapsedTimer, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QFontMetrics, QPainterPath, QPainterPathStroker, QFontDatabase, QPixmap, QBrush, QLinearGradient
import logging
from ..core.subtitle_store import SubtitleStore
from functools import lru_cache
import re
import bisect

logger = logging.getLogger(__name__)

class OverlayWindow(QWidget):
    """
    全透明顶层覆盖窗口，负责绘制字幕 (In-Place Optimized)
    
    性能优化说明 (Performance Optimizations):
    1. 智能重绘 (Smart Redraw): 仅在字幕内容变化或存在动画(渐变/移动/卡拉OK)时刷新，避免静态画面的无效重绘。
    2. 二分查找 (Binary Search): 使用 bisect 快速定位当前时间点的活跃字幕，避免遍历全量列表。
    3. 时钟解耦 (Timer Decoupling): 播放时忽略播放器的低频时间同步信号，由内部 60FPS 时钟接管，避免双重信号竞争。
    4. 缓存机制 (Caching): 维持原有的 LRU Cache 用于解析和纹理生成。
    """
    def __init__(self, store: SubtitleStore, parent=None):
        super().__init__(parent)
        self.store = store
        
        # 内部时钟，用于 60FPS 平滑动画
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(16) # ~60 FPS
        self.animation_timer.timeout.connect(self._on_animation_frame)
        
        self.is_playing = False
        self.base_time_ms = 0      # 播放器报告的基准时间
        self.last_update_tick = 0  # 收到基准时间时的系统 tick
        self.interpolated_time_ms = 0
        self.preview_style = None  # 当前正处于编辑器预览中的样式
        
        # 缓存的排序时间列表，用于二分查找
        # List of start times correspond to self.store.subs.events
        self._cached_start_times = [] 
        self._last_active_indices = set() # 上一帧活跃的事件索引集合
        
        # 预览自动隐藏定时器
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(lambda: self.set_preview_style(None))
        
        # 窗口属性配置
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # 默认字体缓存
        self.font_cache = {}
        # 纹理缓存 (Rendered Pixmap)
        self.pixmap_cache = {}
        
        # 性能标志
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        
        # 监听数据变更以重建索引
        self.store.dataChanged.connect(self._rebuild_search_index)
        # 初始化索引
        self._rebuild_search_index()

    def _rebuild_search_index(self):
        """重建用于二分查找的时间索引"""
        if self.store and self.store.subs:
            # 假设 store 中的事件已经按 start 排序 (add_event/update_event 会保证)
            self._cached_start_times = [e.start for e in self.store.subs.events]
            # 强制清空上一帧状态以触发重绘
            self._last_active_indices = set()
            self.update()

    def resizeEvent(self, event):
        """窗口大小改变时清空缓存"""
        self.pixmap_cache.clear()
        super().resizeEvent(event)

    def set_playing_state(self, playing: bool):
        """设置播放状态并控制动画时钟"""
        self.is_playing = playing
        if playing:
            self.animation_timer.start()
            self.last_update_tick =  QElapsedTimer().msecsSinceReference()
        else:
            self.animation_timer.stop()
            # 暂停时强制重绘一次以确保画面准确
            self.update()

    def closeEvent(self, event):
        """关闭事件处理：停止所有定时器"""
        if self.animation_timer:
            self.animation_timer.stop()
        super().closeEvent(event)

    def set_current_time(self, ms: int):
        """
        接收播放器报告的 '准确时间' (低频, ~30-100ms 一次)
        优化：如果正在播放中，不要在此处触发 update()，防止与动画时钟冲突导致重绘抖动。
        """
        self.base_time_ms = ms
        # 每次校准插值时间
        self.interpolated_time_ms = ms
        
        if not self.is_playing:
            # 只有暂停时，才通过此信号驱动重绘 (例如拖动时间轴)
            self.update() 
        else:
            # 播放中，仅更新时间数据，重绘由 _on_animation_frame 接管
            pass

    def _on_animation_frame(self):
        """
        高频动画帧 (60FPS)
        执行智能重绘检测：仅当画面确实需要变更时调用 update()
        """
        if not self.is_playing:
            return

        # 简单的线性推演
        self.interpolated_time_ms += 16
        current_ms = self.interpolated_time_ms
        
        # --- Smart Redraw Logic ---
        
        # 1. 查找当前活跃的事件索引
        active_indices = self._find_active_event_indices(current_ms)
        active_set = set(active_indices)
        
        should_redraw = False
        
        # 2. 检查：活跃集合是否发生变化 (有字幕出现或消失)
        if active_set != self._last_active_indices:
            should_redraw = True
        else:
            # 3. 检查：保持不变的字幕中，是否存在需要逐帧更新的动画 (Fade, Move, Karaoke)
            # 如果全是静态文本，则无需重绘
            for idx in active_indices:
                event = self.store.get_event(idx)
                if not event: continue
                # 获取该事件的解析元数据（利用 Cache）
                parsed = self._get_parsed_event_data_wrapper(event)
                if parsed and parsed.get('animated', False):
                    should_redraw = True
                    break
        
        self._last_active_indices = active_set
        
        if should_redraw:
            self.update()

    def _find_active_event_indices(self, current_ms):
        """
        极速查找活跃事件索引
        优化：不遍历 events[:idx]，而是利用事件通常有最大时长限制的特点，回溯查找。
        """
        # 找到第一个 start > current_ms 的位置
        idx = bisect.bisect_right(self._cached_start_times, current_ms)
        
        active_indices = []
        events = self.store.subs.events
        
        # 假设字幕最大时长不超过 30 秒 (SSA 规范常见情况)
        # 向上回溯查找 end_ms >= current_ms 的项
        MAX_LOOKBACK = 200 # 限制回溯数量，防止超长事件导致的卡顿
        for i in range(idx - 1, max(-1, idx - 1 - MAX_LOOKBACK), -1):
            if events[i].end >= current_ms:
                active_indices.append(i)
            elif events[i].start < current_ms - 60000:
                # 如果当前项的开始时间已经早于 1 分钟，且结束时间还没到当前时间，
                # 基本可以认为更早的项也不可能活跃（除非有持续一分钟以上的字幕）
                break
                
        return active_indices

    def _sync_overlay(self):
        """
        同步 OverlayWindow 的几何尺寸和位置，使其完全覆盖父窗口。
        这确保了字幕渲染的坐标系 (0,0) 对齐父窗口的左上角。
        """
        if not self.parentWidget():
            logger.warning("OverlayWindow has no parent, cannot sync geometry.")
            return

        # 获取父窗口的几何尺寸
        parent_rect = self.parentWidget().rect()
        if parent_rect.width() <= 0 or parent_rect.height() <= 0:
            logger.debug("Parent widget has invalid size, skipping overlay sync.")
            return

        # 将父窗口的本地坐标 (0,0) 转换为屏幕全局坐标
        global_pos = self.parentWidget().mapToGlobal(QPointF(0, 0)).toPoint()

        # 强制更新 OverlayWindow 的几何尺寸和位置
        self.setGeometry(global_pos.x(), global_pos.y(), parent_rect.width(), parent_rect.height())
        logger.debug(f"Overlay synced to parent: pos={global_pos}, size={parent_rect.size()}")

    def paintEvent(self, event):
        """核心绘制逻辑"""
        if not self.store:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 1. 绘制实时样式预览 (优先级最高)
        if self.preview_style:
            self._draw_preview(painter, self.preview_style)
            return

        current_ms = self.interpolated_time_ms
        
        # 利用 bisect 获取
        active_indices = self._find_active_event_indices(current_ms)
        
        if not active_indices:
            return

        # 2. 绘制所有活跃字幕
        for idx in active_indices:
            ev = self.store.get_event(idx)
            if ev:
                # 显隐判断 (多轨管理核心)
                # event.name 对应的是分组名
                gname = ev.name if ev.name else "Default"
                if not self.store.is_group_visible(gname):
                    continue
                    
                self._draw_event(painter, ev, current_ms)

    def set_preview_style(self, style):
        """设置预览样式，触发重绘"""
        self.preview_style = style
        if style:
            self.preview_timer.start(3000)
        self.update()

    def _draw_preview(self, painter: QPainter, style):
        """在屏幕上绘制预览文本，尊重样式的对齐和边距"""
        # 构建一个模拟事件
        from pysubs2 import SSAEvent
        import re
        
        # 尝试获取当前时间点的活跃字幕文本，作为预览内容（更有代入感）
        current_ms = self.interpolated_time_ms
        active_indices = self._find_active_event_indices(current_ms)
        
        preview_text = "样式预览效果 (Style Preview)"
        if active_indices:
            ev = self.store.get_event(active_indices[0])
            if ev:
                # 移除所有 ASS 标签以纯文本显示
                clean = re.sub(r"\{.*?\}", "", ev.text).strip()
                if clean:
                    preview_text = clean.split('\n')[0] # 取第一行即可

        # 不要硬编码 \an 和 \pos，以便预览 Style 自身的对齐和边距属性
        dummy_ev = SSAEvent(text=preview_text)
        dummy_ev.style = "Dummy" 
        
        old_style = self.store.subs.styles.get("Dummy")
        self.store.subs.styles["Dummy"] = style
        try:
            self._draw_event(painter, dummy_ev, current_ms)
        finally:
            if old_style: self.store.subs.styles["Dummy"] = old_style
            else: del self.store.subs.styles["Dummy"]

    def _get_parsed_event_data_wrapper(self, ev):
        """辅助包装器，用于提取样式键并调用缓存的解析器"""
        style = self.store.subs.styles.get(ev.style, self.store.subs.styles.get("Default"))
        if not style:
             from pysubs2 import SSAStyle
             style = SSAStyle()
             
        base_style_key = (
            style.fontname, style.fontsize, style.bold, style.italic,
            str(style.primarycolor), str(style.outlinecolor), str(style.backcolor),
            style.alignment, style.borderstyle, style.outline, style.shadow,
            style.marginl, style.marginr, style.marginv,
            self.store.extra_style_data.get(ev.style, {}).get("font_style", "")
        )
        return self._get_parsed_event_data(ev.text, base_style_key)

    def _draw_event(self, painter: QPainter, ev, current_ms):
        """绘制单个字幕事件"""
        # --- 基本参数提取 ---
        parsed = self._get_parsed_event_data_wrapper(ev)
        if not parsed: return
        
        # 计算动态不透明度 (Fade)
        opacity = 1.0
        if parsed['fade']:
            t1, t2 = parsed['fade']
            elapsed = current_ms - ev.start
            remaining = ev.end - current_ms
            
            fade_in_op = 1.0
            if t1 > 0:
                fade_in_op = max(0.0, min(1.0, elapsed / t1))
            fade_out_op = 1.0
            if t2 > 0:
                fade_out_op = max(0.0, min(1.0, remaining / t2))
            opacity = min(fade_in_op, fade_out_op)
            
        if opacity <= 0: return

        # 分辨率缩放参数
        play_res_y = float(self.store.subs.info.get("PlayResY", 720))
        if play_res_y <= 0: play_res_y = 720.0
        scale_ratio = self.height() / play_res_y
        rect = self.rect()

        clean_text = parsed['clean_text']
        eff_key = parsed['eff_font_key']
        eff_outline = parsed['outline']
        eff_align = parsed['align']
        eff_shadow = parsed['shadow']
        color_key = parsed['color_key']
        override_pos = None
        
        # 处理缩放
        eff_outline = eff_outline * scale_ratio
        eff_shadow = eff_shadow * scale_ratio
        
        # 字体缩放
        # Key 现在包含 font_style 名: (fontname, size, b, i, style_name)
        scaled_font_key = (eff_key[0], int(eff_key[1] * scale_ratio), eff_key[2], eff_key[3], eff_key[4])
        font = self._get_style_font_by_key(scaled_font_key)
        
        if parsed['pos']:
            px, py = parsed['pos']
            override_pos = (px * scale_ratio, py * scale_ratio)
            
        ml = parsed['margins'][0] * scale_ratio
        mr = parsed['margins'][1] * scale_ratio
        mv = parsed['margins'][2] * scale_ratio
        
        if ml == 0: ml = 20 * scale_ratio
        if mr == 0: mr = 20 * scale_ratio
        if mv == 0: mv = 20 * scale_ratio

        # 构建缓存键 (去掉 rect.width()，改用内容相关的尺寸信息)
        cache_key = (
            clean_text, 
            scaled_font_key, 
            eff_outline, 
            eff_align, 
            eff_shadow,
            color_key,
            (ml, mr, mv)
        )
        
        pixmap = None
        draw_offset = QPointF(0,0)
        
        if cache_key in self.pixmap_cache:
            pixmap, draw_offset = self.pixmap_cache[cache_key]
        else:
            # 需要 style 对象用于颜色解析
            style = self.store.subs.styles.get(ev.style, self.store.subs.styles.get("Default"))
            if not style:
                from pysubs2 import SSAStyle
                style = SSAStyle()
                
            pixmap, draw_offset = self._render_subtitle_texture(
                clean_text, font, eff_align, override_pos, 
                rect, scale_ratio, ml, mr, mv, eff_outline, eff_shadow,
                style, ev.style
            )
            
            # Simple GC for cache
            if len(self.pixmap_cache) > 200: 
                self.pixmap_cache.clear()
            self.pixmap_cache[cache_key] = (pixmap, draw_offset)
            
        if pixmap and not pixmap.isNull():
            painter.save()
            painter.setOpacity(opacity)
            painter.drawPixmap(draw_offset, pixmap)
            painter.restore()

    @lru_cache(maxsize=1024)
    def _get_parsed_event_data(self, text, style_key):
        """
        带缓存的 ASS标签解析
        """
        # 解包默认值
        (s_font, s_size, s_bold, s_italic, s_pri, s_out, s_back, s_align, s_bord_style, s_bord, s_shad, s_ml, s_mr, s_mv, s_style_name) = style_key
        
        # 0. 动画检测 (Optimization Flag)
        # \fad, \move, \t, \k (Karaoke) imply animation
        is_animated = False
        if r"\fad" in text or r"\move" in text or r"\t" in text or r"\k" in text:
            is_animated = True

        # 1. Fade
        fade = None
        fad_match = re.search(r"\\fad\((\d+),(\d+)\)", text)
        if fad_match:
            fade = (float(fad_match.group(1)), float(fad_match.group(2)))
            
        # 2. 字体覆盖 (Font Overrides)
        fn_match = re.search(r"\\fn([^}\\]+)", text)
        eff_fontname = fn_match.group(1) if fn_match else s_font
        
        fs_match = re.search(r"\\fs(\d+(\.\d+)?)", text)
        eff_fontsize = float(fs_match.group(1)) if fs_match else s_size
        
        b_match = re.search(r"\\b(\d+)", text)
        eff_bold = s_bold
        if b_match: eff_bold = (int(b_match.group(1)) > 0)
            
        i_match = re.search(r"\\i([01])", text)
        eff_italic = s_italic
        if i_match: eff_italic = (i_match.group(1) == '1')
        
        eff_font_key = (eff_fontname, eff_fontsize, eff_bold, eff_italic, s_style_name)
            
        # 3. 颜色覆盖 (Color Overrides)
        c_match = re.search(r"\\(?:c|1c)&H([0-9A-Fa-f]+)&", text)
        eff_pri = f"&H{c_match.group(1)}" if c_match else s_pri
        
        c3_match = re.search(r"\\3c&H([0-9A-Fa-f]+)&", text)
        eff_out = f"&H{c3_match.group(1)}" if c3_match else s_out
        
        eff_back = s_back 
        color_key = (eff_pri, eff_out, eff_back)

        # 4. 布局覆盖 (Layout Overrides)
        an_match = re.search(r"\\an(\d)", text)
        eff_align = int(an_match.group(1)) if an_match else s_align
        
        bord_match = re.search(r"\\bord(\d+(\.\d+)?)", text)
        eff_outline = float(bord_match.group(1)) if bord_match else s_bord
        
        shad_match = re.search(r"\\shad(\d+(\.\d+)?)", text)
        eff_shadow = float(shad_match.group(1)) if shad_match else s_shad
        
        # 5. 位置 (Position)
        pos = None
        pos_match = re.search(r"\\pos\((-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\)", text)
        if pos_match:
            pos = (float(pos_match.group(1)), float(pos_match.group(2)))
            
        # 6. 清理文本 (Clean Text)
        clean_text = re.sub(r"\{.*?\}", "", text)
        clean_text = clean_text.replace(r"\N", "\n").replace(r"\n", "\n").replace(r"\h", " ")
        if not clean_text.strip(): return None
        
        return {
            'clean_text': clean_text,
            'fade': fade,
            'animated': is_animated, # New Flag
            'eff_font_key': eff_font_key,
            'color_key': color_key,
            'align': eff_align,
            'outline': eff_outline,
            'shadow': eff_shadow,
            'pos': pos,
            'margins': (s_ml, s_mr, s_mv)
        }

    def _render_subtitle_texture(self, text, font, align, pos, rect, scale, ml, mr, mv, outline, shadow, style, style_name):
        """生成最小化纹理和位置偏移"""
        # 1. 生成屏幕坐标系的 Path
        path, outline_path = self._generate_paths(text, font, align, pos, rect, scale, ml, mr, mv, outline)
        
        # 2. 计算总包围盒 (Text + Outline + Shadow)
        total_rect = path.boundingRect()
        if outline_path:
            total_rect = total_rect.united(outline_path.boundingRect())
            
        shad_depth = shadow * scale
        if shad_depth > 0.1:
            shadow_rect = total_rect.translated(shad_depth, shad_depth)
            total_rect = total_rect.united(shadow_rect)
            
        # 稍微 扩一点避免边缘裁剪 (增加到 10px 以支持超大描边)
        brect = total_rect.toAlignedRect().adjusted(-10, -10, 10, 10)
        
        if brect.width() <= 0 or brect.height() <= 0:
            return QPixmap(), QPointF(0,0)
            
        # 3. 创建 Pixmap
        # High DPI support could be added here by multiplying size by devicePixelRatio
        pixmap = QPixmap(brect.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        
        pm_painter = QPainter(pixmap)
        pm_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pm_painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        # 4. 坐标系平移
        pm_painter.translate(-brect.topLeft())
        
        # 5. 绘制内容
        
        # Shadow
        if shad_depth > 0.1:
            back_color = self._parse_ass_color(style.backcolor)
            pm_painter.setPen(Qt.PenStyle.NoPen)
            pm_painter.setBrush(back_color)
            src = outline_path if outline_path else path
            pm_painter.drawPath(src.translated(shad_depth, shad_depth))
            
        # Outline
        # QUICK FIX REUSE LOGIC
        c_match = re.search(r"\\(?:c|1c)&H([0-9A-Fa-f]+)&", text)
        eff_pri = f"&H{c_match.group(1)}" if c_match else style.primarycolor
        
        c3_match = re.search(r"\\3c&H([0-9A-Fa-f]+)&", text)
        eff_out = f"&H{c3_match.group(1)}" if c3_match else style.outlinecolor
        
        pri_color = self._parse_ass_color(eff_pri)
        out_color = self._parse_ass_color(eff_out)
        
        if outline_path:
            pm_painter.setPen(Qt.PenStyle.NoPen)
            pm_painter.setBrush(out_color)
            pm_painter.drawPath(outline_path)
            
        # Fill / Gradient
        gradient_brush = None
        if style_name in self.store.extra_style_data:
             g_meta = self.store.extra_style_data[style_name]
             if g_meta.get("gradient_enabled", False):
                p_rect = path.boundingRect()
                if p_rect.width() > 1:
                    l_grad = QLinearGradient(p_rect.left(), 0, p_rect.right(), 0)
                    c_start = g_meta.get("gradient_start", pri_color)
                    c_end = g_meta.get("gradient_end", QColor("#FF0000"))
                    l_grad.setColorAt(0.0, c_start)
                    l_grad.setColorAt(1.0, c_end)
                    gradient_brush = QBrush(l_grad)
        
        if gradient_brush:
            pm_painter.setBrush(gradient_brush)
        else:
            pm_painter.setBrush(pri_color)
            
        pm_painter.drawPath(path)
        pm_painter.end()
        
        return pixmap, brect.topLeft()

    def _generate_paths(self, text, font, alignment, override_pos, rect, scale_ratio, ml, mr, mv, outline_width):
        """生成文字路径和描边路径"""
        fm = QFontMetrics(font)
        lines = text.split('\n')
        total_h = len(lines) * fm.height()
        
        # 计算布局起点 (Origin)
        start_x = 0
        start_y = 0
        
        if override_pos:
            max_w = 0
            for line in lines: 
                w = fm.horizontalAdvance(line)
                if w > max_w: max_w = w
            
            # X Anchor
            if alignment in [1, 4, 7]: # Left
                start_x = override_pos[0]
            elif alignment in [2, 5, 8]: # Center
                start_x = override_pos[0] - max_w / 2
            elif alignment in [3, 6, 9]: # Right
                start_x = override_pos[0] - max_w
                
            # Y Anchor
            if alignment in [1, 2, 3]: # Bottom
                start_y = override_pos[1] - total_h
            elif alignment in [4, 5, 6]: # Center
                start_y = override_pos[1] - total_h / 2
            elif alignment in [7, 8, 9]: # Top
                start_y = override_pos[1]
                
            start_y += fm.ascent()
            
        else:
            # Margin Model
            avail_w = rect.width() - ml - mr
            
            # Y Start
            if alignment in [1, 2, 3]: # Bottom
                start_y = (rect.height() - mv) - total_h + fm.ascent()
            elif alignment in [7, 8, 9]: # Top
                start_y = mv + fm.ascent()
            else: # Mid
                 start_y = (rect.height() / 2) - (total_h / 2) + fm.ascent()
            
            start_x = ml
            
        path = QPainterPath()
        current_y = start_y
        
        for line in lines:
            line_w = fm.horizontalAdvance(line)
            line_x = start_x
            
            if not override_pos:
                avail_w = rect.width() - ml - mr
                if alignment in [1, 4, 7]: # Left
                    line_x = ml
                elif alignment in [2, 5, 8]: # Center
                    line_x = ml + (avail_w - line_w) / 2
                elif alignment in [3, 6, 9]: # Right
                    line_x = (rect.width() - mr) - line_w
            else:
                pass 

            path.addText(QPointF(line_x, current_y), font, line)
            current_y += fm.height()
            
        outline_path = None
        # 注意：outline_width 应该是已经根据 scale_ratio 缩放过的绝对像素值
        eff_outline_w = outline_width 
        if eff_outline_w >= 0.1:
            stroker = QPainterPathStroker()
            stroker.setWidth(eff_outline_w * 2)
            stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
            outline_path = stroker.createStroke(path)
            
        return path, outline_path

    def _get_style_font_by_key(self, key):
        """Helper to get font from cache using key directly"""
        if key in self.font_cache:
            return self.font_cache[key]
        
        # key: (fontname, pixel_size, bold, italic, style_name)
        fontname, pixel_size, bold, italic, style_name = key
        
        if pixel_size < 1: pixel_size = 10
        
        font = QFont(fontname)
        font.setPixelSize(pixel_size)
        
        # 如果存在具体的 VF 样式名，则优先使用它实现精准字重控制
        if style_name:
            font.setStyleName(style_name)
        else:
            font.setBold(bold)
            font.setItalic(italic)
            
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        
        self.font_cache[key] = font
        return font

    def _get_alignment_flags(self, alignment):
        flags = Qt.TextFlag.TextWordWrap
        
        if alignment in [1, 4, 7]: flags |= Qt.AlignmentFlag.AlignLeft
        elif alignment in [2, 5, 8]: flags |= Qt.AlignmentFlag.AlignCenter
        elif alignment in [3, 6, 9]: flags |= Qt.AlignmentFlag.AlignRight
        
        if alignment in [1, 2, 3]: flags |= Qt.AlignmentFlag.AlignBottom
        elif alignment in [4, 5, 6]: flags |= Qt.AlignmentFlag.AlignVCenter
        elif alignment in [7, 8, 9]: flags |= Qt.AlignmentFlag.AlignTop
        
        return flags

    def _parse_ass_color(self, ass_color):
        """支持 pysubs2.Color 对象和 &HAABBGGRR& 格式字符串"""
        if hasattr(ass_color, 'r'):
            return QColor(ass_color.r, ass_color.g, ass_color.b, 255 - ass_color.a)
        
        # 处理字符串格式 &H(AA)BBGGRR&
        if isinstance(ass_color, str) and "&H" in ass_color:
            s = ass_color.strip("&H").strip("&")
            try:
                # 倒着取 (ASS 是 BGR 顺序)
                if len(s) >= 6:
                    r = int(s[-2:], 16)
                    g = int(s[-4:-2], 16)
                    b = int(s[-6:-4], 16)
                    a = 0
                    if len(s) >= 8: # 包含 Alpha
                        a = int(s[-8:-6], 16)
                    return QColor(r, g, b, 255 - a)
            except:
                pass
        return QColor(Qt.GlobalColor.white)

    def clear(self):
        """清空画面"""
        self.interpolated_time_ms = -1
        self.update()
