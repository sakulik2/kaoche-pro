"""
LQA Worker - 异步LQA分析线程

在后台执行LQA分析，避免阻塞UI
"""

from PyQt6.QtCore import QThread, pyqtSignal
from typing import List, Tuple, Dict, Any
import logging
import threading
import json

logger = logging.getLogger(__name__)


class LQAWorker(QThread):
    """
    异步LQA分析Worker
    
    信号:
        progress: (current, total) - 进度更新
        result_ready: (row_index, lqa_result) - 单行结果就绪
        batch_complete: (results) - 批次完成
        error_occurred: (row_index, error_msg) - 错误发生
        finished: () - 全部完成
    """
    
    # 信号定义
    progress = pyqtSignal(int, int)  # (current, total)
    result_ready = pyqtSignal(int, dict)  # (row_index, lqa_result)
    batch_complete = pyqtSignal(int, int)  # (batch_start, batch_end)
    error_occurred = pyqtSignal(int, str)  # (row_index, error_msg)
    finished = pyqtSignal()
    
    def __init__(self, 
                 subtitle_pairs: List[Tuple[str, str]], 
                 api_client,
                 prompt_template: str,
                 context: str = "",
                 target_language: str = "zh_CN",
                 source_language: str = "auto",
                 batch_size: int = 10):
        """
        初始化LQA Worker
        
        Args:
            subtitle_pairs: [(source, target), ...] 字幕对列表
            api_client: APIClient实例
            prompt_template: Prompt模板内容
            context: 用户提供的上下文/辩解
            target_language: 目标语言代码
            source_language: 原文语言代码
            batch_size: 批处理大小
        """
        super().__init__()
        self.subtitle_pairs = subtitle_pairs
        self.api_client = api_client
        self.prompt_template = prompt_template
        self.context = context
        self.target_language = target_language
        self.source_language = source_language
        self.batch_size = batch_size
        
        self._stop_flag = False # Added stop flag
        self._is_paused = False
        self._pause_lock = threading.Lock() # Added pause lock
        
    def run(self):
        """执行LQA分析"""
        try:
            total = len(self.subtitle_pairs)
            
            # 分批处理
            for batch_start in range(0, total, self.batch_size):
                if self._stop_flag:
                    break
                
                # 暂停检查
                self._pause_lock.acquire()
                self._pause_lock.release()
                
                batch_end = min(batch_start + self.batch_size, total)
                batch = self.subtitle_pairs[batch_start:batch_end]
                
                # 处理当前批次
                for i, (source, target) in enumerate(batch):
                    if self._stop_flag:
                        break
                    
                    actual_index = batch_start + i
                    
                    try:
                        # 构建prompt
                        # 使用 lqa_processor 的逻辑或直接 format
                        # 为了支持 target_language，这里需要确保模板里有 {target_language} 占位符
                        # 或者使用 lqa_processor.format_prompt
                        from core.services.lqa_processor import format_prompt
                        
                        prompt = format_prompt(
                            self.prompt_template, 
                            context=self.context,
                            target_language=self.target_language,
                            source_language=self.source_language
                        )
                        
                        # format_prompt 只替换了 system/context 部分，具体的 source/target 还需要替换吗？
                        # 不，lqa_processor.process_lqa_batch 是把 pairs 作为 JSON 发送给 user_prompt。
                        # 但这里的 run 方法似乎是 单行处理 (batch loop inside, but wait...)
                        # Line 95 calls generate_content with user_prompt=prompt.
                        # Wait, line 88 was: prompt = self.prompt_template.format(context=..., source=source, target=target)
                        # This implies the prompt template HAS {source} and {target} placeholders?
                        # If so, it's a "Single Pair Prompt".
                        # But process_lqa_batch uses valid JSON-based batch prompts.
                        # I should stick to the existing pattern but add target_language.
                        
                        # 假设模板支持 {target_language}
                        # 为了安全起见，先替换 standard placeholders
                        # prompt = self.prompt_template.replace("{context}", self.context)
                        # prompt = prompt.replace("{target_language}", self.target_language)
                        # prompt = prompt.replace("{source_language}", self.source_language)
                        prompt = prompt.replace("{source}", source)
                        prompt = prompt.replace("{target}", target)
                        
                        # 调用API
                        response = self.api_client.generate_content(
                            system_prompt="你是一个专业的翻译质量评估专家",
                            user_prompt=prompt,
                            json_mode=True
                        )
                        
                        # 解析结果
                        lqa_result = self._parse_response(response)
                        
                        # 发送结果
                        self.result_ready.emit(actual_index, lqa_result)
                        
                    except Exception as e:
                        logger.error(f"LQA分析失败 (行{actual_index+1}): {e}")
                        self.error_occurred.emit(actual_index, f"LQA分析失败: {str(e)}")
                    
                    # 更新进度
                    self.progress.emit(actual_index + 1, total)
                
                # 批次完成
                self.batch_complete.emit(batch_start, batch_end)
                
        except Exception as e:
            logger.error(f"LQA Worker运行失败: {e}", exc_info=True)
        
        finally:
            self.finished.emit()
    
    def _parse_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析API响应
        
        Args:
            response: API响应字典
            
        Returns:
            LQA结果字典
        """
        try:
            # response可能是字典或字符串
            if isinstance(response, dict):
                text = response.get('text', '')
            elif isinstance(response, str):
                text = response
            else:
                logger.error(f"未知的响应类型: {type(response)}")
                text = str(response)
            
            logger.debug(f"LQA响应文本 (前200字符): {text[:200]}")
            
            # 尝试解析JSON
            result = json.loads(text)
            
            # 如果返回的是数组（批量分析），取第一个
            if isinstance(result, list):
                if len(result) > 0:
                    result = result[0]  # 取第一个结果
                else:
                    # 空数组，返回默认值
                    return {
                        'score': 5,
                        'issues': [],
                        'suggestions': '',
                        'comment': ''
                    }
            
            # 确保必要字段存在
            if 'score' not in result:
                result['score'] = 5
            if 'issues' not in result:
                result['issues'] = []
            if 'suggestions' not in result and 'suggestion' in result:
                result['suggestions'] = result['suggestion']  # 兼容不同字段名
            if 'suggestions' not in result:
                result['suggestions'] = ''
            if 'comment' not in result:
                result['comment'] = ''
            
            return result
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            logger.error(f"原始响应: {text[:500] if 'text' in locals() else response}")
            return {
                'score': 0,
                'issues': ['JSON解析失败'],
                'suggestions': '',
                'comment': '',
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"解析LQA响应失败: {e}")
            logger.error(f"响应类型: {type(response)}, 内容: {str(response)[:500]}")
            return {
                'score': 0,
                'issues': ['解析失败'],
                'suggestions': '',
                'comment': '',
                'error': str(e)
            }
    
    def _analyze_single_pair(self, source: str, target: str) -> Dict[str, Any]:
        """
        分析单个字幕对
        
        Args:
            source: 原文
            target: 译文
            
        Returns:
            LQA结果字典
        """
        from core.services.lqa_processor import process_lqa_batch
        
        # 构建输入
        batch = [(source, target)]
        
        # 调用LQA处理器
        results = process_lqa_batch(
            batch,
            self.api_client,
            self.prompt_template,
            self.context,
            target_language=self.target_language,
            source_language=self.source_language
        )
        
        return results[0] if results else {
            'score': 0,
            'issues': ['分析失败'],
            'suggestions': '',
            'error': True
        }
    
    def pause(self):
        """暂停处理"""
        self._is_paused = True
        logger.info("LQA Worker已暂停")
    
    def resume(self):
        """恢复处理"""
        self._is_paused = False
        logger.info("LQA Worker已恢复")
    
    def stop(self):
        """停止处理"""
        self._is_running = False
        self._is_paused = False
        logger.info("LQA Worker已停止")


class GlobalLQAWorker(QThread):
    """
    异步全局 LQA 深度分析 Worker
    """
    finished = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, 
                 all_pairs: List[Dict[str, Any]], 
                 api_client,
                 prompt_template: str,
                 context: str = "",
                 target_language: str = "zh_CN",
                 source_language: str = "auto"):
        super().__init__()
        self.all_pairs = all_pairs
        self.api_client = api_client
        self.prompt_template = prompt_template
        self.context = context
        self.target_language = target_language
        self.source_language = source_language
        
    def run(self):
        try:
            from core.services.lqa_processor import process_global_lqa
            
            result = process_global_lqa(
                self.api_client,
                self.all_pairs,
                self.prompt_template,
                self.context,
                self.target_language,
                self.source_language
            )
            
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"Global LQA Worker 运行失败: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
