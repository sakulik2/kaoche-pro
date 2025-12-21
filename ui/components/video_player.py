import sys
import os
import time
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider,
    QLabel, QFrame, QMessageBox, QStackedWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject

logger = logging.getLogger(__name__)




# ==========================================
# 1. Backends: VLC & MPV Abstraction
# ==========================================

class BasePlayerBackend(QObject):
    playback_started = pyqtSignal()
    playback_paused = pyqtSignal()
    playback_stopped = pyqtSignal()

    def __init__(self, target_wid):
        super().__init__()
        self.wid = target_wid

    def load(self, path): raise NotImplementedError
    def play(self): raise NotImplementedError
    def pause(self): raise NotImplementedError
    def stop(self): raise NotImplementedError
    def seek(self, ms): raise NotImplementedError
    def get_time(self): raise NotImplementedError
    def get_length(self): raise NotImplementedError
    def get_rate(self): raise NotImplementedError
    def is_playing(self): raise NotImplementedError
    def set_pause(self, paused): raise NotImplementedError
    def set_volume(self, val): raise NotImplementedError
    def load_subtitle(self, path): pass
    def reload_with_subtitle(self, video_path, sub_path): pass
    def release(self): pass

class VlcBackend(BasePlayerBackend):
    def __init__(self, target_wid, instance=None):
        super().__init__(target_wid)
        import vlc
        if instance:
            self.instance = instance
        else:
            args = ["--avcodec-hw=none", "--quiet", "--sub-track=0"]
            self.instance = vlc.Instance(args)
        
        self.player = self.instance.media_player_new()
        if sys.platform == "win32":
            self.player.set_hwnd(int(target_wid))
        else:
            self.player.set_xwindow(int(target_wid))

    def load(self, path):
        self.player.set_media(self.instance.media_new(path))
        self.player.play()
        QTimer.singleShot(150, self.player.pause)

    def play(self): self.player.play(); self.playback_started.emit()
    def pause(self): self.player.pause(); self.playback_paused.emit()
    def stop(self): self.player.stop(); self.playback_stopped.emit()
    def seek(self, ms): self.player.set_time(int(ms))
    def get_time(self): return self.player.get_time()
    def get_length(self): return self.player.get_length()
    def get_rate(self): return self.player.get_rate()
    def is_playing(self): return self.player.is_playing() == 1
    def set_pause(self, paused): self.player.set_pause(1 if paused else 0)
    def set_volume(self, val): self.player.audio_set_volume(val)
    
    def load_subtitle(self, path):
        """VLC 专用字幕加载逻辑"""
        try:
            from pathlib import Path
            uri_path = Path(path).absolute().as_uri()
            # 策略优先级: add_slave
            res = self.player.add_slave(0, uri_path, True)
            if res != 0:
                self.player.video_set_subtitle_file(path.replace('\\', '/'))
            return True
        except:
            return False

    def reload_with_subtitle(self, video_path, sub_path):
        """VLC 专用重载逻辑"""
        try:
            norm_sub = sub_path.replace('\\', '/')
            m = self.instance.media_new(video_path)
            m.add_option(f":input-slave={norm_sub}")
            self.player.set_media(m)
            self.player.play()
            return True
        except:
            return False

    def release(self):
        self.player.stop()
        self.player.release()
        if hasattr(self, 'instance'):
            self.instance.release()

class MpvBackend(BasePlayerBackend):
    def __init__(self, target_wid):
        super().__init__(target_wid)
        import mpv
        self.player = mpv.MPV(wid=str(int(target_wid)), vo='gpu', log_handler=None)

    def load(self, path): self.player.play(path)
    def play(self): self.player.pause = False; self.playback_started.emit()
    def pause(self): self.player.pause = True; self.playback_paused.emit()
    def stop(self): self.player.stop(); self.playback_stopped.emit()
    def seek(self, ms): self.player.time_pos = ms / 1000.0
    def get_time(self): return int((self.player.time_pos or 0) * 1000)
    def get_length(self): return int((self.player.duration or 0) * 1000)
    def get_rate(self): return self.player.speed or 1.0
    def is_playing(self): return not self.player.pause
    def set_pause(self, paused): self.player.pause = paused
    def set_volume(self, val): self.player.volume = val
    def release(self): self.player.terminate()

class VideoDisplayArea(QWidget):
    """
    视频显示区域容器
    负责计算并维持内部视频帧的 16:9 比例 (Letterbox/Pillarbox模式)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_frame = QFrame(self)
        self.video_frame.setStyleSheet("background-color: black;")
        
    def resizeEvent(self, event):
        """计算最佳 16:9 loading 区域"""
        size = event.size()
        w = size.width()
        h = size.height()
        
        target_ratio = 16.0 / 9.0
        current_ratio = w / h if h > 0 else 0
        
        if current_ratio > target_ratio:
            # 容器太宽，高度为基准 (Pillarbox)
            new_h = h
            new_w = int(h * target_ratio)
            x = (w - new_w) // 2
            y = 0
        else:
            # 容器太高，宽度为基准 (Letterbox for the container itself)
            new_w = w
            new_h = int(w / target_ratio)
            x = 0
            y = (h - new_h) // 2
            
        self.video_frame.setGeometry(x, y, new_w, new_h)
        self.video_frame.setGeometry(x, y, new_w, new_h)
        super().resizeEvent(event)

class ClickableSlider(QSlider):
    """支持点击跳转的滑块"""
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * event.position().x()) / self.width()
            self.setValue(int(val))
            event.accept()
            # 触发信号
            self.sliderPressed.emit()
            self.sliderMoved.emit(int(val))
            # 同时也处理后续的拖动
        super().mousePressEvent(event)

class VideoPlayerWidget(QWidget):
    """视频播放器组件"""
    
    # 信号定义
    time_changed = pyqtSignal(int)  # 播放位置变化（毫秒）
    playback_started = pyqtSignal()
    playback_paused = pyqtSignal()
    playback_stopped = pyqtSignal()
    current_subtitle_index = pyqtSignal(int)  # 当前字幕索引
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.current_video = None
        self.backend = None
        self._engine_type = "vlc" # 默认 VLC
        self.is_vlc_available = False
        self.is_mpv_available = False
        
        # 预检 VLC (处理 DLL 路径)
        self._init_vlc()
        
        # 检查 MPV
        try:
            import mpv
            self.is_mpv_available = True
        except Exception:
            # 捕获 ImportError 或缺失 DLL 的 OSError
            self.is_mpv_available = False

        # 初始化UI (依赖 is_vlc_available 决定是否显示 fallback)
        self.setup_ui()
        
        # 只有在后端可用时才切换引擎
        if self.is_vlc_available or self.is_mpv_available:
            self.switch_engine(self._engine_type)
        
        # 更新定时器 (16ms = 60FPS)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(16)
    
    def _init_vlc(self):
        """初始化VLC实例"""
        try:
            # 注意：不能在这里先 import vlc，必须先设置好路径
            import traceback
            import os
            import json
            
            # 读取配置中的VLC路径
            custom_vlc_path = None
            try:
                settings_file = 'config/settings.json'
                if os.path.exists(settings_file):
                    with open(settings_file, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                        custom_vlc_path = settings.get('advanced', {}).get('vlc_path')
            except Exception:
                pass
            
            # Windows下尝试自动查找VLC
            if sys.platform.startswith('win'):
                vlc_paths = []
                
                # 优先使用自定义路径
                if custom_vlc_path and os.path.exists(custom_vlc_path):
                    vlc_paths.append(custom_vlc_path)
                    logger.info(f"配置使用自定义VLC路径: {custom_vlc_path}")
                
                # 默认路径
                vlc_paths.extend([
                    r"C:\Program Files\VideoLAN\VLC",
                    r"C:\Program Files (x86)\VideoLAN\VLC"
                ])
                
                found_vlc = False
                for p in vlc_paths:
                    if os.path.exists(p):
                        try:
                            # 关键：检查是否存在libvlc.dll
                            dll_path = os.path.join(p, 'libvlc.dll')
                            if os.path.exists(dll_path):
                                #而在 Python 3.8+ Windows上，必须使用 add_dll_directory
                                os.add_dll_directory(p)
                                
                                # 同时设置环境变量，帮助 vlc.py 找到文件
                                os.environ['PYTHON_VLC_LIB_PATH'] = dll_path
                                os.environ['VLC_PLUGIN_PATH'] = os.path.join(p, 'plugins')
                                
                                logger.info(f"已添加VLC DLL路径: {p}")
                                found_vlc = True
                                break
                        except Exception as e:
                            logger.error(f"尝试添加路径 {p} 失败: {e}")
                
                if not found_vlc and not custom_vlc_path:
                    logger.warning("未在标准路径找到VLC，且未配置自定义路径")

            # 路径设置完成后，再导入 vlc
            try:
                import vlc
                args = [
                    "--avcodec-hw=none",  # 禁用硬件加速，防止花屏
                    "--quiet",  # 减少日志
                    "--sub-track=0", # 默认启用字幕
                    "--sub-autodetect-file", 
                    "--freetype-rel-fontsize=16",
                ]
                self.instance = vlc.Instance(args)
                self.is_vlc_available = True
                logger.info("VLC 检测成功")
            except Exception as e:
                logger.error(f"VLC 初始化失败: {e}")
                self.is_vlc_available = False
        except Exception as e:
            logger.error(f"VLC 配置环境失败: {e}")
            self.is_vlc_available = False
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 视频显示区域 (容器)
        self.display_area = VideoDisplayArea()
        # 实际用于渲染的句柄是内部的 video_frame
        self.video_frame = self.display_area.video_frame
        self.display_area.setMinimumSize(480, 270)
        
        if not self.is_vlc_available and not self.is_mpv_available:
            self.setup_fallback_ui(layout)
            return

        layout.addWidget(self.display_area)
        
        # 控制面板
        controls_layout = QHBoxLayout()
        
        # 播放/暂停按钮
        self.play_pause_btn = QPushButton("▶")
        self.play_pause_btn.setFixedWidth(30)
        self.play_pause_btn.clicked.connect(self.toggle_play_pause)
        controls_layout.addWidget(self.play_pause_btn)
        
        # 停止按钮
        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedWidth(30)
        self.stop_btn.clicked.connect(self.stop)
        controls_layout.addWidget(self.stop_btn)
        
        # 时间轴 (使用自定义ClickableSlider)
        self.timeline_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.timeline_slider.setRange(0, 1000)
        self.timeline_slider.sliderMoved.connect(self.on_timeline_moved)
        self.timeline_slider.sliderPressed.connect(self.on_timeline_pressed)
        self.timeline_slider.sliderReleased.connect(self.on_timeline_released)
        controls_layout.addWidget(self.timeline_slider)
        
        # 时间显示 - 简化显示
        self.time_label = QLabel("00:00")
        controls_layout.addWidget(self.time_label)
        
        # 音量
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(60)
        self.volume_slider.valueChanged.connect(self.on_volume_changed)
        controls_layout.addWidget(QLabel("🔊"))
        controls_layout.addWidget(self.volume_slider)
        
        layout.addLayout(controls_layout)

    def setup_fallback_ui(self, layout):
        """设置后备UI（当所有播放引擎均不可用时）"""
        msg_frame = QFrame()
        msg_frame.setStyleSheet("background-color: #1a1a1a; color: #d4d4d4; border-radius: 8px;")
        msg_layout = QVBoxLayout(msg_frame)
        msg_layout.setSpacing(15)
        msg_layout.setContentsMargins(40, 40, 40, 40)
        
        lbl = QLabel("⚠️ " + self.tr("未检测到可用的视频播放引擎"))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-weight: bold; font-size: 16px; color: #e74c3c;")
        msg_layout.addWidget(lbl)
        
        info = QLabel(self.tr("SubStudio 需要 VLC 或 MPV 引擎来提供丝滑的视频预览体验。"))
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setWordWrap(True)
        msg_layout.addWidget(info)
        
        btn_layout = QHBoxLayout()
        vlc_btn = QPushButton("下载 VLC")
        vlc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        vlc_btn.clicked.connect(lambda: os.startfile("https://www.videolan.org/vlc/"))
        
        mpv_btn = QPushButton("下载 MPV")
        mpv_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mpv_btn.clicked.connect(lambda: os.startfile("https://mpv.io/installation/"))
        
        btn_layout.addWidget(vlc_btn)
        btn_layout.addWidget(mpv_btn)
        msg_layout.addLayout(btn_layout)
        
        layout.addStretch()
        layout.addWidget(msg_frame, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
    
    # _set_video_output 已移除，由后端 initialization 自动处理
    
    def switch_engine(self, engine_type="vlc"):
        """切换播放引擎 (vlc / mpv)"""
        if self.backend:
            self.backend.release()
            
        self._engine_type = engine_type
        try:
            if engine_type == "vlc":
                if not self.is_vlc_available:
                    raise RuntimeError("VLC engine not available")
                if not getattr(self, "instance", None):
                    self._init_vlc()
                self.backend = VlcBackend(self.video_frame.winId(), self.instance)
            else:
                if not self.is_mpv_available:
                    raise RuntimeError("MPV engine not available")
                self.backend = MpvBackend(self.video_frame.winId())
            
            # 重新桥接信号
            self.backend.playback_started.connect(self.playback_started.emit)
            self.backend.playback_paused.connect(self.playback_paused.emit)
            self.backend.playback_stopped.connect(self.playback_stopped.emit)
            
            if self.current_video:
                self.backend.load(self.current_video)
                
            logger.info(f"成功切换至 {engine_type} 引擎")
        except Exception as e:
            logger.error(f"切換引擎 {engine_type} 失败: {e}")
            if engine_type == "mpv": # 如果 MPV 失败，尝试回到 VLC
                 self.switch_engine("vlc")

    def load_video(self, video_path: str) -> bool:
        """加载视频文件"""
        if not self.backend: return False
        try:
            self.current_video = video_path
            return self.backend.load(video_path)
        except Exception as e:
            logger.error(f"加载视频失败: {e}")
            return False
    
    def load_subtitle(self, subtitle_path: str) -> bool:
        """加载外部字幕"""
        if not self.backend: return False
        try:
            # 记录当前字幕路径，用于可能的重载 fallback
            self.current_subtitle = subtitle_path
            return self.backend.load_subtitle(subtitle_path)
        except Exception as e:
            logger.error(f"字幕加载失败: {e}")
            return False

    def reload_with_subtitle(self, subtitle_path: str) -> bool:
        """
        重新加载当前视频并在创建 Media 时内联字幕
        这是一个 fallback 方案，当常规字幕加载失败时使用
        """
        if not self.backend: return False
        if not self.current_video:
            logger.error("无法重载：没有当前视频")
            return False
        
        try:
            # 记录当前字幕路径
            self.current_subtitle = subtitle_path
            return self.backend.reload_with_subtitle(self.current_video, subtitle_path)
        except Exception as e:
            logger.error(f"重载视频并内嵌字幕失败: {e}")
            return False
    
    def toggle_play_pause(self):
        """播放/暂停切换"""
        if not self.backend:
            return
        
        if self.backend.is_playing():
            self.pause()
        else:
            self.play()
    
    def play(self):
        """播放"""
        if self.backend:
            self.backend.play()
            self.play_pause_btn.setText("⏸")
    
    def pause(self):
        """暂停"""
        if self.backend:
            self.backend.pause()
            self.play_pause_btn.setText("▶")
    
    def stop(self):
        """停止"""
        if self.backend:
            self.backend.stop()
            self.play_pause_btn.setText("▶")
            self.timeline_slider.setValue(0)
            self.time_label.setText("00:00 / 00:00")
        
    def get_rate(self) -> float:
        """获取当前播放倍速"""
        if not self.backend: return 1.0
        return self.backend.get_rate()

    def get_length(self) -> int:
        """获取总时长（毫秒）"""
        if not self.backend: return 0
        return self.backend.get_length()

    def set_pause(self, paused: bool):
        """显式设置暂停状态"""
        if not self.backend: return
        self.backend.set_pause(paused)
        self.play_pause_btn.setText("▶" if paused else "⏸")
    
    def seek_to_time(self, milliseconds: int):
        """跳转到指定时间（毫秒）"""
        if self.backend:
            self.backend.seek(milliseconds)
    
    def get_current_time(self) -> int:
        """获取当前播放时间（毫秒）"""
        if not self.backend: return 0
        return self.backend.get_time()
        
    def is_playing(self) -> bool:
        """获取当前播放状态"""
        if self.backend:
            return self.backend.is_playing()
        return False
    
    def toggle_subtitles(self, visible: bool):
        """显示/隐藏字幕 (如果有的话)"""
        if hasattr(self.backend, 'toggle_subtitles'):
            self.backend.toggle_subtitles(visible)
    
    def on_timeline_moved(self, position):
        """时间轴拖动"""
        self._updating = True
    
    def on_timeline_pressed(self):
        """时间轴按下"""
        self._updating = True
    
    def on_timeline_released(self):
        """时间轴释放"""
        if not self.backend:
            return
        
        total_time = self.backend.get_length()
        if total_time > 0:
            position = self.timeline_slider.value()
            target_time = int(total_time * position / 1000)
            self.seek_to_time(target_time)
        
        self._updating = False
    
    def on_volume_changed(self, value):
        """音量变化"""
        if self.backend:
            self.backend.set_volume(value)
    
    def update_ui(self):
        """更新UI（定时器调用）"""
        if not self.backend or not hasattr(self, '_updating'):
            self._updating = False
            return
        
        # 如果正在拖动，跳过更新
        if self._updating:
            return
        
        current_time = self.backend.get_time()
        total_time = self.backend.get_length()
        
        if current_time < 0:
            current_time = 0
        if total_time < 0:
            total_time = 0
        
        # 更新时间轴
        if total_time > 0:
            position = int(current_time * 1000 / total_time)
            self.timeline_slider.setValue(position)
        
        # 更新时间显示
        self.time_label.setText(
            f"{self.format_time(current_time)} / {self.format_time(total_time)}"
        )
        
        # 发射时间变化信号
        if current_time > 0:
            self.time_changed.emit(current_time)
    
    def format_time(self, milliseconds: int) -> str:
        """格式化时间显示"""
        if milliseconds < 0:
            milliseconds = 0
        
        seconds = milliseconds // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
    
    def closeEvent(self, event):
        """关闭事件"""
        self.close()
        super().closeEvent(event)

    def close(self):
        """显式关闭并释放资源"""
        if self.timer:
            self.timer.stop()
        
        if self.backend:
            self.backend.release()
            self.backend = None
