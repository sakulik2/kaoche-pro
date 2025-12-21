import os
import json
import logging
from pysubs2 import SSAStyle
from PyQt6.QtGui import QColor

logger = logging.getLogger(__name__)

class StylePresetManager:
    """
    样式预设管理器
    负责将 SSAStyle 序列化保存为 .json 文件，以及从文件加载
    """
    def __init__(self, base_dir=None):
        if base_dir:
            self.styles_root = base_dir
        else:
            # 默认：tools/SubStudio/styles
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.styles_root = os.path.join(current_dir, "styles")
            
        if not os.path.exists(self.styles_root):
            os.makedirs(self.styles_root)

    def get_presets(self):
        """获取所有可用预设名称 (文件名不含后缀)"""
        presets = []
        if not os.path.exists(self.styles_root):
            return presets
            
        for f in os.listdir(self.styles_root):
            if f.endswith(".json"):
                presets.append(os.path.splitext(f)[0])
        return sorted(presets)

    def save_preset(self, name, style: SSAStyle):
        """保存当前样式为预设"""
        try:
            # 序列化 SSAStyle
            # 注意: pysubs2 的 Color 是 pysubs2.Color 对象，需要转为 ASS string &HBBGGRR
            # 但 pysubs2 内部 color 存储为 PySubs2 Color object.
            # 简便起见，我们存储 dict
            
            data = {
                "fontname": style.fontname,
                "fontsize": style.fontsize,
                "primarycolor": self._color_to_ass(style.primarycolor),
                "secondarycolor": self._color_to_ass(style.secondarycolor),
                "outlinecolor": self._color_to_ass(style.outlinecolor),
                "backcolor": self._color_to_ass(style.backcolor),
                "bold": style.bold,
                "italic": style.italic,
                "underline": style.underline,
                "strikeout": style.strikeout,
                "scalex": style.scalex,
                "scaley": style.scaley,
                "spacing": style.spacing,
                "angle": style.angle,
                "borderstyle": style.borderstyle,
                "outline": style.outline,
                "shadow": style.shadow,
                "alignment": style.alignment,
                "marginl": style.marginl,
                "marginr": style.marginr,
                "marginv": style.marginv,
                "encoding": style.encoding
            }
            
            path = os.path.join(self.styles_root, f"{name}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            return True, f"已保存预设: {name}"
        except Exception as e:
            logger.error(f"Failed to save preset: {e}")
            return False, str(e)

    def load_preset(self, name):
        """加载预设为 SSAStyle 字典兼容对象 (用于 update)"""
        path = os.path.join(self.styles_root, f"{name}.json")
        if not os.path.exists(path):
            return None
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 转换颜色 string 回 pysubs2.Color (实际上 pysubs2 style 属性接受 Color 对象)
            # 但我们这里返回 data dict，让调用者去 update style
            from pysubs2 import Color
            
            # Helper to parse ASS hex string back to pysubs2.Color if needed
            # 其实 pysubs2.SSAStyle 属性赋值接受 int/tuple/Color
            # json 里的 &HBBGGRR 是 string。pysubs2 有 parse_style 逻辑吗？
            # 我们可以保留 string，pysubs2 不会自动转换 string -> Color。
            # 所以我们需要手动处理颜色字段
            
            for key in ["primarycolor", "secondarycolor", "outlinecolor", "backcolor"]:
                if key in data:
                    data[key] = self._ass_to_color(data[key])
                    
            return data
        except Exception as e:
            logger.error(f"Failed to load preset: {e}")
            return None

    def _color_to_ass(self, color_obj):
        """pysubs2.Color -> &HAABBGGRR String"""
        # pysubs2.Color 是 (r,g,b,a) 0-255
        # ASS needs &HAABBGGRR where AA is alpha (00-FF), BBGGRR
        # Actually pysubs2 stores color as object.
        # Let's verify what color_obj is. usually it is instance of pysubs2.Color
        if hasattr(color_obj, "r"):
            alpha = 255 - color_obj.a # pysubs2: 255=opaque, ASS: 00=opaque (Wait, pysubs2 follows ASS convention?)
            # pysubs2 Color: r,g,b,a (0-255). 
            # In pysubs2, alpha 0 is transparent, 255 opaque? 
            # No, pysubs2 docs say: "alpha (int): Transparency, 0-255 (0 is transparent, 255 is opaque)" -> This is standard RGBA.
            # ASS uses &H00 (opaque) to &HFF (transparent).
            # Wait, pysubs2 handles this conversion internally when saving to file.
            # But here we are serializing to JSON.
            # To be safe, let's just save the tuple (r,g,b,a) or dictionary.
            return {"r": color_obj.r, "g": color_obj.g, "b": color_obj.b, "a": color_obj.a}
        return color_obj

    def _ass_to_color(self, data):
        """Dict -> pysubs2.Color"""
        from pysubs2 import Color
        if isinstance(data, dict):
            return Color(data['r'], data['g'], data['b'], data['a'])
        return data
