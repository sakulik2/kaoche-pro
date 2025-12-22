import os
import logging
import subprocess
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QRadioButton, QSlider, QCheckBox, 
                             QGroupBox, QSpinBox, QFileDialog, QMessageBox, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, QThread

logger = logging.getLogger(__name__)

class ExportDialog(QDialog):
    """
    视频压制导出对话框
    参考主流压制工具 UI，支持 CRF/ABR 模式及硬件加速
    """
    def __init__(self, video_path, subtitle_store, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.store = subtitle_store
        self.setWindowTitle("视频压制导出")
        self.resize(550, 450)
        self.setup_ui()
        self.detect_hardware()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 1. 模式选择 (CRF / ABR)
        mode_layout = QHBoxLayout()
        mode_layout.addStretch()
        self.radio_crf = QRadioButton("CRF 恒定画质模式")
        self.radio_abr = QRadioButton("ABR 平均码率模式")
        self.radio_crf.setChecked(True)
        mode_layout.addWidget(self.radio_crf)
        mode_layout.addWidget(self.radio_abr)
        mode_layout.addStretch()
        layout.addLayout(mode_layout)

        # 2. 参数调整区
        self.param_group = QGroupBox("参数设置")
        self.param_layout = QVBoxLayout(self.param_group)

        # CRF 滑块
        self.crf_container = QWidget()
        crf_lay = QVBoxLayout(self.crf_container)
        crf_top = QHBoxLayout()
        self.lbl_crf_title = QLabel("CRF 画质级别 (越小质量越高):")
        self.spin_crf = QSpinBox()
        self.spin_crf.setRange(0, 51)
        self.spin_crf.setValue(19)
        crf_top.addWidget(self.lbl_crf_title)
        crf_top.addStretch()
        crf_top.addWidget(self.spin_crf)
        crf_lay.addLayout(crf_top)
        self.slider_crf = QSlider(Qt.Orientation.Horizontal)
        self.slider_crf.setRange(0, 51)
        self.slider_crf.setValue(19)
        self.slider_crf.valueChanged.connect(self.spin_crf.setValue)
        self.spin_crf.valueChanged.connect(self.slider_crf.setValue)
        crf_lay.addWidget(self.slider_crf)
        self.param_layout.addWidget(self.crf_container)

        # ABR 滑块 (默认隐藏)
        self.abr_container = QWidget()
        self.abr_container.hide()
        abr_lay = QVBoxLayout(self.abr_container)
        abr_top = QHBoxLayout()
        self.lbl_abr_title = QLabel("ABR 平均码率 (kbps):")
        self.spin_abr = QSpinBox()
        self.spin_abr.setRange(100, 50000)
        self.spin_abr.setValue(3600)
        abr_top.addWidget(self.lbl_abr_title)
        abr_top.addStretch()
        abr_top.addWidget(self.spin_abr)
        abr_lay.addLayout(abr_top)
        self.slider_abr = QSlider(Qt.Orientation.Horizontal)
        self.slider_abr.setRange(100, 10000) # 常用区间
        self.slider_abr.setValue(3600)
        self.slider_abr.valueChanged.connect(self.spin_abr.setValue)
        self.spin_abr.valueChanged.connect(self.slider_abr.setValue)
        abr_lay.addWidget(self.slider_abr)
        self.lbl_size_est = QLabel("预计文件大小: 计算中...")
        abr_lay.addWidget(self.lbl_size_est)
        self.param_layout.addWidget(self.abr_container)

        # Preset 滑块
        preset_lay = QVBoxLayout()
        preset_top = QHBoxLayout()
        preset_top.addWidget(QLabel("Preset 预设 (越小输出越快):"))
        self.spin_preset = QSpinBox()
        self.spin_preset.setRange(0, 9)
        self.spin_preset.setValue(4)
        preset_top.addStretch()
        preset_top.addWidget(self.spin_preset)
        preset_lay.addLayout(preset_top)
        self.slider_preset = QSlider(Qt.Orientation.Horizontal)
        self.slider_preset.setRange(0, 8)
        self.slider_preset.setValue(4)
        self.slider_preset.valueChanged.connect(self.spin_preset.setValue)
        self.spin_preset.valueChanged.connect(self.slider_preset.setValue)
        preset_lay.addWidget(self.slider_preset)
        self.param_layout.addLayout(preset_lay)

        layout.addWidget(self.param_group)

        # 3. 硬件加速区
        hw_group = QGroupBox("硬件加速设置")
        hw_lay = QVBoxLayout(hw_group)

        # 解码加速
        dec_lay = QHBoxLayout()
        self.check_hw_dec = QCheckBox("硬件解码")
        self.check_hw_dec.setChecked(True)
        dec_lay.addWidget(self.check_hw_dec)
        self.radio_dec_cuda = QRadioButton("CUDA")
        self.radio_dec_dx9 = QRadioButton("DX9")
        self.radio_dec_dx11 = QRadioButton("DX11")
        self.radio_dec_qsv = QRadioButton("Intel QSV")
        self.radio_dec_dx11.setChecked(True)
        dec_lay.addSpacing(10)
        dec_lay.addWidget(self.radio_dec_cuda)
        dec_lay.addWidget(self.radio_dec_dx9)
        dec_lay.addWidget(self.radio_dec_dx11)
        dec_lay.addWidget(self.radio_dec_qsv)
        dec_lay.addStretch()
        hw_lay.addLayout(dec_lay)

        # 编码加速
        enc_lay = QHBoxLayout()
        self.check_hw_enc = QCheckBox("硬件编码")
        self.check_hw_enc.setChecked(True)
        enc_lay.addWidget(self.check_hw_enc)
        self.radio_enc_cuda = QRadioButton("CUDA (NVENC)")
        self.radio_enc_qsv = QRadioButton("Intel QSV")
        self.radio_enc_cuda.setChecked(True)
        enc_lay.addSpacing(10)
        enc_lay.addWidget(self.radio_enc_cuda)
        enc_lay.addWidget(self.radio_enc_qsv)
        enc_lay.addStretch()
        hw_lay.addLayout(enc_lay)

        layout.addWidget(hw_group)

        # 4. 底部信息与按钮
        bottom_layout = QHBoxLayout()
        self.lbl_gpu = QLabel("正在检测显卡设备...")
        self.lbl_gpu.setStyleSheet("color: #6B7280; font-size: 11px;")
        bottom_layout.addWidget(self.lbl_gpu)
        bottom_layout.addStretch()
        
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        bottom_layout.addWidget(btn_cancel)
        
        self.btn_start = QPushButton("开始转码")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: white;
                font-weight: bold;
                padding: 6px 20px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2563EB; }
        """)
        self.btn_start.clicked.connect(self.on_start)
        bottom_layout.addWidget(self.btn_start)
        
        layout.addLayout(bottom_layout)

        # 事件绑定
        self.radio_crf.toggled.connect(self.toggle_mode)
        self.radio_abr.toggled.connect(self.toggle_mode)
        
        # 应用样式 (Dark/Light 继承主窗口)
        self.setStyleSheet("""
            QGroupBox { font-weight: bold; margin-top: 10px; }
            QRadioButton, QCheckBox { font-size: 12px; }
        """)

    def toggle_mode(self):
        if self.radio_crf.isChecked():
            self.crf_container.show()
            self.abr_container.hide()
        else:
            self.crf_container.hide()
            self.abr_container.show()

    def detect_hardware(self):
        """自动检测显卡与编码器支持"""
        try:
            # 1. 检测 GPU 型号
            cmd = "wmic path win32_VideoController get name"
            res = subprocess.check_output(cmd, shell=True).decode('gbk', errors='ignore')
            lines = [l.strip() for l in res.split('\n') if l.strip() and "Name" not in l]
            if lines:
                self.lbl_gpu.setText(f"检测到设备: {lines[0]}")
            
            # 2. 检测编码器支持
            res_enc = subprocess.check_output("ffmpeg -encoders", shell=True).decode()
            has_nvenc = "h264_nvenc" in res_enc
            has_qsv = "h264_qsv" in res_enc
            
            self.radio_enc_cuda.setEnabled(has_nvenc)
            self.radio_enc_qsv.setEnabled(has_qsv)
            
            if not has_nvenc and has_qsv:
                self.radio_enc_qsv.setChecked(True)
            elif not has_nvenc and not has_qsv:
                self.check_hw_enc.setChecked(False)
                self.check_hw_enc.setEnabled(False)
                
        except Exception as e:
            logger.error(f"Hardware detection failed: {e}")
            self.lbl_gpu.setText("无法识别显卡设备")

    def on_start(self):
        # 1. 选择保存路径
        save_path, _ = QFileDialog.getSaveFileName(
            self, "保存压制视频", 
            os.path.splitext(self.video_path)[0] + "_burn.mp4",
            "MP4 Video (*.mp4)"
        )
        if not save_path: return
        
        # 2. 收集参数
        params = {
            "mode": "crf" if self.radio_crf.isChecked() else "abr",
            "crf": self.spin_crf.value(),
            "bitrate": self.spin_abr.value(),
            "preset": self.spin_preset.value(),
            "hw_dec": self.check_hw_dec.isChecked(),
            "dec_type": self._get_dec_type(),
            "hw_enc": self.check_hw_enc.isChecked(),
            "enc_type": self._get_enc_type(),
            "input": self.video_path,
            "output": save_path
        }
        
        self.accept_params = params
        self.accept()

    def _get_dec_type(self):
        if self.radio_dec_cuda.isChecked(): return "cuda"
        if self.radio_dec_dx9.isChecked(): return "dxva2"
        if self.radio_dec_dx11.isChecked(): return "d3d11va"
        if self.radio_dec_qsv.isChecked(): return "qsv"
        return "auto"

    def _get_enc_type(self):
        if self.radio_enc_cuda.isChecked(): return "h264_nvenc"
        if self.radio_enc_qsv.isChecked(): return "h264_qsv"
        return "libx264"

from PyQt6.QtWidgets import QWidget # 为通配符导入补全 QWidget
