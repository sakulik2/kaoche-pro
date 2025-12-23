import os
import logging
from PyQt6.QtCore import QObject, pyqtSignal, QThread

logger = logging.getLogger(__name__)

class ModelDownloadThread(QThread):
    """独立的下载线程，避免阻塞 UI"""
    progress = pyqtSignal(str) # 进度信息
    finished = pyqtSignal(bool, str) # success, path/error

    def __init__(self, repo_id, local_dir, mirror_url=None):
        super().__init__()
        self.repo_id = repo_id
        self.local_dir = local_dir
        self.mirror_url = mirror_url

    def run(self):
        try:
            # 动态设置环境变量
            if self.mirror_url:
                os.environ["HF_ENDPOINT"] = self.mirror_url
            else:
                # 如果没有指定，清除可能存在的环境变量（恢复官方源）
                if "HF_ENDPOINT" in os.environ:
                    del os.environ["HF_ENDPOINT"]
            
            from huggingface_hub import snapshot_download
            
            source_name = "镜像源" if self.mirror_url else "官方源"
            self.progress.emit(f"开始从 {source_name} 下载: {self.repo_id} ...")
            
            # 使用 snapshot_download 下载整个仓库
            # allow_patterns 只下载必要文件 (model.bin, config.json, vocabulary等)
            # 对于 CTranslate2 模型，通常需要 model.bin, config.json, vocabulary.json/txt
            # 智能判断下载模式
            allow_patterns = None
            if "sherpa" in self.repo_id.lower() or "parakeet" in self.repo_id.lower():
                # Sherpa 模型只需要 onnx 和 tokens
                allow_patterns = ["*.onnx", "tokens.txt"]
            else:
                # Whisper/CTranslate2 模型默认下载所有关键文件
                # 也可以显式指定 ["model.bin", "config.json", "vocabulary.*"] 但默认通常没问题
                pass

            model_path = snapshot_download(
                repo_id=self.repo_id,
                local_dir=self.local_dir,
                local_dir_use_symlinks=False, # 必须 False，否则 Windows 下可能产生无法读取的软链
                resume_download=True,
                max_workers=4,
                allow_patterns=allow_patterns
            )
            
            self.progress.emit("下载完成！")
            self.finished.emit(True, model_path)
            
        except Exception as e:
            logger.error(f"Download failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.finished.emit(False, str(e))

class ModelManager(QObject):
    """
    统一管理 AI 模型的下载、路径解析与状态检查
    """
    # 信号
    download_started = pyqtSignal()
    download_progress = pyqtSignal(str)
    download_finished = pyqtSignal(bool, str) # success, message
    model_list_changed = pyqtSignal() # 当只有状态更新时触发
    
    # 支持的模型列表
    # 支持的模型列表
    SUPPORTED_MODELS = [
        # Whisper Models
        {"id": "deepdml/faster-whisper-large-v3-turbo-ct2", "name": "Large V3 Turbo (推荐)", "size": "1.6GB", "desc": "速度与精度的最佳平衡", "type": "whisper"},
        {"id": "Systran/faster-whisper-large-v3", "name": "Large V3 (官方)", "size": "3.1GB", "desc": "精度最高，但速度较慢", "type": "whisper"},
        {"id": "Systran/faster-whisper-medium", "name": "Medium", "size": "1.5GB", "desc": "平衡型", "type": "whisper"},
        {"id": "Systran/faster-whisper-small", "name": "Small", "size": "500MB", "desc": "速度快，精度一般", "type": "whisper"},
        {"id": "Systran/faster-whisper-base", "name": "Base", "size": "200MB", "desc": "极速，适合简单场景", "type": "whisper"},
        
        # Sherpa-ONNX Models
        {
            "id": "csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8", 
            "name": "Parakeet TDT 0.6B (Int8)", 
            "size": "~700MB", 
            "desc": "Sherpa-ONNX引擎，RNN-T架构，实时性好", 
            "type": "sherpa"
        },
        # Punctuation Model
        {
            "id": "csukuangfj/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12",
            "name": "Sherpa Punctuation (ZH/EN)",
            "size": "50 MB",
            "desc": "自动标点恢复 (支持中英文)",
            "type": "punctuation",
            "engine": "sherpa"
        },
    ]
    
    DEFAULT_MODEL_ID = "deepdml/faster-whisper-large-v3-turbo-ct2"
    
    def __init__(self, base_dir=None):
        super().__init__()
        
        # 确定模型存储根目录
        if base_dir:
            self.models_root = base_dir
        else:
            # 默认：tools/SubStudio/models
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.models_root = os.path.join(current_dir, "models")
            
        if not os.path.exists(self.models_root):
            os.makedirs(self.models_root)
            
        self.download_thread = None
        self._custom_model_path = None # 用户自定义的本地路径

    def set_custom_model_path(self, path):
        """设置自定义模型路径 (优先使用)"""
        if path and os.path.exists(path):
            self._custom_model_path = path
            return True
        self._custom_model_path = None
        return False

    def scan_local_models(self):
        """
        递归扫描 models_root 下的所有子文件夹，寻找包含 model.bin 或 tokens.txt 的目录
        返回: list of (name, full_path)
        """
        found_models = []
        try:
            for root, dirs, files in os.walk(self.models_root):
                # Whisper Check
                is_whisper = "model.bin" in files and "config.json" in files
                # Sherpa Check (tokens.txt + encoder*.onnx)
                # 必须包含 encoder，避免过早识别为就绪
                has_onnx = any(f.endswith(".onnx") for f in files)
                has_encoder = any("encoder" in f and f.endswith(".onnx") for f in files)
                is_sherpa = "tokens.txt" in files and has_encoder
                
                if is_whisper or is_sherpa:
                    # Found a valid model dir
                    # Create a friendly name relative to models_root
                    rel_path = os.path.relpath(root, self.models_root)
                    # e.g. whisper/large-v3-turbo
                    found_models.append((rel_path, root))
        except Exception as e:
            logger.error(f"Failed to scan local models: {e}")
            
        return found_models

    def get_supported_models(self):
        return self.SUPPORTED_MODELS

    def get_model_path(self, model_id=None):
        """
        获取模型的本地绝对路径 (带自动寻优逻辑)
        优先级: 自定义路径 > 指定ID路径 > 默认ID路径 > 本地已存在的最高质量模型
        """
        # 1. 优先检查自定义路径
        if self._custom_model_path and os.path.exists(self._custom_model_path):
             return self._custom_model_path
             
        # 2. 检查指定 ID 或默认 ID
        if not model_id:
            model_id = self.DEFAULT_MODEL_ID
            
        sanitized_name = model_id.replace("/", "_")
        target_dir = os.path.join(self.models_root, sanitized_name)
        
        # Check validity based on type (heuristic)
        if os.path.exists(target_dir):
            files = os.listdir(target_dir)
            if "model.bin" in files: return target_dir
            if "tokens.txt" in files:
                # Sherpa Parakeet Check: needs encoder, decoder, joiner
                has_enc = any("encoder" in f and f.endswith(".onnx") for f in files)
                has_dec = any("decoder" in f and f.endswith(".onnx") for f in files)
                has_join = any("joiner" in f and f.endswith(".onnx") for f in files)
                if has_enc and has_dec and has_join:
                    return target_dir
            
        # 3. [智能寻优] 如果指定模型不在，尝试在本地 models 目录下找一个最好的“替补”
        logger.info(f"Model {model_id} not found locally, scanning for best alternative...")
        
        # 确定目标类型
        target_type = "whisper" # 默认
        for m in self.SUPPORTED_MODELS:
            if m["id"] == model_id:
                target_type = m.get("type", "whisper")
                break
                
        locals = self.scan_local_models() # list of (rel_path, full_path)
        
        # 筛选同类型模型
        candidates = []
        for name, path in locals:
            # 检测本地模型类型
            local_type = "unknown"
            files = []
            try: files = os.listdir(path)
            except: continue
            
            if "model.bin" in files: local_type = "whisper"
            elif "tokens.txt" in files and any(f.endswith(".onnx") for f in files): local_type = "sherpa"
            
            if local_type == target_type:
                candidates.append((name, path))
                
        if not candidates:
            return None
            
        # 优先级权重 (分值越高越好)
        rank = {"large-v3": 100, "large": 90, "medium": 70, "small": 50, "base": 30, "tiny": 10, "parakeet": 80}
        best_path = None
        max_score = -1
        
        for name, path in candidates:
            score = 5 # 基础分
            lower_name = name.lower()
            for key, val in rank.items():
                if key in lower_name:
                    score = max(score, val); break
            
            if score > max_score:
                max_score = score
                best_path = path
        
        if best_path:
            logger.info(f"Auto-selected best alternative model: {best_path} (Score: {max_score})")
            
        return best_path

    def is_model_ready(self, model_id=None):
        return self.get_model_path(model_id) is not None

    def download_model(self, model_id=None, mirror_url="https://hf-mirror.com"):
        """
        启动后台线程下载模型
        :param model_id: 模型ID
        :param mirror_url: 镜像地址，如果为None则使用官方源
        """
        if not model_id:
            model_id = self.DEFAULT_MODEL_ID
            
        sanitized_name = model_id.replace("/", "_")
        target_dir = os.path.join(self.models_root, sanitized_name)
        
        if self.download_thread and self.download_thread.isRunning():
            logger.warning("Download already in progress")
            return False

        self.download_thread = ModelDownloadThread(model_id, target_dir, mirror_url)
        self.download_thread.progress.connect(self.download_progress.emit)
        self.download_thread.finished.connect(self._on_download_finished)
        
        self.download_started.emit()
        self.download_thread.start()
        return True
        
    def _on_download_finished(self, success, result):
        self.download_finished.emit(success, result)
        self.download_thread = None
