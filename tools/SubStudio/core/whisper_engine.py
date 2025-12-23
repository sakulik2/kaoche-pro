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

    def __init__(self, model_path, audio_path, models_root, device="cuda", compute_type="float16", align=True, language=None, initial_prompt=None, vad_filter=True):
        super().__init__()
        self.model_path = model_path
        self.audio_path = audio_path
        self.models_root = models_root
        self.device = device
        self.compute_type = compute_type
        self.align = align
        self.language = language
        self.initial_prompt = initial_prompt
        self.vad_filter = vad_filter
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            # 环境变量重定向：将 torch/torchaudio 的缓存目录设为项目本地
            models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
            torch_home = os.path.join(models_dir, "hub")
            os.makedirs(torch_home, exist_ok=True)
            os.environ["TORCH_HOME"] = torch_home
            logger.info(f"Setting TORCH_HOME to {torch_home}")
            
            import torch
            
            # [CRITICAL] PyTorch 2.6+ 默认 weights_only=True 导致 pyannote/whisperx 加载失败
            # Monkeypatch torch.load to force weights_only=False globally for this thread
            _original_load = torch.load
            def _robust_load(*args, **kwargs):
                # FORCE weights_only=False to support older models/libraries (Pyannote/WhisperX)
                # potentially unsafe but necessary for these libraries until they update.
                kwargs['weights_only'] = False
                return _original_load(*args, **kwargs)
            torch.load = _robust_load
            logger.info("Applied torch.load patch (force weights_only=False)")
            
            import whisperx
            import gc
            import warnings
            
            # [Optimization] 抑制 benign 警告并启用 TF32 加速
            # 1. 忽略 Pyannote/TorchAudio 版本不匹配警告
            warnings.filterwarnings("ignore", message=".*torchaudio._backend.list_audio_backends.*")
            warnings.filterwarnings("ignore", message=".*Model was trained with.*")
            warnings.filterwarnings("ignore", message=".*Lightning automatically upgraded.*")
            
            # 2. 启用 TF32 (TensorFloat-32) 以获得在 Ampere+ GPU 上的最佳性能
            # 这也解决了 Pyannote 的 ReproducibilityWarning
            if torch.cuda.is_available():
                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True
                logger.info("Enabled TF32 for faster inference")
            
            # --- 阶段 1: 加载模型 (Loading Model) ---
            self.progress.emit("正在加载模型 (Loading Model)...")
            self.progress_percent.emit(5)
            
            # 自动降级处理
            if self.device == "cuda" and not torch.cuda.is_available():
                self.progress.emit("CUDA 不可用，切换到 CPU...")
                self.device = "cpu"
                self.compute_type = "int8"
            
            try:
                # whisperx.load_model 内部封装了 faster-whisper
                # 注意: whisperx 默认使用 vad_model，如果只想加载识别模型需要注意参数
                # 这里我们直接加载完整管线
                model = whisperx.load_model(
                    self.model_path, 
                    device=self.device, 
                    compute_type=self.compute_type,
                    language=self.language,
                    asic_iris=False # 避免可能的 mps 错误
                )
            except Exception as e:
                # 尝试 int8 降级
                if "float16" in self.compute_type:
                    self.progress.emit("float16 加载失败，尝试 int8...")
                    model = whisperx.load_model(
                        self.model_path, 
                        device=self.device, 
                        compute_type="int8",
                        language=self.language
                    )
                else:
                    raise e
            
            # [CRITICAL PATCH] 修复 large-v3-turbo 维度问题 (Runtime Patch)
            # whisperx.load_model 返回的是 FasterWhisperPipeline，其实际模型在 .model 属性中
            try:
                # 兼容性检查：确定是 pipeline 还是 direct model (POC vs Engine)
                # Engine 中使用的是 whisperx.load_model，它返回 FasterWhisperPipeline
                inner_model = model.model 
                
                current_filters = inner_model.feature_extractor.mel_filters
                is_v3_derived = "turbo" in self.model_path.lower() or "large-v3" in self.model_path.lower()
                
                if is_v3_derived and current_filters.shape[0] == 80:
                    self.progress.emit("应用模型热修复 (Applying Runtime Patch: 80->128)...")
                    logger.warning("Detecting 80-mel filters on v3/turbo model. Applying patch...")
                    import numpy as np
                    new_filters = inner_model.feature_extractor.get_mel_filters(
                        inner_model.feature_extractor.sampling_rate, 
                        inner_model.feature_extractor.n_fft, 
                        n_mels=128
                    )
                    new_filters = new_filters.astype(np.float32)
                    inner_model.feature_extractor.mel_filters = new_filters
                    logger.info("Applied mel-filter patch: 80 -> 128")
            except Exception as patch_e:
                 logger.warning(f"Patch failed (non-fatal?): {patch_e}")

            self.progress_percent.emit(10)
            
            if self._is_cancelled: return

            # --- 阶段 2: 加载音频与 VAD (Audio & VAD) ---
            self.progress.emit("正在读取音频与分析 VAD (Loading Audio & VAD)...")
            audio = whisperx.load_audio(self.audio_path)
            
            # 提示词处理
            # WhisperX 的 transcribe 接口支持 initial_prompt 但位置可能不同，
            # v3.1.1+ 通常通过 asr_options 传递
            prompt = self.initial_prompt
            if not prompt:
                if self.language == "zh":
                    prompt = "。，！？；"
                elif self.language == "en":
                    prompt = ".,!?; "
                else:
                    prompt = "。，！？；.,!?; "
            
            # 构建 ASR 选项
            asr_options = {
                "initial_prompt": prompt,
                "hotwords": None,
            }

            if self._is_cancelled: return

            # --- 阶段 3: 批量转写 (Batch Transcription) ---
            # 这是阻塞操作，进度条设为不确定模式 (-1)
            self.progress.emit("正在批量转写...")
            self.progress_percent.emit(-1) # Indeterminate mode
            
            batch_size = 16 # 显存允许时越大越快
            
            result = model.transcribe(
                audio, 
                batch_size=batch_size, 
                language=self.language,
                chunk_size=30, # VAD chunk size def 30s
                print_progress=False, # 我们无法捕获它的 stdout 进度
                combined_progress=False
            )
            # 注意: whisperx.transcribe 返回 dict: {'segments': [...], 'language': 'zh'}
            
            segments = result["segments"]
            detected_lang = result.get("language", "unknown")
            
            # 回显语言
            self.progress.emit(f"DETECTION: {detected_lang}")
            logger.info(f"Detected language: {detected_lang}")
            
            self.progress_percent.emit(90)
            
            # --- 阶段 4: 精准对齐 ---
            if self.align and not self._is_cancelled:
                try:
                    self.progress.emit("正在进行音频对齐...")
                    
                    # 加载对齐模型
                    align_model_dir = os.path.join(self.models_root, "alignment")
                    if not os.path.exists(align_model_dir):
                        os.makedirs(align_model_dir, exist_ok=True)

                    model_a, metadata = whisperx.load_align_model(
                        language_code=detected_lang, 
                        device=self.device,
                        model_dir=align_model_dir
                    )
                    
                    # 执行对齐
                    result_aligned = whisperx.align(
                        segments, 
                        model_a, 
                        metadata, 
                        audio, 
                        self.device, 
                        return_char_alignments=True
                    )
                    
                    # 资源清理
                    del model_a
                    if self.device == "cuda": torch.cuda.empty_cache()
                    
                    if "segments" in result_aligned:
                        # 转换格式以适配后续处理
                        aligned_segments = []
                        for seg in result_aligned["segments"]:
                            item = {
                                "start": seg.get("start", 0),
                                "end": seg.get("end", 0),
                                "text": seg.get("text", "")
                            }
                            if "words" in seg: item["words"] = seg["words"]
                            if "chars" in seg: item["chars"] = seg["chars"]
                            aligned_segments.append(item)
                        segments = aligned_segments
                        
                except Exception as ae:
                    logger.error(f"Alignment failed: {ae}")
                    self.progress.emit(f"对齐失败 (跳过): {ae}")
            
            # 释放主模型
            del model
            gc.collect()
            if self.device == "cuda": torch.cuda.empty_cache()

            # --- 阶段 5: SRT 后处理 ---
            if not self._is_cancelled:
                try:
                    from .srt_processor import SRTProcessor
                    self.progress.emit("正在优化字幕格式 (Finishing)...")
                    # whisperx 的 segment 结构可能稍有不同，确保兼容
                    processed_segments = SRTProcessor.process_segments(
                        segments, 
                        lang=detected_lang
                    )
                    segments = processed_segments
                except Exception as pe:
                    logger.warning(f"Post-processing warning: {pe}")

            self.progress_percent.emit(95)
            self.progress.emit("处理完成 (Finalizing)...")
            
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
        
    def start_transcription(self, audio_path, device="cuda", align=True, language=None, initial_prompt=None, vad_filter=True):
        if self.is_running():
            return False, "Task already running"
            
        model_path = self.manager.get_model_path() # 获取当前选定的模型 (Custom or Default)
        if not model_path:
            # [Auto Fallback] 如果未找到本地模型，默认使用 large-v3-turbo，
            # WhisperX 将会自动从 HuggingFace 缓存下载。
            logger.info("未找到本地模型，自动回退至默认模型 (Auto-Download): large-v3-turbo")
            model_path = self.manager.DEFAULT_MODEL_ID
            
        # 默认语言逻辑：如果您想支持 UI 传入，这里可以扩展
        self.worker = TranscriptionWorker(
            model_path, 
            audio_path,
            self.manager.models_root, # Pass the root path explicitly
            device, 
            align=align, 
            language=language,
            initial_prompt=initial_prompt,
            vad_filter=vad_filter
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
