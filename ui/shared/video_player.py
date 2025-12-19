"""
视频播放器组件
使用 python-vlc 实现视频播放和字幕显示
"""

import sys
import os
import time
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider,
    QLabel, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

logger = logging.getLogger(__name__)



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
        
        self.player = None
        self.instance = None
        self.current_video = None
        self.current_subtitle = None
        self.is_vlc_available = False
        self._reload_attempted = False  # 用于防止无限重载循环
        
        # 初始化VLC
        self._init_vlc()
        
        # 初始化UI
        self.setup_ui()
        
        # 更新定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(100)  # 100ms更新一次
        
        if self.is_vlc_available:
            logger.info("视频播放器初始化完成")
        else:
            logger.warning("VLC不可用，视频播放功能受限")
    
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
                # VLC 参数配置（针对字幕优化）
                # 经过测试，不应强制指定 codec，让 VLC 自动协商最佳渲染器（如 DirectWrite）
                args = [
                    "--avcodec-hw=none",  # 禁用硬件加速，防止花屏
                    "--quiet",  # 减少日志
                    "--sub-track=0", # 默认启用字幕
                    "--sub-autodetect-file", 
                    "--freetype-rel-fontsize=16",
                ]
                
                logger.debug(f"VLC Instance 参数: {args}")
                
                self.instance = vlc.Instance(args)
                self.player = self.instance.media_player_new()
                self.is_vlc_available = True
                logger.info("VLC初始化成功")
            except OSError as e:
                # 捕获架构不匹配错误 (如64位Python加载32位VLC)
                error_msg = str(e)
                if "193" in error_msg or "%1" in error_msg:
                    logger.error("VLC架构不匹配: 检测到尝试加载32位VLC DLL到64位Python环境 (或反之)")
                    self.last_error = "VLC架构不匹配: 请安装与Python位数一致的VLC (通常是64位)"
                else:
                    logger.error(f"加载VLC库失败: {e}")
                    self.last_error = f"VLC Load Error: {e}"
                self.is_vlc_available = False
                
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"VLC初始化失败: {e}\n{error_details}")
            self.last_error = f"VLC Init Error: {str(e)}"
            self.is_vlc_available = False
            
            # 额外提示
            if sys.maxsize > 2**32:
                # 64-bit Python
                if custom_vlc_path and "x86" in custom_vlc_path:
                    logger.warning("提示: 您正在运行64位Python，但VLC路径包含'x86'，这通常意味着您安装了32位VLC。请下载安装64位VLC。")
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 视频显示区域 (容器)
        self.display_area = VideoDisplayArea()
        # 实际用于渲染的句柄是内部的 video_frame
        self.video_frame = self.display_area.video_frame
        self.display_area.setMinimumSize(480, 270)
        
        if not self.is_vlc_available:
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
        
        # 设置VLC渲染窗口
        QTimer.singleShot(100, self._set_video_output)

    def setup_fallback_ui(self, layout):
        """设置后备UI（VLC缺失时）"""
        msg_frame = QFrame()
        msg_frame.setStyleSheet("background-color: #333; color: white;")
        msg_layout = QVBoxLayout(msg_frame)
        
        lbl = QLabel(self.tr("⚠️ 未检测到 VLC 播放器组件"))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        msg_layout.addWidget(lbl)
        
        info = QLabel(self.tr("请安装 VLC Media Player 以使用视频播放功能"))
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_layout.addWidget(info)
        
        link_btn = QPushButton(self.tr("去官网下载 VLC"))
        link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        link_btn.clicked.connect(lambda: os.startfile("https://www.videolan.org/vlc/"))
        msg_layout.addWidget(link_btn)
        
        layout.addWidget(msg_frame)
    
    def _set_video_output(self):
        """设置视频输出窗口"""
        if not self.player:
            return
        
        try:
            if sys.platform.startswith('win'):
                self.player.set_hwnd(int(self.video_frame.winId()))
            elif sys.platform == 'darwin':
                self.player.set_nsobject(int(self.video_frame.winId()))
            else:
                self.player.set_xwindow(int(self.video_frame.winId()))
        except Exception as e:
            logger.error(f"设置视频输出失败: {e}")
    
    def load_video(self, video_path: str) -> bool:
        """加载视频文件"""
        if not self.player or not self.instance:
            logger.error("VLC未初始化")
            return False
        
        try:
            import vlc
            media = self.instance.media_new(video_path)
            self.player.set_media(media)
            self.current_video = video_path
            
            logger.info(f"视频加载成功: {video_path}")
            
            # 自动预加载: 播放一小段以显示首帧并获取元数据，然后暂停
            self.player.play()
            # 150ms 应该足够显示首帧但不会播放太多声音
            QTimer.singleShot(150, self.player.pause)
            
            return True
        except Exception as e:
            logger.error(f"视频加载失败: {e}")
            return False
    
    def reload_with_subtitle(self, subtitle_path: str) -> bool:
        """
        重新加载当前视频并在创建 Media 时内联字幕
        这是一个 fallback 方案，当常规字幕加载失败时使用
        """
        if not self.current_video or not self.player or not self.instance:
            logger.error("无法重载：没有当前视频或VLC未初始化")
            return False
        
        try:
            logger.info(f"🔄 尝试重载视频并内嵌字幕：{subtitle_path}")
            
            # 保存当前播放位置和状态
            current_time = self.player.get_time() if self.player.is_playing() else 0
            was_playing = self.player.is_playing()
            
            # 1. 准备路径：始终转换为 URI 格式
            subtitle_path_normalized = subtitle_path.replace('\\', '/')
            from pathlib import Path
            try:
                uri_path = Path(subtitle_path).absolute().as_uri()
            except Exception:
                uri_path = None

            # 2. 创建新的 Media 对象 (使用 input-slave)
            media = self.instance.media_new(self.current_video)

            if os.path.exists(subtitle_path):
                # 优先使用 input-slave (VLC 推荐的同步加载方式)
                target_opt = uri_path if uri_path else subtitle_path_normalized
                media.add_option(f":input-slave={target_opt}")
                
                # 保留 sub-file 作为双重保险
                media.add_option(f":sub-file={target_opt}")
                
                # 自动检测编码，不强制指定 codec
                media.add_option(":sub-autodetect-file")
                
                logger.info(f"✅ 已将字幕选项添加到 Media (使用 input-slave)")
            else:
                logger.error(f"字幕文件不存在: {subtitle_path}")
                return False
            
            # 3. 设置并播放
            self.player.set_media(media)
            self.player.play()
            
            if current_time > 0:
                QTimer.singleShot(300, lambda: self.player.set_time(current_time))
            
            if not was_playing:
                QTimer.singleShot(400, self.player.pause)
            
            self.current_subtitle = subtitle_path
            logger.info("✅ 视频+字幕重载完成")
            
            # 4. 验证
            QTimer.singleShot(800, self._verify_subtitle_loaded)
            return True
            
        except Exception as e:
            logger.error(f"重载视频失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _verify_subtitle_loaded(self):
        """验证字幕是否真正加载"""
        if not self.player:
            return
        
        try:
            spu_count = self.player.video_get_spu_count()
            spu_ids = self.player.video_get_spu_description()
            current_spu = self.player.video_get_spu()
            
            logger.info(f"[验证] 字幕轨道: count={spu_count}, current={current_spu}")
            
            if spu_ids and len(spu_ids) > 1:
                logger.info("✅ 字幕轨道加载成功！")
                
                # 如果当前没有选中字幕，强制选中最后一个
                if current_spu == -1:
                    last_id = spu_ids[-1][0]
                    self.player.video_set_spu(last_id)
                    logger.info(f"验证后自动激活轨道: {last_id}")
            else:
                logger.warning("⚠️ 仍未检测到字幕轨道，可能是VLC版本问题或字幕文件格式不支持")
                
        except Exception as e:
            logger.error(f"验证失败: {e}")
    
    def load_subtitle(self, subtitle_path: str) -> bool:
        """加载外部字幕"""
        if not self.player:
            return False
        
        if not subtitle_path:
            return False
            
        # 路径防抖
        now = time.time()
        if hasattr(self, '_last_load_path') and self._last_load_path == subtitle_path:
            if hasattr(self, '_last_load_time') and now - self._last_load_time < 1.0:
                logger.debug(f"跳过重复字幕加载请求: {subtitle_path}")
                return True
        
        self._last_load_path = subtitle_path
        self._last_load_time = now
        self._reload_attempted = False  # 重置重载标志
        
        try:
            QTimer.singleShot(300, lambda: self._do_load_subtitle(subtitle_path))
            return True
        except Exception as e:
            logger.error(f"字幕加载请求失败: {e}")
            return False

    def _do_load_subtitle(self, subtitle_path):
        """实际执行加载字幕"""
        try:
            from pathlib import Path
            
            logger.info(f"正在尝试加载字幕: {subtitle_path}")
            
            if not os.path.exists(subtitle_path):
                logger.error(f"字幕文件不存在: {subtitle_path}")
                return False
            
            result = False
            uri_path = None
            try:
                uri_path = Path(subtitle_path).absolute().as_uri()
            except Exception:
                pass
            
            # 标准化路径
            path_normalized = subtitle_path.replace('\\', '/')

            # 策略优先级:
            # 1. 尝试 URI 格式的 add_slave (最推荐)
            if uri_path:
                # add_slave(type=0 subtitle, uri, select=True)
                res = self.player.add_slave(0, uri_path, True)
                if res == 0:
                    logger.info("add_slave(URI) 成功")
                    result = True
            
            # 2. 如果失败，尝试 URI 格式的 set_subtitle_file
                if self.player.video_set_subtitle_file(path_normalized):
                    logger.debug("video_set_subtitle_file(Path) 成功")
                    result = True
            
            # 4. 终极尝试：直接修改 Media 的 Options (虽然 Media 已存在，但某些 VLC 版本可能生效)
            if not result:
                m = self.player.get_media()
                if m:
                    m.add_option(f"sub-file={path_normalized}")
                    logger.debug("media.add_option(sub-file) 作为最后尝试")
                    result = True

            if result:
                self.current_subtitle = subtitle_path
                # 给予更多时间让 VLC 解析字幕文件
                QTimer.singleShot(500, lambda: self.activate_last_subtitle_track(retry=12))
            else:
                logger.error(f"❌ 所有字幕加载尝试均失败: {subtitle_path}")
                # 即使返回 False，也尝试一下 fallback check
                self.activate_last_subtitle_track(retry=0)
                return False
                
            return result
                
        except Exception as e:
            logger.error(f"字幕加载执行失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def activate_last_subtitle_track(self, retry=10):
        """激活最后一个字幕轨道"""
        if not self.player:
            return
            
        try:
            spu_count = self.player.video_get_spu_count()
            spu_ids = self.player.video_get_spu_description()
            
            logger.debug(f"[字幕轨道] count={spu_count}, ids={spu_ids}")
            
            if spu_ids and len(spu_ids) > 1:
                # 找到最后一个非禁用的轨道
                last_id = spu_ids[-1][0]
                self.player.video_set_spu(last_id)
                logger.info(f"✅ 成功激活字幕轨道 ID: {last_id}, 描述: {spu_ids[-1][1]}")
                
                # 验证
                QTimer.singleShot(100, self._verify_track_active)
            else:
                if retry > 0:
                    # 尝试短暂播放以激活
                    state = self.player.get_state()
                    import vlc
                    if state == vlc.State.Stopped or state == vlc.State.NothingSpecial:
                        logger.debug("视频未就绪，尝试短暂播放以激活字幕轨道...")
                        self.player.play()
                        QTimer.singleShot(50, self.player.pause)
                    
                    # 指数退避重试
                    delay = 500 if retry > 5 else 1000
                    logger.warning(f"⚠️ 未检测到字幕轨道，{delay}ms后重试 (剩余 {retry} 次)...")
                    QTimer.singleShot(delay, lambda: self.activate_last_subtitle_track(retry - 1))
                else:
                    logger.error("❌ 最终加载失败：即使增加重试也未检测到有效字幕轨道")
                    
                    # Fallback: 尝试重载视频+内嵌字幕
                    if self.current_subtitle and not self._reload_attempted:
                        logger.warning("🔄 尝试 fallback 方案：重载视频并内嵌字幕...")
                        self._reload_attempted = True
                        QTimer.singleShot(500, lambda: self.reload_with_subtitle(self.current_subtitle))

        except Exception as e:
            logger.error(f"激活字幕轨道异常: {e}")

    def _verify_track_active(self):
        """延迟验证轨道激活状态"""
        if not self.player: return
        try:
            current_spu = self.player.video_get_spu()
            spu_ids = self.player.video_get_spu_description()
            
            # 如果当前是 -1 (禁用)，但我们有轨道可用，再次尝试激活最后一个
            if current_spu == -1 and spu_ids and len(spu_ids) > 1:
                last_id = spu_ids[-1][0]
                logger.warning(f"⚠️ 首次激活似乎未生效，再次尝试激活轨道: {last_id}")
                self.player.video_set_spu(last_id)
            else:
                logger.debug(f"验证字幕激活状态: current={current_spu}")
        except Exception:
            pass



    
    def toggle_play_pause(self):
        """播放/暂停切换"""
        if not self.player:
            return
        
        if self.player.is_playing():
            self.pause()
        else:
            self.play()
    
    def play(self):
        """播放"""
        if not self.player:
            return
        
        self.player.play()
        self.play_pause_btn.setText("⏸")
        self.playback_started.emit()
        logger.debug("播放开始")
    
    def pause(self):
        """暂停"""
        if not self.player:
            return
        
        self.player.pause()
        self.play_pause_btn.setText("▶")
        self.playback_paused.emit()
        logger.debug("播放暂停")
    
    def stop(self):
        """停止"""
        if not self.player:
            return
        
        self.player.stop()
        self.play_pause_btn.setText("▶")
        self.timeline_slider.setValue(0)
        self.time_label.setText("00:00 / 00:00")
        self.playback_stopped.emit()
        logger.debug("播放停止")
    
    def seek_to_time(self, milliseconds: int):
        """跳转到指定时间（毫秒）"""
        if not self.player:
            return
        
        self.player.set_time(milliseconds)
        logger.debug(f"跳转到: {milliseconds}ms")
    
    def get_current_time(self) -> int:
        """获取当前播放时间（毫秒）"""
        if not self.player:
            return 0
        return self.player.get_time()
    
    def toggle_subtitles(self, visible: bool):
        """显示/隐藏字幕"""
        if not self.player:
            return
        
        # VLC字幕轨道控制
        if visible:
            self.player.video_set_spu(0)  # 启用第一个字幕轨道
        else:
            self.player.video_set_spu(-1)  # 禁用字幕
    
    def on_timeline_moved(self, position):
        """时间轴拖动"""
        if not self.player:
            return
        
        # 暂时禁用UI更新，避免冲突
        self._updating = True
    
    def on_timeline_pressed(self):
        """时间轴按下"""
        self._updating = True
    
    def on_timeline_released(self):
        """时间轴释放"""
        if not self.player:
            return
        
        total_time = self.player.get_length()
        if total_time > 0:
            position = self.timeline_slider.value()
            target_time = int(total_time * position / 1000)
            self.seek_to_time(target_time)
        
        self._updating = False
    
    def on_volume_changed(self, value):
        """音量变化"""
        if not self.player:
            return
        
        self.player.audio_set_volume(value)
    
    def update_ui(self):
        """更新UI（定时器调用）"""
        if not self.player or not hasattr(self, '_updating'):
            self._updating = False
            return
        
        # 如果正在拖动，跳过更新
        if self._updating:
            return
        
        current_time = self.player.get_time()
        total_time = self.player.get_length()
        
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
        if self.player:
            self.player.stop()
        super().closeEvent(event)
