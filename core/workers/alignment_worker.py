"""
Alignment Worker - 异步字幕对齐线程

在后台执行字幕对齐，支持时间轴对齐和LLM填补
"""

from PyQt6.QtCore import QThread, pyqtSignal
from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class AlignmentWorker(QThread):
    """
    异步字幕对齐Worker
    
    信号:
        progress: (status_message) - 状态更新
        alignment_complete: (aligned_pairs) - 对齐完成
        llm_fill_started: () - LLM填补开始
        llm_fill_progress: (current, total) - LLM填补进度
        error_occurred: (error_msg) - 错误发生
        finished: () - 完成
    """
    
    # 信号定义
    progress = pyqtSignal(str)  # 状态消息
    alignment_complete = pyqtSignal(list)  # 对齐结果
    llm_fill_started = pyqtSignal()
    llm_fill_progress = pyqtSignal(int, int)  # (current_retry, max_retries)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()
    
    def __init__(self,
                 source_data: List[Dict],
                 target_data: List[Dict],
                 anchor_mode: str = 'source',
                 auto_fill: bool = True,
                 api_client=None,
                 batch_size: int = 10):
        """
        初始化对齐Worker
        
        Args:
            source_data: 原文字幕数据 (含start, end, text)
            target_data: 译文字幕数据
            anchor_mode: 对齐模式 ('source' 或 'target')
            auto_fill: 是否自动LLM填补空缺
            api_client: API客户端（填补空缺时使用）
        """
        super().__init__()
        self.source_data = source_data
        self.target_data = target_data
        self.anchor_mode = anchor_mode
        self.auto_fill = auto_fill
        self.api_client = api_client
        self.batch_size = batch_size
        
        self._is_running = True
    
    def run(self):
        """执行对齐"""
        try:
            # 步骤1: 时间轴对齐
            self.progress.emit(f"开始{self.anchor_mode}模式对齐...")
            
            from core.services.alignment import align_subtitles
            
            aligned = align_subtitles(
                self.source_data,
                self.target_data,
                anchor_mode=self.anchor_mode
            )
            
            self.progress.emit(f"时间轴对齐完成: {len(aligned)} 对")
            
            # 步骤2: 检查空缺
            if self.auto_fill and self.api_client:
                empty_count = sum(1 for src, tgt in aligned if not src or not tgt)
                
                if empty_count > 0:
                    self.progress.emit(f"检测到 {empty_count} 个空缺")
                    self.llm_fill_started.emit()
                    
                    # LLM填补
                    aligned = self._fill_gaps_with_llm(aligned)
                else:
                    self.progress.emit("无空缺，跳过LLM填补")
            
            # 完成
            if self._is_running:
                self.alignment_complete.emit(aligned)
                self.progress.emit(f"对齐完成: {len(aligned)} 对")
            
        except Exception as e:
            error_msg = f"对齐失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.error_occurred.emit(error_msg)
        
        finally:
            self.finished.emit()
    
    def _fill_gaps_with_llm(self, aligned: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """
        使用LLM填补空缺
        
        Args:
            aligned: 初始对齐结果
            
        Returns:
            填补后的对齐结果
        """
        try:
            from core.services.alignment import fill_alignment_gaps
            
            # 自定义进度回调
            max_retries = 3
            for retry in range(max_retries):
                if not self._is_running:
                    break
                
                self.llm_fill_progress.emit(retry + 1, max_retries)
                self.progress.emit(f"LLM填补尝试 {retry + 1}/{max_retries}...")
            
            result = fill_alignment_gaps(
                aligned,
                self.source_data,
                self.target_data,
                self.api_client,
                auto_fill=True,
                max_retries=max_retries,
                batch_size=self.batch_size
            )
            
            # 统计填补结果
            before_empty = sum(1 for src, tgt in aligned if not src or not tgt)
            after_empty = sum(1 for src, tgt in result if not src or not tgt)
            filled = before_empty - after_empty
            
            self.progress.emit(f"LLM填补完成: 填补了 {filled} 个空缺")
            
            return result
            
        except Exception as e:
            logger.error(f"LLM填补失败: {e}")
            self.progress.emit(f"LLM填补失败: {str(e)}")
            return aligned
    
    def stop(self):
        """停止处理"""
        self._is_running = False
        logger.info("Alignment Worker已停止")
