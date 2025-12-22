import logging
import json
import os
from typing import List, Dict, Any, Callable
from PyQt6.QtCore import QThread, pyqtSignal

# 参考 LQA 的全局导入
from core.services.lqa_processor import load_prompt_template, format_prompt
from core.utils.llm_utils import parse_json_from_response

logger = logging.getLogger(__name__)

class TranslationWorker(QThread):
    """
    异步翻译 Worker
    """
    progress = pyqtSignal(str, int) # msg, percent
    finished = pyqtSignal(bool, list) # success, results

    def __init__(self, store, client, target_lang, mode="bilingual", batch_size=12):
        super().__init__()
        self.store = store
        self.client = client
        self.target_lang = target_lang
        self.mode = mode # "bilingual" or "replace"
        self.batch_size = batch_size
        self._is_cancelled = False

    def _strip_tags(self, text):
        """正则剥离行首标签块，返回 (tags, clean_text)"""
        import re
        # 匹配所有开头的 {...} 块
        match = re.match(r"^((?:\{.*?\})*)(.*)$", text, re.DOTALL)
        if match:
            return match.group(1), match.group(2)
        return "", text

    def run(self):
        try:
            events = self.store.subs.events
            if not events:
                self.finished.emit(True, [])
                return

            # 1. 预处理：物理剥离所有标签，防止 LLM 弄丢 {\an8} 等
            preprocessed = [] # list of (tag_block, clean_text)
            for e in events:
                preprocessed.append(self._strip_tags(e.text))

            # A. 加载 Prompt 模板 (统筹管理)
            prompt_tmpl = load_prompt_template(".translate_en.txt")
            if not prompt_tmpl:
                # 兜底
                prompt_tmpl = "Translate the following JSON list to {target_lang}."

            translated_results = []
            chunk_size = self.batch_size
            total = len(events)
            
            for i in range(0, total, chunk_size):
                if self._is_cancelled: break
                
                # 当前批次的纯文本
                chunk_data = preprocessed[i : i + chunk_size]
                chunk_pure_texts = [item[1] for item in chunk_data]
                
                # 准备上下文 (使用纯文本前 3 句)
                context = ""
                if i > 0:
                    prev_items = preprocessed[max(0, i-3) : i]
                    context = "\n".join([f"- {item[1]}" for item in prev_items])
                
                # B. 生成 System Prompt (包含指令和上下文变量)
                system_prompt = format_prompt(
                    prompt_tmpl,
                    context=context,
                    target_language=self.target_lang
                )
                
                # C. 生成 User Prompt (纯数据)
                user_prompt = json.dumps(chunk_pure_texts, ensure_ascii=False)
                
                self.progress.emit(f"正在翻译 第 {i+1}-{min(i+chunk_size, total)} 条...", int(i * 100 / total))
                
                try:
                    # D. 调用 API (System/User 隔离模式)
                    response = self.client.generate_content(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        json_mode=True
                    )
                    
                    # E. 鲁棒解析
                    data = parse_json_from_response(response['text'])
                    if data and isinstance(data, dict):
                        api_texts = data.get("translated", [])
                    elif isinstance(data, list):
                        api_texts = data
                    else:
                        api_texts = []
                    
                    # 数量校准
                    if len(api_texts) != len(chunk_data):
                        logger.warning(f"Batch {i}: Expect {len(chunk_data)}, Got {len(api_texts)}. Using original as fallback.")
                        api_texts = (api_texts + chunk_pure_texts)[:len(chunk_data)]
                    
                    # 物理回填：将翻译结果与原标签块焊接
                    for idx, trans_txt in enumerate(api_texts):
                        orig_tag = chunk_data[idx][0]
                        translated_results.append(orig_tag + trans_txt)
                    
                except Exception as e:
                    logger.error(f"翻译批次失败: {e}")
                    # 容错：使用原文 (带标签)
                    for idx in range(len(chunk_data)):
                        translated_results.append(chunk_data[idx][0] + chunk_data[idx][1])
            
            if self._is_cancelled:
                return

            self.progress.emit("翻译完成，正在同步轨道...", 100)
            self.finished.emit(True, translated_results)

        except Exception as e:
            logger.error(f"Translation Worker Error: {e}")
            self.finished.emit(False, [str(e)])

class TranslationService:
    """
    SubStudio 翻译逻辑封装
    """
    @staticmethod
    def apply_translation(store, results, mode="bilingual"):
        """
        将翻译结果应用回 Store (多轨导入模式)
        """
        if len(results) != len(store.subs.events):
            logger.error("翻译结果数量与原字幕不符")
            return
            
        # 1. 确保“译文”分组存在 (继承默认样式，深蓝色)
        track_name = "译文"
        if track_name not in store.groups:
            store.add_group(track_name, style="Default", color="#1e3a8a")
            
        from pysubs2 import SSAEvent
        
        # 2. 根据模式处理
        if mode == "bilingual":
            # 模式 A: 修改原字幕为双语 (不增新行)
            for i, trans_text in enumerate(results):
                orig_event = store.subs.events[i]
                # 提取标签
                import re
                tags = "".join(re.findall(r"^((?:\{.*?\})*)", orig_event.text))
                clean_orig = re.sub(r"^((?:\{.*?\})*)", "", orig_event.text)
                
                # 这种模式下结果通常已经是带标签的（worker回填了）
                # results[i] 已经是 tag + translated_text
                # 我们拼回 \N + clean_orig
                new_text = f"{results[i]}\\N{clean_orig}"
                store.update_event(i, text=new_text)
        else:
            # 模式 B: 作为新的轨道导入 (克隆新行)
            # 用户要求: 作为新的轨道导入进时间轴，同时隐藏原文
            new_events = []
            for i, trans_text in enumerate(results):
                orig_event = store.subs.events[i]
                # 克隆一份
                new_ev = SSAEvent(start=orig_event.start, end=orig_event.end, 
                                  text=results[i], style=orig_event.style)
                new_ev.name = track_name # 分组/轨道名
                new_ev.effect = "1"      # 时间轴纵向偏移 (第 2 轨)
                new_events.append(new_ev)
            
            # 追加到 store
            store.subs.events.extend(new_events)
            
            # 3. 自动隐藏原文轨道 (假设原文在 Default 分组)
            # 获取所有已存在分组，如果没有显式分组，通常是 Default 或空
            # 我们先找出所有译文之外的分组并隐藏它们 (保护性操作)
            for gname in store.groups:
                if gname != track_name:
                    store.set_group_visibility(gname, False)
            
            # 确保译文轨道是可见的
            store.set_group_visibility(track_name, True)
            
        store._mark_dirty()
        store.dataChanged.emit()
