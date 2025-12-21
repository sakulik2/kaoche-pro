import logging
import logging.handlers
import os
import sys
import json
from datetime import datetime

def setup_logging(config_path=None):
    """
    配置全局日志 - 智能会话策略
    """
    # 1. 确保日志目录存在
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 2. 生成基于启动时刻的文件名 (log(YYYY-MM-DD).txt)
    # 由于 Handler 在此处初始化后会一直持有句柄，因此即便运行跨过零点，
    # 该会话的所有日志仍会保留在启动当天的文件中，满足“不割裂”需求。
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"log({date_str}).txt")
    
    # 默认配置
    log_level_str = "INFO"
    
    # 尝试从配置文件读取偏好级别
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                log_level_str = settings.get('advanced', {}).get('log_level', 'INFO')
        except Exception as e:
            print(f"Error loading settings for logging: {e}")

    # 转换日志级别
    level = getattr(logging, log_level_str.upper(), logging.INFO)
    
    # 3. 创建专业格式化器 (包含模块名以便区分工具)
    formatter = logging.Formatter(
        '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 获取根Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 清除旧的handlers，避免重复
    if root_logger.handlers:
        root_logger.handlers.clear()
        
    # 4. Console Handler (终端调试)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)
    
    # 5. File Handler (持久化记录 - 跨午夜不割裂)
    # 使用 RotatingFileHandler 仅为了防止单个文件极端过大 (10MB)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, 
            maxBytes=10*1024*1024, 
            backupCount=10, 
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging at {log_file}: {e}")
        
    logging.info(f"Log initialized. Session File: {log_file}")
