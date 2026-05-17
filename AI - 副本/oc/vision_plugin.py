# =============================================================================
# vision_plugin.py
# 通用AI助手视觉分析插件
# 与主程序完全解耦：删除本文件后主程序无报错，仅失去屏幕观察功能
#
# 核心特性
# --------
# 1. 子线程异步处理：截图、压缩、API请求全部在后台完成，不阻塞UI
# 2. 自动截图压缩：JPEG 50%质量压缩，减少API请求体积和延迟
# 3. 防重复触发：上一次请求未完成时再次点击会给出提示
# 4. 状态同步：分析期间自动切换到Thinking姿态，完成后恢复
# =============================================================================
import os
import base64
import pyautogui
from io import BytesIO
from PIL import Image
import requests
from PyQt5.QtCore import QThread, pyqtSignal

# =============================== 【可替换】核心配置区 ===============================
# 多模态大模型API配置
VISION_API_KEY = "YOUR_VISION_API_KEY_HERE"  # ⚠️ 你的多模态API密钥
VISION_ENDPOINT = "YOUR_VISION_ENDPOINT_ID_HERE"  # ⚠️ 你的多模态模型端点ID
VISION_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"  # 【可替换】API地址

# 截图配置
SCREENSHOT_QUALITY = 50  # 【可替换】JPEG压缩质量(1-100)，数值越小体积越小
REQUEST_TIMEOUT = 20  # 【可替换】API请求超时时间（秒）
# ==============================================================================

class VisionWorker(QThread):
    """
    视觉分析工作线程
    在子线程中完成截图 → 压缩 → API请求全过程
    结束后通过信号将结果返回主线程，避免UI阻塞
    """
    finished_signal = pyqtSignal(str)

    def run(self):
        try:
            # 1. 截取全屏
            img = pyautogui.screenshot()
            
            # 2. 压缩为JPEG格式（大幅减小体积）
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=SCREENSHOT_QUALITY)
            img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # 3. 构建API请求
            headers = {"Authorization": f"Bearer {VISION_API_KEY}"}
            payload = {
                "model": VISION_ENDPOINT,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "这是我现在的屏幕，请以你的人设进行吐槽或给出建议。回复字数限制在15个字内"  # 【可替换】视觉分析提示词
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{img_str}"}
                            }
                        ]
                    }
                ]
            }
            
            # 4. 发送请求并获取结果
            res = requests.post(VISION_URL, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
            reply = res.json()['choices'][0]['message']['content']
            self.finished_signal.emit(reply)
            
        except Exception as e:
            print(f"[Vision] 请求出错: {e}")
            self.finished_signal.emit("（视野受限，看不清你的屏幕...）")  # 【可替换】错误提示语


class VisionPlugin:
    def __init__(self, main_pet):
        self.pet = main_pet
        self._worker = None  # 持有线程引用，防止被GC提前回收

    def analyze_screen(self):
        """
        公开接口：启动屏幕视觉分析
        主程序右键菜单"观察屏幕"调用此方法
        """
        # 防止重复触发：如果上一次请求还在运行，直接给出提示
        if self._worker is not None and self._worker.isRunning():
            self.pet.start_speaking("（正在观察中，请稍等...）")  # 【可替换】重复请求提示语
            return
        
        # 切换到思考状态
        self.pet.is_thinking = True
        self.pet.update_pose("Thinking")        
        
        # 启动工作线程
        self._worker = VisionWorker()
        self._worker.finished_signal.connect(self._on_vision_done)
        self._worker.start()
        
    def _on_vision_done(self, text):
        """
        视觉分析完成回调
        重置思考状态，然后触发主程序的回复播放
        """
        self.pet.is_thinking = False
        self.pet._play_response(text)