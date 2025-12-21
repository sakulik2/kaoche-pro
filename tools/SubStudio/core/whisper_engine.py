import os
import logging
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer
import time

logger = logging.getLogger(__name__)

class TranscriptionWorker(QThread):
    progress = pyqtSignal(str) # 进度文本
    progress_percent = pyqtSignal(int) # 0-100
    finished = pyqtSignal(bool, object) # success, result (list of dict or error str)

    def __init__(self, model_path, audio_path, device="cuda", compute_type="float16", align=True, language=None, initial_prompt=None):
        super().__init__()
        self.model_path = model_path
        self.audio_path = audio_path
        self.device = device
        self.compute_type = compute_type
        self.align = align
        self.language = language
        self.initial_prompt = initial_prompt
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            # 环境变量重定向：将 torch/torchaudio 的缓存目录设为项目本地，避免下载到 C 盘
            # 模型路径通常为 tools/SubStudio/models/hub
            models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
            torch_home = os.path.join(models_dir, "hub")
            os.makedirs(torch_home, exist_ok=True)
            os.environ["TORCH_HOME"] = torch_home
            logger.info(f"Setting TORCH_HOME to {torch_home}")
            
            import torch
            from faster_whisper import WhisperModel
            
            self.progress.emit("正在加载模型 (Loading Model)...")
            self.progress_percent.emit(5)
            
            # 1. 加载模型
            # 自动降级处理：如果 cuda 不可用，强制 cpu
            if self.device == "cuda" and not torch.cuda.is_available():
                self.progress.emit("CUDA 不可用，切换到 CPU...")
                self.device = "cpu"
                self.compute_type = "int8" # CPU 推荐 int8
            
            try:
                model = WhisperModel(self.model_path, device=self.device, compute_type=self.compute_type)
            except Exception as e:
                # 某些旧显卡不支持 float16
                if "float16" in self.compute_type:
                    self.progress.emit("float16 加载失败，尝试 int8...")
                    model = WhisperModel(self.model_path, device=self.device, compute_type="int8")
                else:
                    raise e

            self.progress_percent.emit(20)
            
            if self._is_cancelled: return

            # 2. [CRITICAL PATCH] 修复 large-v3-turbo 维度问题 (Runtime Patch)
            # 检查 mel_filters 第一维是否为 80 (旧版默认)，如果是且模型需要 128，则进行热修复
            # 注意：这里我们假设 turbo 模型总是需要 128 mels。更严谨的做法是 try-catch 第一次推理错误？
            # 简单起见，照搬 POC 的检测逻辑
            try:
                current_filters = model.feature_extractor.mel_filters
                # 通常 turbo 模型如果被错误加载，这里可能只有 80
                # 但我们需要知道模型本身是否期望 128。
                # faster-whisper 1.0+ 对 v3 支持较好，但对于 ctranslate2 转换版可能仍需手动干预
                # 我们的策略：如果路径包含 turbo 且 filters 是 80，或者仅仅尝试修正
                
                # 简易启发式：如果文件名包含 turbo 或者 large-v3
                is_v3_derived = "turbo" in self.model_path.lower() or "large-v3" in self.model_path.lower()
                
                if is_v3_derived and current_filters.shape[0] == 80:
                    self.progress.emit("应用模型热修复 (Applying Runtime Patch)...")
                    new_filters = model.feature_extractor.get_mel_filters(
                        model.feature_extractor.sampling_rate, 
                        model.feature_extractor.n_fft, 
                        n_mels=128
                    )
                    # 必须转换为 float32，否则 CTranslate2 会报错 Unsupported type: <f8
                    new_filters = new_filters.astype(np.float32)
                    model.feature_extractor.mel_filters = new_filters
                    logger.info("Applied mel-filter patch: 80 -> 128")
            except Exception as patch_e:
                logger.warning(f"Patch failed (non-fatal?): {patch_e}")
            
            self.progress_percent.emit(30)
            
            # 3. 开始转写
            start_msg = f"正在转写 (Transcribing)... 设备: {self.device}"
            self.progress.emit(start_msg)
            print(f"[WhisperEngine] {start_msg}")
            logger.info(start_msg)
            
            # beam_size=5 是常用配置
            # 强化标点符号输出：如果用户没提供 prompt，使用默认的标点诱导提示
            prompt = self.initial_prompt
            if not prompt:
                if self.language == "zh":
                    prompt = "。，！？；"
                elif self.language == "en":
                    prompt = ".,!?; "
                else:
                    # 自动检测模式或多语言混合模式：使用通用混合标点提示
                    prompt = "。，！？；.,!?; "
            
            self.progress.emit(f"正在转写 (Transcribing)... 模式: {'自动检测' if not self.language else self.language}")
            segments_gen, info = model.transcribe(
                self.audio_path, 
                beam_size=5, 
                language=self.language,
                initial_prompt=prompt
            ) 
            
            segments = []
            total_duration = info.duration
            print(f"[WhisperEngine] Audio Duration: {total_duration:.2f}s")
            
            for seg in segments_gen:
                if self._is_cancelled: 
                    print("[WhisperEngine] Task Cancelled.")
                    return
                
                segments.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text
                })
                
                # Terminal & Log Output
                log_msg = f"[{seg.start:.2f}s -> {seg.end:.2f}s] {seg.text.strip()}"
                print(log_msg)
                logger.info(log_msg)
                
                # 更新进度 30% -> 90%
                if total_duration > 0:
                    percent = 30 + int((seg.end / total_duration) * 60)
                    percent = min(90, percent)
                    self.progress_percent.emit(percent)
                    self.progress.emit(f"转写中: {seg.end:.1f}s / {total_duration:.1f}s")
            
            self.progress_percent.emit(90)
            
            # 4. 精准对齐 (WhisperX Alignment)
            if self.align and not self._is_cancelled:
                try:
                    import whisperx
                    self.progress.emit("正在进行音频对齐 (Aligning)...")
                    logger.info("Starting WhisperX alignment...")
                    
                    # 加载对齐模型
                    # 针对中文通常使用 WAV2VEC2_ASR_700_CHINESE，英文为默认
                    lang_code = info.language
                    model_a, metadata = whisperx.load_align_model(
                        language_code=lang_code, 
                        device=self.device
                    )
                    
                    # 执行对齐
                    result_aligned = whisperx.align(
                        segments, 
                        model_a, 
                        metadata, 
                        self.audio_path, 
                        self.device, 
                        return_char_alignments=True
                    )
                    
                    # 释放对齐模型显存
                    import gc
                    del model_a
                    if self.device == "cuda": torch.cuda.empty_cache()
                    gc.collect()
                    
                    # 提取对齐后的段落
                    if "segments" in result_aligned:
                        aligned_segments = []
                        for seg in result_aligned["segments"]:
                            # 保留 words 和 chars 以供 SRTProcessor 进行精确重切分
                            item = {
                                "start": seg.get("start", 0),
                                "end": seg.get("end", 0),
                                "text": seg.get("text", "")
                            }
                            if "words" in seg: item["words"] = seg["words"]
                            if "chars" in seg: item["chars"] = seg["chars"]
                            aligned_segments.append(item)
                            
                        segments = aligned_segments
                        logger.info(f"Alignment successful. Managed {len(segments)} segments.")
                    
                except ImportError:
                    logger.warning("whisperx not installed, skipping alignment.")
                except Exception as ae:
                    logger.error(f"Alignment failed: {ae}")
                    self.progress.emit(f"对齐失败 (跳过): {ae}")
            
            # 5. SRT/ASS 后处理 (Post-Processing)
            if not self._is_cancelled:
                from .srt_processor import SRTProcessor
                self.progress.emit("正在优化字幕格式 (Finishing)...")
                processed_segments = SRTProcessor.process_segments(
                    segments, 
                    lang=info.language
                )
                segments = processed_segments

            self.progress_percent.emit(95)
            self.progress.emit("处理完成 (Finalizing)...")
            print(f"[WhisperEngine] Processed segments: {len(segments)}")
            logger.info(f"Transcription and Post-processing Completed. Total: {len(segments)}")
            
            self.finished.emit(True, segments)
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.finished.emit(False, str(e))

class WhisperEngine(QObject):
    """
    SubStudio 核心推理引擎
    包装 Worker，处理任务队列与状态
    """
    task_started = pyqtSignal()
    task_progress = pyqtSignal(str, int) # msg, percent
    task_finished = pyqtSignal(bool, object) # success, result
    
    def __init__(self, model_manager):
        super().__init__()
        self.manager = model_manager
        self.worker = None
        
    def is_running(self):
        return self.worker is not None and self.worker.isRunning()
        
    def start_transcription(self, audio_path, device="cuda", align=True, language=None, initial_prompt=None):
        if self.is_running():
            return False, "Task already running"
            
        model_path = self.manager.get_model_path() # 获取当前选定的模型 (Custom or Default)
        if not model_path:
            return False, "No model selected or downloaded"
            
        # 默认语言逻辑：如果您想支持 UI 传入，这里可以扩展
        self.worker = TranscriptionWorker(
            model_path, 
            audio_path, 
            device, 
            align=align, 
            language=language,
            initial_prompt=initial_prompt
        )
        self.worker.progress.connect(lambda msg: self.task_progress.emit(msg, -1)) # -1 ignore
        self.worker.progress_percent.connect(lambda p: self.task_progress.emit("", p)) # "" ignore
        self.worker.finished.connect(self._on_worker_finished)
        
        self.task_started.emit()
        self.worker.start()
        return True, "Started"

    def cancel(self):
        if self.worker:
            self.worker.cancel()
            
    def _on_worker_finished(self, success, result):
        self.task_finished.emit(success, result)
        self.worker = None
