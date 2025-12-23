# kaoche-pro

**一个烤肉工具箱**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

<img src="ui/assets/icon.png" width="100" height="100" />

**kaoche-pro** 是一款基于 AI 驱动的专业级字幕处理桌面应用。它采用现代化的插件架构，集成了质量分析 (LQA)、格式转换、智能听轴工作室 (SubStudio) 等全方位功能，旨在通过自动化与 AI 技术深度赋能字幕组、本地化团队及视频创作者。

## ✨ 核心功能模块

### 1. 🎙️ 字幕工作室 (SubStudio)
- **AI 智能听轴**: 深度集成 `faster-whisper` 与 `whisperx`，实现高精度语音转写与字符级强制对齐。
- **所见即所得 (WYSIWYG)**: 独创的“重力吸附”时间轴与实时视频预览，拖拽操作如丝般顺滑。
- **听音拍键 (Rapid Recording)**: 专为听译设计的 J/K 键拍打模式，快速生成时间轴，效率提升 300%。
- **语义重组引擎**: 针对 AI 生成的流水账文本，智能进行标点重组与断句修复。

### 2. ⚖️ 质量分析 (LQA)
基于大语言模型 (LLM) 的深度字幕质量评估系统。
- **AI 自动评分**: 多维度评估翻译质量（准确性、流畅度、术语一致性），并提供具体修改建议。
- **可视化审校**: 内置视频播放器，实时预览字幕叠加效果，点击表格行自动跳转视频进度。
- **双向同步**: 表格与视频播放进度实时双向同步，审校体验流畅无感。

### 3. 🔄 全能格式转换 (Converter)
无损、批量的字幕工程格式互转中心。
- **多格式支持**: 支持 SRT, ASS, VTT, Excel (XLSX), 纯文本 (TXT) 等格式的高效互转。
- **智能编码检测**: 内置高精度编码识别算法，自动处理 GBK/UTF-8 等各种编码，彻底告别乱码。
- **样式清洗**: 转换时可智能去除 ASS 样式代码，还原纯净文本以便进行 CAT (辅助翻译) 处理。

## 🚀 技术特性

- **插件化架构**: 极易扩展的 `Tools` 系统，支持功能模块的热插拔式开发与独立维护。
- **现代化 UI**: 基于 PyQt6 开发的高密度 Fusion 风格界面，支持深色/浅色主题一键切换。
- **AI 引擎集成**: 拥有独立的 **模型管理器 (Model Manager)**，支持 Whisper 模型的一键下载与管理；兼容 OpenAI/Anthropic/Google 等主流 LLM API。
- **本地化隐私**: 所有音频转写均在本地 GPU/CPU 运行，API Key 支持加密存储，保障数据安全。

## 📦 快速开始

### 环境依赖
- Python 3.10+
- FFmpeg (用于音视频处理，请确保已添加至系统路径)
- NVIDIA 显卡 (推荐，用于加速 AI 听轴)

### 安装步骤

1. **克隆仓库**:
   ```bash
   git clone https://github.com/sakulik2/kaoche-pro.git
   cd kaoche-pro
   ```

2. **创建虚拟环境 (推荐)**:
   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

3. **安装依赖**:
   ```bash
   pip install -r requirements.txt
   
   # 如需使用 GPU 加速 (推荐)，请安装 PyTorch CUDA 版本:
   # pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
   ```

4. **运行应用**:
   ```bash
   python main.py
   ```

## 📖 使用指南

1. **启动应用**: 运行后进入 **仪表盘 (Dashboard)**，这里列出了所有可用的工具卡片。
2. **全局配置**: 点击右上角或菜单栏的 **“设置”**。
    - 在 **“AI 引擎”** 中下载需要的 Whisper 模型 (如 `large-v3-turbo`)。
    - 在 **“LQA 配置”** 中填入 LLM API Key 以启用质量分析功能。
3. **开始工作**:
    - **SubStudio**: 拖入视频文件即可开始制作时间轴。
    - **Converters**: 拖入字幕或 Excel 文件即可批量转换。

## 📂 项目结构

```
kaoche-pro/
├── core/               # 核心框架 (通用组件、工具基类)
├── tools/              # 插件目录
│   ├── SubStudio/      # 专业字幕听轴工作室
│   ├── lqa/            # 字幕质量分析工具
│   └── converter/      # 格式转换器
├── ui/                 # 通用 UI 组件、启动器与资源文件
├── config/             # 配置文件存储
├── models/             # AI 模型仓库
├── main.py             # 程序入口
└── requirements.txt    # 项目依赖
```

## 📄 许可证

MIT License

---
*Built with ❤️ by Subtitle Professionals for Subtitle Professionals.*
