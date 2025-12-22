import os
import re
import logging
import subprocess
import tempfile
from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

class ExportWorker(QThread):
    """
    FFmpeg 压制执行线程
    """
    progress = pyqtSignal(int)      # 0-100
    msg = pyqtSignal(str)           # 详细状态信息
    finished = pyqtSignal(bool, str) # success, error_msg

    def __init__(self, params, store):
        super().__init__()
        self.params = params
        self.store = store
        self._is_cancelled = False
        self._process = None

    def run(self):
        tmp_ass = None
        try:
            # 1. 准备临时 ASS 文件
            tmp_ass = self._prepare_ass()
            
            # 2. 构建 FFmpeg 命令
            cmd = self._build_command(tmp_ass)
            logger.info(f"Executing FFmpeg: {' '.join(cmd)}")
            
            # 3. 运行并获取总时长
            total_duration = self._get_video_duration(self.params['input'])
            
            # 启动进程
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # FFmpeg 的进度在 stderr，这里合流
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore',
                shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            # 4. 实时解析进度
            while True:
                if self._is_cancelled:
                    self._process.kill()
                    self.finished.emit(False, "用户取消了压制任务。")
                    return

                line = self._process.stdout.readline()
                if not line:
                    break
                
                # 采样行数据: frame=  123 fps=0.0 q=28.0 size=    1024kB time=00:00:03.45 bitrate=2422.3kbits/s speed=1.23x
                if "time=" in line:
                    match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                    if match:
                        h, m, s = match.groups()
                        current_ms = (int(h) * 3600 + int(m) * 60 + float(s)) * 1000
                        if total_duration > 0:
                            percent = int((current_ms / total_duration) * 100)
                            self.progress.emit(min(100, percent))
                
                # 如果有错误信息也记录
                if "Error" in line:
                    logger.warning(f"FFmpeg Warning: {line.strip()}")

            self._process.wait()
            if self._process.returncode == 0:
                self.finished.emit(True, "压制完成！")
            else:
                self.finished.emit(False, f"FFmpeg 退出异常，退出码: {self._process.returncode}")

        except Exception as e:
            logger.exception("Export failed")
            self.finished.emit(False, str(e))
        finally:
            if tmp_ass and os.path.exists(tmp_ass):
                try: os.remove(tmp_ass)
                except: pass

    def cancel(self):
        self._is_cancelled = True

    def _prepare_ass(self):
        """生成临时的 ASS 字幕文件"""
        # 使用 tempfile 生成一个唯一的临时文件
        fd, path = tempfile.mkstemp(suffix='.ass')
        os.close(fd)
        # 将当前的 SubtitleStore 内容保存到该文件
        self.store.subs.save(path)
        return path

    def _build_command(self, ass_path):
        p = self.params
        cmd = ["ffmpeg", "-y"]
        
        # 硬件解码
        if p.get('hw_dec') and p.get('dec_type') != 'auto':
            cmd.extend(["-hwaccel", p['dec_type']])
            
        cmd.extend(["-i", p['input']])
        
        # 滤镜部分 (针对 Windows 路径进行转义)
        # libass 滤镜在 Windows 下要求路径中的冒号必须转义，且路径通常使用正斜杠
        safe_ass_path = ass_path.replace("\\\\", "/").replace("\\", "/").replace(":", "\\\\:")
        filter_str = f"ass='{safe_ass_path}'"
        cmd.extend(["-vf", filter_str])
        
        # 视频编码
        enc = p.get('enc_type', 'libx264')
        cmd.extend(["-c:v", enc])
        
        # Preset 映射
        preset_val = p.get('preset', 4)
        if enc == 'libx264':
            presets = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"]
            cmd.extend(["-preset", presets[min(preset_val, 8)]])
        elif enc == 'h264_nvenc':
            cmd.extend(["-preset", f"p{min(max(1, 7-preset_val), 7)}"]) # 映射 0-8 到 p7-p1
        elif enc == 'h264_qsv':
            cmd.extend(["-preset", f"{min(preset_val, 7)}"]) # 0-7
            
        # 质量控制
        if p['mode'] == 'crf':
            if "nvenc" in enc:
                cmd.extend(["-rc", "vbr", "-cq", str(p['crf']), "-b:v", "0"])
            else:
                cmd.extend(["-crf", str(p['crf'])])
        else:
            # ABR
            cmd.extend(["-b:v", f"{p['bitrate']}k"])
            
        # 音频处理
        cmd.extend(["-c:a", "copy"])
        
        # 输出
        cmd.append(p['output'])
        return cmd

    def _get_video_duration(self, path):
        """获取视频总时长（毫秒）"""
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
            res = subprocess.check_output(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0).decode().strip()
            return float(res) * 1000
        except:
            return 0
