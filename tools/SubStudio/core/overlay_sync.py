from PyQt6.QtCore import QObject, QEvent, QRect, QPoint, Qt
from PyQt6.QtWidgets import QWidget
import logging

logger = logging.getLogger(__name__)

class OverlaySyncController(QObject):
    """
    负责将 OverlayWindow 物理吸附到 VideoContainer 上
    使用 EventFilter 监听宿主窗口的变化
    """
    def __init__(self, overlay_window: QWidget, video_container: QWidget):
        super().__init__()
        self.overlay = overlay_window
        self.container = video_container
        self.is_active = False

    def start_sync(self):
        """开启同步"""
        if not self.container:
            return
            
        # 安装事件过滤器
        self.container.installEventFilter(self)
        self.container.window().installEventFilter(self) # 同时也监听主窗口移动
        
        self.is_active = True
        
        # 修正：不要立即 Show，而是检查容器可见性
        # 这解决了“窗口打开时字幕先出现”的问题
        if self.container.isVisible():
            self.overlay.show()
            self._sync_geometry()
        else:
            self.overlay.hide()
            
        logger.info("Overlay Sync Started")

    def stop_sync(self):
        """停止同步"""
        if self.container:
            self.container.removeEventFilter(self)
            try:
                self.container.window().removeEventFilter(self)
            except:
                pass
        
        self.is_active = False
        self.overlay.hide()
        logger.info("Overlay Sync Stopped")

    def eventFilter(self, obj, event):
        """由于 VLC 窗口层级特殊，必须通过此方式持续跟踪"""
        if not self.is_active:
            return False

        # 监听容器或主窗口的变动
        if event.type() in [QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange]:
            self._sync_geometry()
        
        # 窗口关闭或隐藏时
        if event.type() == QEvent.Type.Hide:
            if obj == self.container or obj == self.container.window():
                 self.overlay.hide()
        
        if event.type() == QEvent.Type.Show:
             if obj == self.container:
                 self.overlay.show()
                 self._sync_geometry()

        # 监听主窗口激活状态
        if event.type() == QEvent.Type.ActivationChange:
            if obj == self.container.window():
                if self.container.window().isActiveWindow():
                    self.overlay.show()
                    self._sync_geometry()
                else:
                    self.overlay.hide()

        return False # 不拦截事件，继续传递

    def sync_now(self):
        """外部调用强制同步"""
        self._sync_geometry()

    def _sync_geometry(self):
        """核心：计算全局坐标并同步"""
        if not self.container.isVisible() or not self.container.window().isVisible():
            self.overlay.hide()
            return

        if self.container.window().windowState() & Qt.WindowState.WindowMinimized:
            self.overlay.hide()
            return
            
        if not self.overlay.isVisible():
            self.overlay.show()

        # 获取容器在屏幕上的绝对坐标
        global_pos = self.container.mapToGlobal(QPoint(0, 0))
        width = self.container.width()
        height = self.container.height()
        
        # 强制设置 overlay 位置
        self.overlay.setGeometry(global_pos.x(), global_pos.y(), width, height)
        # 确保置顶 (某些情况下会被遮挡)
        # self.overlay.raise_() 
        # 注意：频繁 raise_ 会导致主窗口失去焦点，这里依赖 WindowStaysOnTopHint
