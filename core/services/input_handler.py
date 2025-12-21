"""
输入文件编排器
负责分析输入文件类型，并结合当前应用状态给出处理决策。
"""

import os
import logging
from enum import Enum, auto
from typing import Dict, Any, Optional, List
from core.parsers.bilingual_parser import detect_bilingual_format, detect_language

logger = logging.getLogger(__name__)

class InputType(Enum):
    VIDEO = auto()
    BILINGUAL = auto()
    MONOLINGUAL = auto()
    UNKNOWN = auto()

class SuggestedAction(Enum):
    LOAD_VIDEO = auto()             # 直接加载视频
    VIDEO_CONFLICT = auto()         # 视频冲突（询问替换或新窗口）
    
    LOAD_BILINGUAL = auto()         # 直接加载双语
    BILINGUAL_CONFLICT = auto()     # 双语冲突（询问新窗口、替换或取消）
    
    ASK_TYPE = auto()               # 询问是原文还是译文
    SUGGEST_TARGET = auto()         # 建议作为译文（已有原文）
    SUGGEST_SOURCE = auto()         # 建议作为原文（已有译文）
    FULL_CONFLICT = auto()          # 全量冲突（已有原文和译文）

class InputOrchestrator:
    """
    负责判定输入文件的处理逻辑。
    不包含任何 UI 弹窗代码，只负责提供“决策建议”。
    """

    def decide_action(self, 
                      file_path: str, 
                      has_video: bool,
                      has_subtitle_data: bool,
                      has_source_file: bool = False,
                      has_target_file: bool = False) -> Dict[str, Any]:
        """
        根据输入文件和当前状态决定建议操作。
        
        Args:
            file_path: 输入文件路径
            has_video: 当前是否已加载视频
            has_subtitle_data: 当前是否已有字幕数据
            has_source_file: 当前是否已加载原文路径
            has_target_file: 当前是否已加载译文路径
            
        Returns:
            Dict 包含 'action', 'type', 'format_hint' 等信息
        """
        file_path = os.path.normpath(file_path)
        ext = file_path.lower().split('.')[-1]
        
        # 1. 识别基础类型
        input_type = self._detect_input_type(file_path, ext)
        
        # 2. 根据类型和状态进行决策
        if input_type == InputType.VIDEO:
            return self._decide_video_action(has_video)
            
        if input_type == InputType.BILINGUAL:
            format_hint = detect_bilingual_format(file_path)
            return self._decide_bilingual_action(has_subtitle_data, has_source_file, has_target_file, format_hint)
            
        # 3. 单语字幕或文本：增加内容语言检测
        detected_lang = self._detect_content_language(file_path)
        return self._decide_monolingual_action(has_subtitle_data, has_source_file, has_target_file, detected_lang)

    def _detect_content_language(self, file_path: str) -> str:
        """采样检测文件内容的语言"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 采样前 20 行非空文本
                sample = []
                for _ in range(100): # 最多读100行找20行非空
                    line = f.readline()
                    if not line: break
                    if line.strip():
                        sample.append(line.strip())
                        if len(sample) >= 20: break
                
                if not sample: return 'unknown'
                
                # 合并样本进行判定
                return detect_language("\n".join(sample))
        except:
            return 'unknown'

    def _detect_input_type(self, file_path: str, ext: str) -> InputType:
        """判定文件类型"""
        if ext in ['mp4', 'mkv', 'avi', 'mov', 'wmv']:
            return InputType.VIDEO
            
        if ext in ['srt', 'ass', 'ssa', 'vtt']:
            # 标准字幕通常不视为双语文件（除非内部逻辑强制）
            return InputType.MONOLINGUAL
            
        # 检查是否为双语文本
        if detect_bilingual_format(file_path) != 'unknown':
            return InputType.BILINGUAL
            
        return InputType.MONOLINGUAL

    def _decide_video_action(self, has_video: bool) -> Dict[str, Any]:
        if has_video:
            return {'action': SuggestedAction.VIDEO_CONFLICT, 'type': InputType.VIDEO}
        return {'action': SuggestedAction.LOAD_VIDEO, 'type': InputType.VIDEO}

    def _decide_bilingual_action(self, has_data: bool, has_src: bool, has_tgt: bool, format_hint: str) -> Dict[str, Any]:
        if has_data or has_src or has_tgt:
            return {
                'action': SuggestedAction.BILINGUAL_CONFLICT, 
                'type': InputType.BILINGUAL,
                'format_hint': format_hint
            }
        return {
            'action': SuggestedAction.LOAD_BILINGUAL, 
            'type': InputType.BILINGUAL,
            'format_hint': format_hint
        }

    def _decide_monolingual_action(self, has_data: bool, has_src: bool, has_tgt: bool, detected_lang: str) -> Dict[str, Any]:
        """根据检测到的语言，给出更聪明的建议"""
        
        # 如果当前全空且无数据，根据语言直接建议
        if not has_src and not has_tgt and not has_data:
            if detected_lang in ['en', 'ja', 'fr', 'de', 'ru', 'ko']:
                return {'action': SuggestedAction.ASK_TYPE, 'type': InputType.MONOLINGUAL, 'suggested': 'source', 'detected': detected_lang}
            elif detected_lang == 'zh':
                return {'action': SuggestedAction.ASK_TYPE, 'type': InputType.MONOLINGUAL, 'suggested': 'target', 'detected': detected_lang}
            return {'action': SuggestedAction.ASK_TYPE, 'type': InputType.MONOLINGUAL}
            
        # 如果只有原文，推断为译文
        if has_src and not has_tgt:
            return {'action': SuggestedAction.SUGGEST_TARGET, 'type': InputType.MONOLINGUAL, 'detected': detected_lang}
            
        # 如果只有译文，推断为原文
        if not has_src and has_tgt:
            return {'action': SuggestedAction.SUGGEST_SOURCE, 'type': InputType.MONOLINGUAL, 'detected': detected_lang}
            
        # 其余情况（包括已有双语数据且 src/tgt 为空的情况）均视为全量冲突
        return {'action': SuggestedAction.FULL_CONFLICT, 'type': InputType.MONOLINGUAL, 'detected': detected_lang}
