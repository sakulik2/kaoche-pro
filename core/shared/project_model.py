"""
项目数据模型模块
负责管理字幕数据、文件路径、项目状态以及持久化。
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ProjectModel:
    """
    项目模型类，封装了字幕数据的所有操作，支持撤销/重做（通过外部控制）及文件同步。
    管理字幕数据、源文件/目标文件路径、视频文件路径、锚定模式和全局上下文。
    """
    
    def __init__(self):
        """
        初始化 ProjectModel 实例。
        设置默认的空数据和文件路径。
        """
        self.subtitle_data: List[Dict[str, Any]] = []
        self.source_file: Optional[str] = None
        self.target_file: Optional[str] = None
        self.anchor_mode: str = 'source' # 'source', 'target', 'auto'
        self.global_context: str = ""
        self.video_file: Optional[str] = None
    
    def clear(self):
        """
        清空所有项目数据和文件路径，重置为初始状态。
        """
        self.subtitle_data = []
        self.source_file = None
        self.target_file = None
        self.video_file = None
        self.global_context = ""
        
    def get_data(self) -> List[Dict[str, Any]]:
        """
        获取当前存储的所有字幕数据。
        
        Returns:
            List[Dict[str, Any]]: 包含所有字幕条目的列表。
        """
        return self.subtitle_data
        
    def set_data(self, data: List[Dict[str, Any]]):
        """
        设置字幕数据。
        
        Args:
            data (List[Dict[str, Any]]): 要设置的字幕数据列表。
        """
        self.subtitle_data = data
        
    def count(self) -> int:
        """
        获取当前字幕数据的条目数量。
        
        Returns:
            int: 字幕数据中的条目数量。
        """
        return len(self.subtitle_data)
        
    def get_item(self, index: int) -> Optional[Dict[str, Any]]:
        """
        根据索引获取单个字幕条目。
        
        Args:
            index (int): 要获取的条目的索引。
            
        Returns:
            Optional[Dict[str, Any]]: 对应索引的字幕条目，如果索引无效则返回 None。
        """
        if 0 <= index < len(self.subtitle_data):
            return self.subtitle_data[index]
        return None
        
    def delete_row(self, index: int) -> bool:
        """
        删除指定索引的字幕行。
        
        Args:
            index (int): 要删除的行的索引。
            
        Returns:
            bool: 如果删除成功则返回 True，否则返回 False。
        """
        if 0 <= index < len(self.subtitle_data):
            del self.subtitle_data[index]
            return True
        return False
        
    def insert_row(self, index: int, data: Optional[Dict[str, Any]] = None) -> bool:
        """
        在指定索引处插入一行新的字幕数据。
        如果未提供数据，则插入一个默认的空行。
        
        Args:
            index (int): 插入行的索引。
            data (Optional[Dict[str, Any]]): 要插入的数据。默认为 None，将插入空数据。
            
        Returns:
            bool: 如果插入成功则返回 True，否则返回 False。
        """
        if data is None:
            data = {
                'source': {'text': ''},
                'target': {'text': ''},
                'lqa_result': None
            }
        
        if 0 <= index <= len(self.subtitle_data):
            self.subtitle_data.insert(index, data)
            return True
        return False
        
    def merge_rows(self, index: int, direction: str) -> tuple[bool, int]:
        """
        合并当前行与相邻行。
        
        Args:
            index (int): 当前行的索引。
            direction (str): 合并方向，'up' 表示与上一行合并，'down' 表示与下一行合并。
            
        Returns:
            tuple[bool, int]: 一个元组，表示合并是否成功 (bool) 和合并后保留行的索引 (int)。
                              如果合并失败，索引为 -1。
        """
        if index < 0 or index >= len(self.subtitle_data):
            return False, -1
            
        if direction == 'up':
            if index == 0: return False, -1
            target_index = index - 1
            main_index = index # The one merging into target
            keep_index = target_index
            
            # Merge current into target (above)
            # Text order: target + current
            item_top = self.subtitle_data[target_index]
            item_bottom = self.subtitle_data[index]
            
        else: # down
            if index >= len(self.subtitle_data) - 1: return False, -1
            target_index = index + 1
            main_index = index
            keep_index = index # We generally keep the current index if merging down effectively means "pulling next up" or "pushing current down"
            # Actually, usually "Merge Down" means current + next, become one row at current index.
            
            item_top = self.subtitle_data[index]
            item_bottom = self.subtitle_data[target_index]
            
        # Extract text
        src_top = self._get_text(item_top.get('source'))
        tgt_top = self._get_text(item_top.get('target'))
        src_bottom = self._get_text(item_bottom.get('source'))
        tgt_bottom = self._get_text(item_bottom.get('target'))
        
        merged_src = f"{src_top}\n{src_bottom}"
        merged_tgt = f"{tgt_top}\n{tgt_bottom}"
        
        # We merge into the 'top' item usually, or specific logic.
        # Let's preserve the Logic from MainWindow:
        # If 'up': merge into (row-1), delete row.
        # If 'down': merge into (row), delete row+1. 
        # Wait, MainWindow logic for 'down' was: merged into target_row (row+1)? No?
        # Let's check MainWindow logic carefully.
        
        # Re-implementing simplified logic that makes sense:
        # Merge Up: Top + Bottom -> Top. Delete Bottom.
        # Merge Down: Top + Bottom -> Top. Delete Bottom. 
        # (Difference is which row is 'selected' initially)
        
        # Actually logic in MainWindow was:
        # if up: merge_to = row-1, remove = row. src = target(top) + current(bottom)
        # if down: merge_to = row, remove = row+1. src = current(top) + target(bottom)
        
        if direction == 'up':
            merge_to = target_index
            remove_at = index
        else: # down
            merge_to = index
            remove_at = target_index
            
        # Apply merge
        self._update_text(merge_to, 'source', merged_src)
        self._update_text(merge_to, 'target', merged_tgt)
        
        # Delete the other
        del self.subtitle_data[remove_at]
        
        return True, merge_to

    def get_lqa_pairs(self):
        """准备LQA分析所需的数据对"""
        pairs = []
        for item in self.subtitle_data:
            src = item.get('source', {})
            tgt = item.get('target', {})
            src_text = src.get('text', '') if isinstance(src, dict) else str(src)
            tgt_text = tgt.get('text', '') if isinstance(tgt, dict) else str(tgt)
            pairs.append((src_text, tgt_text))
        return pairs

    def update_text(self, index, type_, text):
        """更新文本"""
        if 0 <= index < len(self.subtitle_data):
            self._update_text(index, type_, text)
            return True
        return False

    def _get_text(self, obj):
        if isinstance(obj, dict):
            return obj.get('text', '')
        return str(obj) if obj else ''
        
    def _update_text(self, index, type_, text):
        item = self.subtitle_data[index]
        if isinstance(item[type_], dict):
            item[type_]['text'] = text
        else:
            item[type_] = {'text': text}

    def save_project(self, filepath):
        """保存项目到文件 (.kcp)"""
        data = {
            'version': '1.0',
            'source_file': self.source_file,
            'target_file': self.target_file,
            'video_file': self.video_file,
            'anchor_mode': self.anchor_mode,
            'global_context': self.global_context,
            'subtitle_data': self.subtitle_data
        }
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save project: {e}")
            return False

    def load_project(self, filepath):
        """从文件加载项目 (.kcp)"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.source_file = data.get('source_file')
            self.target_file = data.get('target_file')
            self.video_file = data.get('video_file')
            self.anchor_mode = data.get('anchor_mode', 'source')
            self.global_context = data.get('global_context', "")
            self.subtitle_data = data.get('subtitle_data', [])
            
            return True
        except Exception as e:
            logger.error(f"Failed to load project: {e}")
            return False
