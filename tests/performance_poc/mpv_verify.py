import sys
import os

# --- 必须在 import mpv 之前设置 DLL 路径 ---
libmpv_path = r"D:\Program Files\Nosub-2.6.1-win64"
if os.path.exists(libmpv_path):
    if hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(libmpv_path)
    os.environ["PATH"] = libmpv_path + os.pathsep + os.environ["PATH"]

# Try to import mpv
try:
    import mpv
except ImportError:
    print("Error: 'python-mpv' is not installed in this environment.")
    print("Please run: pip install python-mpv")
    sys.exit(1)

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog
from PyQt6.QtCore import Qt

class MpvVerifyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MPV Backend Verification (Repaired)")
        self.resize(800, 600)
        
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        
        self.video_frame = QWidget()
        self.video_frame.setStyleSheet("background: black;")
        layout.addWidget(self.video_frame)
        
        self.status_label = QLabel("Initializing MPV...")
        layout.addWidget(self.status_label)
        
        self.btn = QPushButton("Test OSD / Subtitles")
        self.btn.clicked.connect(self._test_osd)
        layout.addWidget(self.btn)
        
        self.load_btn = QPushButton("Load Video File")
        self.load_btn.clicked.connect(self._load_video)
        layout.addWidget(self.load_btn)
        
        self.player = None
        
        # Delay initialization slightly to ensure winId is ready
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, self._init_mpv)

    def _init_mpv(self):
        try:
            wid = int(self.video_frame.winId())
            # 我们不再强制 sub-font-provider，而是尝试设置几个常见的 Windows 字体
            # 如果 libass 依然找不到提供者，这通常是 DLL 编译时未包含字体支持
            self.player = mpv.MPV(wid=str(wid),
                                 vo='gpu',
                                 osd_font='Microsoft YaHei', # 尝试中文系统最通用的字体
                                 osd_font_size=40,
                                 log_handler=print,
                                 loglevel='debug')
            self.status_label.setText("MPV Initialized. (If OSD still invisible, font provider missing in DLL)")
        except Exception as e:
            self.status_label.setText(f"MPV Init Failed: {str(e)}")
            print(f"Detailed Error: {e}")

    def _load_video(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Video", "", "Video (*.mp4 *.mkv)")
        if file and self.player:
            self.player.play(file)
            self.status_label.setText(f"Playing: {os.path.basename(file)}")

    def _test_osd(self):
        if self.player:
            # Test high-freq OSD update
            self.player.show_text("Testing Subtitle Sync... SUCCESS", duration=2000)
            self.player.command("show-text", "Raw Command Test (60FPS Sync Ready)", 3000)
            self.status_label.setText("OSD Commands Sent.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MpvVerifyWindow()
    win.show()
    sys.exit(app.exec())
