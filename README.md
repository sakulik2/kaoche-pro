<div align="center">
  <img src="ui/assets/icon.png" width="128" height="128" alt="Kaoche Pro Icon">
  <h1>kaoche-pro</h1>
  <p><strong>专业的视频字幕质量评估与对齐工具</strong></p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.8%2B-blue.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
    <img src="https://img.shields.io/badge/Platform-Windows-lightgrey.svg" alt="Platform">
  </p>
</div>

**kaoche-pro** 是一款专为字幕组和本地化人员打造的桌面增强工具。它整合了先进的 AI 模型（如 OpenAI, Gemini, Claude）进行 LQA（语言质量评估）分析，并提供强大的时间轴自动对齐、项目管理及沉浸式视频预览功能，极大提升字幕校对效率。

## ✨ 核心功能

### 🤖 AI 智能 LQA 分析
*   **多维度评估**：自动检测翻译错误、风格不符、术语不一致等问题。
*   **深度反馈**：提供详细的评分、问题分类（严重性）及具体的修改建议。
*   **灵活性**：支持自定义 Prompt 模板，完美适配不同类型的字幕项目。

### ⏱️ 智能时间轴对齐
*   **高效算法**：基于文本内容的智能对齐算法，快速纠正双语字幕错位。
*   **多种模式**：支持“以原文为准”、“以译文为准”或“自动锚点”模式，灵活应对各种时间轴问题。

### 🎬 沉浸式视频预览
*   **全格式支持**：内置 VLC 播放器内核，支持 `.mp4`, `.mkv`, `.avi` 等几乎所有视频格式。
*   **实时字幕挂载**：
    *   **完美支持 ASS**：通过 input-slave 机制完美渲染 `.ass` 特效字幕及常规 `.srt` 字幕。
    *   **同步预览**：修正后的字幕实时在视频上预览，所见即所得。
*   **精准定位**：点击字幕行即可快速跳转视频，配合波形/进度条实现帧级定位。

### 📁 项目管理与导出
*   **项目文件 (.kcp)**：支持保存/加载项目状态，随时恢复工作进度。
*   **多格式导入**：支持 `.srt`, `.ass`, `.vtt` 字幕，纯文本 `.txt`，及 Excel `.xlsx` 双语对照表。
*   **专业导出**：LQA 分析报告 (JSON/CSV/Excel)、修正后的字幕文件（原文/译文/建议）。

### 🛡️ 隐私与安全
*   **配置加密**：支持主密码保护，对 API Key 进行 AES 加密存储。
*   **本地优先**：敏感配置均保留在本地，打包与导出时不包含个人隐私数据。

## 📦 安装指南

### 前置要求
*   **操作系统**: Windows 10/11
*   **Python**: 3.8 或更高版本
*   **VLC Media Player**: 必须安装（软件会自动检测路径，用于视频播放）

### 1. 克隆项目
```bash
git clone https://github.com/sakulik2/kaoche-pro.git
cd kaoche-pro
```

### 2. 创建虚拟环境 (推荐)
```bash
python -m venv venv
# 激活虚拟环境:
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (CMD):
.\venv\Scripts\activate.bat
```

### 3. 安装依赖
```bash
pip install -r requirements.txt
```

> **注意**: 首次运行时，如果是 Python 3.8+ 环境，程序会自动配置 VLC 的 DLL 路径。

## 🚀 快速开始

### 运行源码
在虚拟环境激活状态下：
```bash
python main.py
```

### 使用流程
1.  **配置 API**：首次启动进入“设置”，配置 LLM 提供商（OpenAI, Gemini 等）及 API Key。
2.  **加载文件**：
    *   点击 **“打开项目”** 或直接拖拽 `.kcp` 文件。
    *   或者分别加载视频、原文字幕和译文字幕。
3.  **开始分析**：点击工具栏 **“🚀 LQA 分析”**，AI 将自动评估每一句字幕。
4.  **复查与修正**：
    *   双击表格单元格直接编辑。
    *   右键菜单进行“单句复查”或“应用建议”。
    *   在视频播放器中实时查看修改效果。
5.  **导出成果**：通过 **“导出”** 菜单生成最终字幕或质量报告。

## 🛠️ 打包指南 (Build)

如果你想生成独立的 `.exe` 可执行文件以便分发：

1.  **安装打包工具**
    ```bash
    pip install pyinstaller Pillow
    ```
    *(注：Pillow 用于自动处理图标转换)*

2.  **执行打包命令**
    ```bash
    pyinstaller kaoche-pro.spec --clean
    ```

3.  **获取程序**
    打包完成后，可执行文件将生成在 `dist/kaoche-pro/` 目录下。

> **提示**: `kaoche-pro.spec` 已配置为**排除**你的个人配置文件，因此发布给他人是安全的。用户在使用时只需安装 VLC 即可。

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。

---
**Authors**: sakulik
