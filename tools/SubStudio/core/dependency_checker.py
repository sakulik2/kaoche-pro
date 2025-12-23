
import os
import sys
import subprocess
import logging
import importlib.util
from PyQt6.QtWidgets import QMessageBox, QApplication

logger = logging.getLogger(__name__)

class DependencyChecker:
    @staticmethod
    def _is_nvidia_gpu_available():
        """检查 NVIDIA GPU 是否可用 (通过 nvidia-smi)。"""
        try:
            # 检查 nvidia-smi 是否存在且可运行
            subprocess.check_output(['nvidia-smi'], stderr=subprocess.STDOUT)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def _get_cuda_version():
        """Get CUDA version from nvcc or nvidia-smi."""
        version = None
        # Try nvcc first
        try:
            output = subprocess.check_output(['nvcc', '--version'], text=True, stderr=subprocess.STDOUT)
            for line in output.split('\n'):
                if "release" in line:
                    # Example: Cuda compilation tools, release 12.8, V12.8.93
                    parts = line.split(',')
                    for part in parts:
                        if "release" in part:
                            version = part.strip().split()[-1]
                            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        if version:
            return version

        # 回退使用 nvidia-smi
        try:
            output = subprocess.check_output(['nvidia-smi'], text=True, stderr=subprocess.STDOUT)
            for line in output.split('\n'):
                if "CUDA Version:" in line:
                    # Example: ... CUDA Version: 13.0 ...
                    version = line.split('CUDA Version:')[1].split('|')[0].strip()
                    break
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
            
        return version

    @staticmethod
    def check_sherpa_cuda(parent=None):
        """
        检查是否需要将 sherpa-onnx 升级到 CUDA 版本。
        如果依赖就绪（或已升级），返回 True；如果失败，返回 False。
        """
        if not DependencyChecker._is_nvidia_gpu_available():
            logger.info("No NVIDIA GPU detected. Skipping CUDA dependency check.")
            return True

        cuda_version = DependencyChecker._get_cuda_version()
        if not cuda_version:
            logger.info("NVIDIA GPU detected but no CUDA Toolkit version found. Skipping CUDA dependency upgrade.")
            return True
        
        logger.info(f"Detected CUDA Version: {cuda_version}")

        current_version = DependencyChecker._get_installed_version()
        if not current_version:
            logger.warning("sherpa-onnx not installed via pip.")
            return True

        # 目标版本条件：必须包含 '+cuda' 或者正是我们指定的版本
        # 注意：pip show 输出的 cuda 版本通常形如 '1.12.20+cuda'
        if "+cuda" in current_version:
             logger.info(f"sherpa-onnx is already CUDA enabled: {current_version}")
             return True
        
        # 判断是否需要升级
        # 如果用户有 GPU + CUDA Toolkit 但运行的是 CPU 版本 (无 +cuda)，提示升级
        logger.info(f"Detected CPU version of sherpa-onnx ({current_version}) on a CUDA-capable machine.")
        
        response = QMessageBox.question(
            parent,
            "检测到 CUDA 环境",
            f"检测到您的电脑支持 NVIDIA CUDA 加速 (CUDA {cuda_version})，但当前安装的是 sherpa-onnx CPU 版本。\n\n"
            "是否立即自动安装 GPU 加速版 (约 150MB)？\n"
            "安装将显著提升转写速度。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        if response != QMessageBox.StandardButton.Yes:
            return True

        # Perform upgrade
        progress = QMessageBox(parent)
        progress.setWindowTitle("正在配置 AI 组件")
        progress.setText("正在下载并安装 sherpa-onnx (CUDA 版)...\n请勿关闭程序。")
        progress.setStandardButtons(QMessageBox.StandardButton.NoButton)
        progress.show()
        QApplication.processEvents()

        try:
            # Uninstall current
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'uninstall', 'sherpa-onnx', '-y'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # 安装 CUDA 版本
            # 使用已验证的命令
            cmd = [
                sys.executable, '-m', 'pip', 'install', 
                'sherpa-onnx==1.12.20+cuda',
                '-f', 'https://k2-fsa.github.io/sherpa/onnx/cuda.html'
            ]
            
            # Using Popen to capture output if needed, but check_call is simpler
            subprocess.check_call(cmd)
            
            progress.close()
            QMessageBox.information(parent, "安装完成", "CUDA 组件安装成功！\n程序将继续运行。")
            return True

        except subprocess.CalledProcessError as e:
            progress.close()
            logger.error(f"Failed to install sherpa-onnx cuda: {e}")
            QMessageBox.critical(parent, "安装失败", f"自动安装失败，请手动检查网络或权限。\n错误: {e}")
            return False

    @staticmethod
    def _get_installed_version():
        """获取已安装的 sherpa-onnx 版本。"""
        try:
            result = subprocess.check_output(
                [sys.executable, '-m', 'pip', 'show', 'sherpa-onnx'],
                text=True
            )
            for line in result.split('\n'):
                if line.startswith('Version: '):
                    return line.split('Version: ')[1].strip()
        except subprocess.CalledProcessError:
            return None
        return None


