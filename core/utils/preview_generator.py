
"""
字幕预览生成器
负责将内部字幕数据转换为播放器可用的ASS格式
"""
import os
import time
import logging
import tempfile

logger = logging.getLogger(__name__)

class PreviewGenerator:
    """字幕预览生成类"""
    
    @staticmethod
    def generate_preview(subtitle_data, project_root):
        """
        生成临时ASS文件用于预览
        
        Args:
            subtitle_data: 内部字幕数据列表
            project_root: 项目根目录
            
        Returns:
            temp_path: 生成的临时文件路径 (失败返回 None)
        """
        try:
            import pysubs2
            
            # 使用 pysubs2 构建字幕对象
            subs = pysubs2.SSAFile()
            
            # 设置基本样式
            subs.info['PlayResX'] = '1280'
            subs.info['PlayResY'] = '720'
            
            style = pysubs2.SSAStyle(
                fontname="Arial", 
                fontsize=40, 
                primarycolor=pysubs2.Color(255, 255, 0), # 黄色
                backcolor=pysubs2.Color(0, 0, 0, 128),   # 半透明黑色背景
                outline=2,
                shadow=1
            )
            subs.styles["Default"] = style
            
            MAX_TIME = 36000000 # 10 hours
            
            for item in subtitle_data:
                target = item.get('target', {})
                text = target.get('text', '') if isinstance(target, dict) else str(target)
                source_start = item.get('source', {}).get('start', 0)
                source_end = item.get('source', {}).get('end', 0)
                
                # 转换时间（秒 -> 毫秒）
                s = float(source_start if source_start is not None else 0)
                e = float(source_end if source_end is not None else 0)
                
                start_ms = max(0, min(int(s * 1000), MAX_TIME))
                end_ms = max(0, min(int(e * 1000), MAX_TIME))
                
                event = pysubs2.SSAEvent(start=start_ms, end=end_ms, text=text)
                event.style = "Default"
                subs.events.append(event)
            
            # 确定临时文件路径
            temp_dir = os.path.join(project_root, 'temp')
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir, exist_ok=True)
                
            temp_path = os.path.join(temp_dir, 'preview_subtitles.ass')
            
            # 尝试删除旧文件
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                # 文件可能被占用，换个名字
                temp_path = os.path.join(temp_dir, f'preview_subtitles_{int(time.time())}.ass')
                
            # 保存
            subs.save(temp_path, encoding='utf-8')
            logger.info(f"生成预览字幕: {temp_path}")
            
            return temp_path
            
        except ImportError:
            logger.error("缺少 pysubs2 库")
            return None
        except Exception as e:
            logger.error(f"生成预览失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
