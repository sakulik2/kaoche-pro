import logging
import os
import pysubs2
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

class SubtitleStore(QObject):
    """
    SubStudio 核心数据存储
    单一事实来源 (Single Source of Truth)
    """
    # 信号定义
    fileLoaded = pyqtSignal(str) # 文件名
    dataChanged = pyqtSignal() # 任何改动触发
    eventsChanged = pyqtSignal(list, str) # 变更的索引, 原因
    selectionChanged = pyqtSignal(list) # 选中的索引
    styleChanged = pyqtSignal(str) # 样式名
    groupsChanged = pyqtSignal() # 分组信息变更
    
    def __init__(self):
        super().__init__()
        self.filename = None
        self.subs = pysubs2.SSAFile() # 默认为空文档
        self.is_dirty = False
        self.selected_indices = [] # 选中的索引列表
        
        # 分组管理数据结构
        # groups: { group_name: { "style": style_name, "color": "#RRGGBB" } }
        self.groups = {}
        self._init_default_group()

        # 样式扩展元数据 (用于存储 Gradient 等非标准运行时属性)
        # 格式: { style_name: { "gradient_enabled": bool, "gradient_start": QColor, "gradient_end": QColor } }
        self.extra_style_data = {}
        
        # 默认样式与预设初始化
        self._init_default_style()
        self.inject_standard_styles()

    def _init_default_style(self):
        """确保有一个基础默认样式"""
        if "Default" not in self.subs.styles:
            style = pysubs2.SSAStyle()
            style.fontsize = 20
            style.primarycolor = pysubs2.Color(255, 255, 255)
            self.subs.styles["Default"] = style

    def inject_standard_styles(self):
        """注入专业级预设样式 (防止非 ASS 文件显得太简陋)"""
        # 1. Studio-Standard (经典白，细描边)
        if "Studio-Standard" not in self.subs.styles:
            s1 = pysubs2.SSAStyle()
            s1.fontname = "Microsoft YaHei"
            s1.fontsize = 20
            s1.primarycolor = pysubs2.Color(255, 255, 255)
            s1.outlinecolor = pysubs2.Color(0, 0, 0)
            s1.outline = 1.0
            s1.shadow = 1.5
            self.subs.styles["Studio-Standard"] = s1
            
        # 2. Cinema-Boxed (半透明黑底白字，高对比度)
        if "Cinema-Boxed" not in self.subs.styles:
            s2 = pysubs2.SSAStyle()
            s2.fontname = "Microsoft YaHei"
            s2.fontsize = 18
            s2.primarycolor = pysubs2.Color(255, 255, 255)
            s2.backcolor = pysubs2.Color(0, 0, 0, 150) # 半透明背景
            s2.outline = 0
            s2.shadow = 0
            s2.borderstyle = 3 # 3 代表 Opaque box
            self.subs.styles["Cinema-Boxed"] = s2
            
        # 3. Energy-Highlight (活力黄，加粗)
        if "Energy-Highlight" not in self.subs.styles:
            s3 = pysubs2.SSAStyle()
            s3.fontname = "Microsoft YaHei"
            s3.fontsize = 22
            s3.primarycolor = pysubs2.Color(255, 240, 0) # 亮黄
            s3.outlinecolor = pysubs2.Color(0, 0, 0)
            s3.outline = 2.0
            s3.bold = True
            self.subs.styles["Energy-Highlight"] = s3
            
        self.styleChanged.emit("") # 广播样式库更新

    def load_file(self, path: str):
        """加载字幕文件 (支持 .srt, .ass 等 pysubs2 支持的所有格式)"""
        try:
            logger.info(f"Loading subtitle file: {path}")
            self.subs = pysubs2.load(path)
            self.filename = path
            self.is_dirty = False
            
            # 智能增强：注入预设样式
            self.inject_standard_styles()
            
            self.fileLoaded.emit(path)
            self.dataChanged.emit()
            logger.info(f"Loaded {len(self.subs)} events.")
        except Exception as e:
            logger.error(f"Failed to load file {path}: {e}")
            raise e

    def save_file(self, path: str = None):
        """保存字幕文件 (自动处理渐变编译)"""
        target_path = path or self.filename
        if not target_path:
            raise ValueError("No filename specified for save.")
        
        from .ass_compiler import AssGradientCompiler
        
        # 1. 预处理：编译渐变标签
        # 我们记录下修改过的 (index, original_text) 对，以便保存后恢复
        modified_events = []
        
        try:
            for idx, event in enumerate(self.subs.events):
                style_name = event.style
                if style_name in self.extra_style_data:
                    meta = self.extra_style_data[style_name]
                    if meta.get("gradient_enabled"):
                        original_text = event.text
                        compiled_text = AssGradientCompiler.compile_event(event, meta)
                        
                        if compiled_text != original_text:
                            event.text = compiled_text
                            modified_events.append((idx, original_text))
                            
            logger.info(f"Saving subtitle file to: {target_path} (Compiled {len(modified_events)} gradients)")
            self.subs.save(target_path)
            self.filename = target_path
            self.is_dirty = False
            
        except Exception as e:
            logger.error(f"Failed to save file {target_path}: {e}")
            raise e
            
        finally:
            # 2. 恢复：还原内存中的纯净文本
            for idx, original_text in modified_events:
                self.subs.events[idx].text = original_text
            # 恢复后无需触发 dataChanged，因为逻辑上数据并未改变，只是为了 IO 做的临时变换
    def add_event(self, start_ms: int, end_ms: int, text: str, style: str = "Default"):
        """添加一条新字幕"""
        event = pysubs2.SSAEvent(start=start_ms, end=end_ms, text=text, style=style)
        self.subs.events.append(event)
        
        # 始终保持时间顺序
        self.subs.events.sort(key=lambda e: e.start)
        
        # 标记脏状态并发送信号
        self._mark_dirty()
        # 由于 sort 了，索引全变，简单起见通知全量更新
        self.dataChanged.emit()

    def delete_events(self, indices: list[int]):
        """批量删除字幕"""
        if not indices:
            return
            
        # 从后往前删，防止索引偏移
        for i in sorted(indices, reverse=True):
            if 0 <= i < len(self.subs.events):
                del self.subs.events[i]
                
        self._mark_dirty()
        self.dataChanged.emit()

    def update_event(self, index: int, **kwargs):
        """更新单条字幕属性 (start, end, text, style)"""
        if not (0 <= index < len(self.subs.events)):
            logger.warning(f"Invalid event index: {index}")
            return
            
        event = self.subs.events[index]
        changed = False
        
        for key, value in kwargs.items():
            if hasattr(event, key):
                old_val = getattr(event, key)
                if old_val != value:
                    setattr(event, key, value)
                    changed = True
        
        if changed:
            # 如果修改了时间，可能需要重新排序
            if 'start' in kwargs:
                self.subs.events.sort(key=lambda e: e.start)
                # 排序后 index 可能变化，需要全量刷新
                self.dataChanged.emit()
            else:
                self.eventsChanged.emit([index], "update")
                
            self._mark_dirty()

    def get_event(self, index: int) -> pysubs2.SSAEvent:
        if 0 <= index < len(self.subs.events):
            return self.subs.events[index]
        return None

    def set_selection(self, indices: list[int]):
        """设置选中的字幕索引列表"""
        if self.selected_indices == indices:
            return
        self.selected_indices = indices
        self.selectionChanged.emit(indices)

    def get_all_events(self):
        return self.subs.events

    def _mark_dirty(self):
        self.is_dirty = True

    # === 分组管理方法 ===
    
    def _init_default_group(self):
        """初始化默认分组"""
        if "Default" not in self.groups:
            self.groups["Default"] = {
                "style": "Default",
                "color": "#3498db"  # 蓝色
            }
    
    def add_group(self, name: str, style: str = "Default", color: str = "#3498db"):
        """添加新分组"""
        if name in self.groups:
            logger.warning(f"分组 '{name}' 已存在")
            return False
        
        self.groups[name] = {
            "style": style,
            "color": color
        }
        self._mark_dirty()
        self.groupsChanged.emit()
        logger.info(f"创建分组: {name}")
        return True
    
    def delete_group(self, name: str):
        """删除分组"""
        if name == "Default":
            logger.warning("不能删除 Default 分组")
            return False
        
        if name not in self.groups:
            logger.warning(f"分组 '{name}' 不存在")
            return False
        
        # 将使用此分组的字幕重置为 Default
        for event in self.subs.events:
            if event.name == name:
                event.name = "Default"
        
        del self.groups[name]
        self._mark_dirty()
        self.groupsChanged.emit()
        self.dataChanged.emit()
        logger.info(f"删除分组: {name}")
        return True
    
    def update_group(self, name: str, style: str = None, color: str = None):
        """更新分组属性"""
        if name not in self.groups:
            logger.warning(f"分组 '{name}' 不存在")
            return False
        
        if style:
            self.groups[name]["style"] = style
            # 级联更新：当分组关联样式改变时，所有属于该分组的字幕也应切换样式
            updated_count = 0
            for event in self.subs.events:
                if event.name == name:
                    event.style = style
                    updated_count += 1
            if updated_count > 0:
                self.dataChanged.emit()
                
        if color:
            self.groups[name]["color"] = color
        
        self._mark_dirty()
        self.groupsChanged.emit()
        logger.info(f"更新分组: {name}")
        return True
    
    def assign_group_to_events(self, indices: list[int], group_name: str):
        """将指定字幕分配给分组，并自动应用该分组的样式"""
        if group_name not in self.groups:
            logger.warning(f"分组 '{group_name}' 不存在")
            return False
        
        group_style = self.groups[group_name]["style"]
        
        for idx in indices:
            if 0 <= idx < len(self.subs.events):
                event = self.subs.events[idx]
                event.name = group_name  # 设置 ASS Actor 字段
                event.style = group_style  # 自动应用分组的样式
        
        self._mark_dirty()
        self.dataChanged.emit()
        logger.info(f"分配 {len(indices)} 条字幕到分组: {group_name}")
        return True
    
    def get_group_info(self, name: str):
        """获取分组信息"""
        return self.groups.get(name, None)
    
    def get_all_groups(self):
        """获取所有分组"""
        return dict(self.groups)
