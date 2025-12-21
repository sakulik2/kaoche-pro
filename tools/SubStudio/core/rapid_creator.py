from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import logging

logger = logging.getLogger(__name__)

class RapidCreationController(QObject):
    """
    听音拍键控制器 (JK Keys)
    负责处理键盘输入、延迟补偿、磁性吸附以及最终的字幕生成
    """
    # 信号
    recording_started = pyqtSignal(float) # start_ms
    recording_progress = pyqtSignal(float, float) # start_ms, current_ms
    recording_finished = pyqtSignal()
    
    def __init__(self, store, audio_processor=None):
        super().__init__()
        self.store = store
        self.audio_processor = audio_processor
        
        # 配置参数 (Human Error Correction)
        self.latency_compensation_start = -150 # ms
        self.latency_compensation_end = -50    # ms
        self.magnetic_gap_threshold = 300      # ms
        self.min_duration = 300                # ms
        
        # 状态
        self.is_recording = False
        self.current_start_ms = 0
        self.active_group_name = "Default"
        
        # 计时器 (驱动 Ghost Block)
        self.tick_timer = QTimer()
        self.tick_timer.setInterval(30) # 30ms 刷新率
        self.tick_timer.timeout.connect(self._on_tick)
        
        self.current_video_time_ref = 0 # 外部注入的当前播放时间引用
        
    def set_active_group(self, group_name):
        """设置当前拍键使用的分组"""
        self.active_group_name = group_name
        
    def update_video_time(self, ms):
        """实时接收播放器时间"""
        self.current_video_time_ref = ms
        
    def on_key_press(self):
        """J/K 按下：开始录制"""
        if self.is_recording: return
        
        self.is_recording = True
        
        # 1. 应用延迟补偿
        raw_start = self.current_video_time_ref
        corrected_start = max(0, raw_start + self.latency_compensation_start)
        
        # 2. 磁性吸附 (Smart Snap)
        # 寻找上一条字幕的结束时间
        events = self.store.get_all_events()
        if events:
            # 简单策略：找最近的一个结束点。由于通常是顺序拍，取最后一个即可？
            # 还是遍历寻找 < corrected_start 且差值最小的那个？
            # 假设用户是顺序制作，取最后一个结束时间
            last_event = events[-1]
            gap = corrected_start - last_event.end
            if 0 < gap < self.magnetic_gap_threshold:
                logger.info(f"Magnetic Snap Triggered: Gap {gap:.1f}ms -> 0ms")
                corrected_start = last_event.end
        
        self.current_start_ms = corrected_start
        self.recording_started.emit(corrected_start)
        self.tick_timer.start()
        logger.info(f"Rapid Record START: Raw={raw_start:.0f}, Corrected={corrected_start:.0f}")

    def on_key_release(self):
        """J/K 松开：结束录制并提交"""
        if not self.is_recording: return
        
        self.is_recording = False
        self.tick_timer.stop()
        
        # 1. 应用延迟补偿
        raw_end = self.current_video_time_ref
        corrected_end = raw_end + self.latency_compensation_end
        
        # 2. VAD 智能纠错 (TODO: Phase 7.2)
        # corrected_end = self._apply_vad_correction(self.current_start_ms, corrected_end)
        
        # 3. 门控 (Min Duration)
        duration = corrected_end - self.current_start_ms
        if duration < self.min_duration:
            logger.warning(f"Record dropped: Duration {duration:.0f}ms < {self.min_duration}ms")
            # 依然发射 finished 以清除 Ghost Block
            self.recording_finished.emit()
            return
            
        # 4. 提交数据
        # 自动获取分组样式
        group_info = self.store.get_group_info(self.active_group_name)
        style = group_info["style"] if group_info else "Default"
        
        # 创建事件
        # 注意：add_event 会自动 sort，但为了性能，也许批量拍键时不该每次都 sort?
        # 暂且用 add_event，性能瓶颈后再优化
        self.store.add_event(
            start_ms=int(self.current_start_ms),
            end_ms=int(corrected_end),
            text="在此输入...",
            style=style
        )
        
        # 修正 Metadata (Group/Actor)
        # add_event 默认没加 Name/Actor 字段，我们需要手动 patch 或者修改 add_event
        # 这里直接获取刚加进去的那条 (最后一条? 不一定，因为 sorted)
        # 为了稳妥，我们修改 add_event 让它返回 index 或者 event 对象，或者直接在这里 update
        # 此时 store 的 events 已经重新排序了。
        # 这是一个潜在 Race Condition。
        # 更好的做法是给 store 加一个 add_event_with_kwargs
        
        # 临时补救：遍历找刚才那条？容易错。
        # 建议：修改 SubtitleStore.add_event 支持 **kwargs
        
        # 既然我们控制 Store 代码，我会在稍后修改 Store。
        # 现在假设 add_event 之后，我们通过特定的标记或时间戳找到它？
        # 或者直接在 Store 里加一个专用接口：add_group_event
        
        # 暂时用折衷方案：只通过 add_event 加，Group 属性均在 Default Group 逻辑里覆盖？不行。
        # 我将调用 store.assign_group_to_events 针对刚刚插入的那个。
        # 寻找匹配 start/end 的 event
        target_idx = -1
        events = self.store.get_all_events()
        for i, ev in enumerate(events):
            if abs(ev.start - self.current_start_ms) < 2 and abs(ev.end - corrected_end) < 2:
                target_idx = i
                break
        
        if target_idx >= 0:
            self.store.assign_group_to_events([target_idx], self.active_group_name)
            
        self.recording_finished.emit()
        logger.info(f"Rapid Record END: Duration={duration:.0f}ms")

    def _on_tick(self):
        """驱动 UI 刷新 Ghost Block"""
        if self.is_recording:
            # 假定当前时间就是 End
            current = self.current_video_time_ref
            self.recording_progress.emit(self.current_start_ms, current)
