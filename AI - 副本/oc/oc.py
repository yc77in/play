import sys
import os
import json
import random
import time
import requests
import pyperclip
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# ================= 【可替换】插件导入模块 =================
# 说明：以下为可选功能插件，无对应插件时请注释掉导入语句和初始化代码
# 如需使用，请自行实现对应插件类
try:
    from tts_plugin import TTSPlugin
    from vision_plugin import VisionPlugin
    from memory_plugin import MemoryPlugin
    from music_plugin import MusicPlugin
except ImportError:
    print("提示：部分插件未找到，对应功能将不可用")
    TTSPlugin = VisionPlugin = MemoryPlugin = MusicPlugin = None

# ================= 核心配置模块 ⚠️  =================

API_KEY = "YOUR_API_KEY_HERE"                       # ⚠️ 你的大模型API密钥
ENDPOINT_ID = "YOUR_ENDPOINT_ID_HERE"  # ⚠️ 你的模型端点ID（如果有）
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"  # 【可替换】大模型API地址
# 本地文件路径（一般无需修改，如需自定义存储位置可调整）
PATH = os.path.dirname(os.path.abspath(__file__))# ⚠️ 你的oc.py在的位置
CONFIG_FILE = os.path.join(PATH, "config.json")  # 【可替换】配置文件名称
LOG_FILE = os.path.join(PATH, "chat_log.txt")       # 【可替换】聊天日志文件名称

# ================= 1. 记忆回溯面板模块 【可替换UI样式】 =================
class HistoryPanel(QDialog):
    def __init__(self, parent=None, log_path=""):
        super().__init__(parent)
        self.log_path = log_path
        self.setWindowTitle("记忆回溯")  # 【可替换】窗口标题
        self.setFixedSize(440, 500)  # 【可替换】窗口大小
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Dialog)
        layout = QVBoxLayout(self)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)
        self.refresh_list()

    def refresh_list(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not os.path.exists(self.log_path):
            return
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for line in reversed(lines):
                if not line.strip():
                    continue
                row = QFrame()
                row.setStyleSheet("QFrame { border-bottom: 1px solid #eee; }")  # 【可替换】分割线样式
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(4, 4, 4, 4)
                row_layout.setSpacing(6)
                text_scroll = QScrollArea()
                text_scroll.setFixedHeight(75)  # 【可替换】单条记录高度
                text_scroll.setWidgetResizable(True)
                text_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                text_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                text_scroll.setFrameShape(QFrame.NoFrame)
                text_scroll.setStyleSheet("""
                    QScrollArea          { background: transparent; border: none; }
                    QScrollBar:vertical  { width: 6px; background: #f0f0f0; border-radius: 3px; }
                    QScrollBar::handle:vertical { background: #ccc; border-radius: 3px; min-height: 20px; }
                """)  # 【可替换】滚动条样式
                lbl = QLabel(line.strip())
                lbl.setWordWrap(True)
                lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
                lbl.setStyleSheet("padding: 3px; background: transparent; font-size: 12px;")  # 【可替换】文字样式
                lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
                text_scroll.setWidget(lbl)
                btn = QPushButton("抹除")  # 【可替换】按钮文字
                btn.setFixedSize(50, 30)  # 【可替换】按钮大小
                btn.setStyleSheet(
                    "QPushButton { background:#ff4d4f; color:white; border-radius:3px; }"
                    "QPushButton:hover { background:#ff7875; }"
                )  # 【可替换】按钮样式
                btn.clicked.connect(lambda checked, c=line: self.delete_entry(c))
                row_layout.addWidget(text_scroll)
                row_layout.addWidget(btn, 0, Qt.AlignVCenter)
                self.list_layout.addWidget(row)
        except Exception:
            pass

    def delete_entry(self, content):
        lines = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(self.log_path, "w", encoding="utf-8") as f:
            for line in lines:
                if line.strip() != content.strip():
                    f.write(line)
        self.refresh_list()

# ================= 2. 随机小剧场弹窗模块 【可替换UI+逻辑】 =================
class EventWindow(QDialog):
    choice_made = pyqtSignal(str, str)
    def __init__(self, parent, scene, option_a, option_b):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedSize(300, 240)  # 【可替换】窗口大小
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 250, 250, 0.98); 
                border: 2px solid #ecdada; 
                border-radius: 15px;
            }
        """)  # 【可替换】背景样式
        f_layout = QVBoxLayout(self.frame)
        f_layout.setContentsMargins(15, 15, 15, 15)
        f_layout.setSpacing(10)
        self.label = QLabel(scene)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.label.setStyleSheet("color:#555; font-size:13px; padding:2px; border:none; background:transparent;")  # 【可替换】文字样式
        f_layout.addWidget(self.label)
        for opt in [option_a, option_b]:
            scroll = QScrollArea()
            scroll.setFixedHeight(50)  # 【可替换】选项按钮高度
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setStyleSheet("""
                QScrollArea { background: transparent; border: none; }
                QScrollBar:horizontal { height: 4px; background: #f0f0f0; }
                QScrollBar::handle:horizontal { background: #dcdcdc; border-radius: 2px; }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
            """)  # 【可替换】滚动条样式
            btn = QPushButton(opt)
            btn.setStyleSheet("""
                QPushButton {
                    background: #fff;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    padding: 8px 15px;
                    text-align: left;
                    min-width: 500px;
                    min-height: 30px;
                    color: #333;
                }
                QPushButton:hover { 
                    background: #fdf0f0; 
                    border: 1px solid #ecdada;
                }
                QPushButton:pressed {
                    background: #f9e4e4;
                }
            """)  # 【可替换】按钮样式
            btn.clicked.connect(lambda checked, o=opt: self.make_choice(o, scene))
            scroll.setWidget(btn)
            f_layout.addWidget(scroll)
        layout.addWidget(self.frame)

    def make_choice(self, text, scene):
        self.choice_made.emit(text, scene)
        self.accept()

# ================= 3. API工作线程模块 【可替换API格式】 =================
class ApiWorker(QThread):
    finished_signal = pyqtSignal(str)
    def __init__(self, payload):
        super().__init__()
        self.payload = payload

    def run(self):
        try:
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
            res = requests.post(BASE_URL, headers=headers, json=self.payload, timeout=15)
            # 【可替换】不同大模型的响应解析逻辑
            self.finished_signal.emit(res.json()['choices'][0]['message']['content'])
        except:
            self.finished_signal.emit("ERR_API")

# ================= 4. 情感分析工作线程模块 【可替换分析规则】 =================
class SentimentWorker(QThread):
    finished_signal = pyqtSignal(str, str, float)
    def __init__(self, text, weight=1.0):
        super().__init__()
        self.text = text
        self.weight = weight

    def run(self):
        # 【可替换】情感分析Prompt，可根据自己的人设调整
        prompt = f"""你是一个情感分析模型。对以下文本进行情感分析，
                    只返回JSON，禁止输出任何其他内容（包括代码块标记）。
                    文本：{self.text}
                    
                    返回格式（严格遵守）：
                    {{"score": 数字(-10到10), "type": "正面或负面或中性", "intensity": 数字(1到5)}}
                    
                    注意：
                    - score是情感分数，-10极度负面，+10极度正面，0中性
                    - type只能是"正面"、"负面"、"中性"三种
                    - intensity是情感强度，1最弱，5最强
                    - 必须识别讽刺、隐喻、反话、含蓄表达等复杂情感"""

        payload = {
            "model": ENDPOINT_ID,
            "messages": [{"role": "user", "content": prompt}]
        }
        try:
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
            res = requests.post(BASE_URL, headers=headers, json=payload, timeout=10)
            result = res.json()['choices'][0]['message']['content']
            self.finished_signal.emit(result, self.text, self.weight)
        except Exception as e:
            print(f"[情感分析] API请求失败: {e}")
            self.finished_signal.emit('{"score": 0, "type": "中性", "intensity": 1}', self.text, self.weight)

# ================= 5. 主程序核心模块 =================
class AIPet(QWidget):  # 【可替换】类名，改为你的角色名
    def __init__(self):
        super().__init__()
        # 【可替换】初始数值
        self.affinity = 0  # 初始好感度
        self.emotion_value = 15  # 初始心情值
        self.is_dragging = self.is_speaking = self.is_thinking = False
        self.current_text_full, self.current_text_idx = "", 0
        self.anim_frame, self.anim_dir = 0, 1
        self.old_clipboard, self.last_interact_time = "", time.time()
        self.last_user_msg = ""
        self.load_data()
        self.init_ui()
        self.init_timers()
        # 插件初始化（无插件时自动跳过）
        self.tts = TTSPlugin(self) if TTSPlugin else None
        self.vision = VisionPlugin(self) if VisionPlugin else None
        self.memory = MemoryPlugin() if MemoryPlugin else None
        self.music = MusicPlugin(self) if MusicPlugin else None
        self._speech_queue = []
        self._theater_active = False
        self._sentiment_workers = []

    # ── 配置加载模块 【可替换默认人设】 ──
    def load_data(self):
        # 【可替换】核心角色人设，后期可以通过菜单的核心设定功能直接改，下次启动直接覆盖这个设定⚠️⚠️
        self.system_prompt = (
            "你扮演【你的角色名】。【角色核心性格】。\n"
            "【绝对指令】：\n"
            "1. 严禁输出任何括号及括号内的动作描述。\n"
            "2. 说话极简，单次回复严禁超过25个字。\n"
            "3. 直接输出台词，不要有任何旁白或动作说明。"
        )
        # 【可替换】默认主人信息
        self.master_info = {"nickname": "主人", "relation": "朋友"}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                    self.affinity = d.get("affinity", 0)
                    self.emotion_value = d.get("emotion", 15)
                    self.system_prompt = d.get("prompt", self.system_prompt)
                    self.master_info = d.get("master", self.master_info)
            except:
                pass

    # ── UI初始化模块 【可替换所有UI参数】 ──
    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(350, 500)  # 【可替换】主窗口大小
        # 【可替换】角色图片位置和大小
        self.role_label = QLabel(self)
        self.role_label.setGeometry(45, 140, 260, 260)
        self.update_pose("Normal")
        # 【可替换】聊天气泡位置和大小
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setGeometry(25, 20, 300, 110)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setStyleSheet("QScrollArea{background:rgba(255,255,255,0.95);border:1px solid #ddd;border-radius:15px;}")  # 【可替换】气泡样式
        self.bubble_content = QLabel()
        self.bubble_content.setWordWrap(True)
        self.bubble_content.setStyleSheet("padding:8px;")  # 【可替换】气泡内边距
        self.scroll_area.setWidget(self.bubble_content)
        self.scroll_area.hide()
        # 【可替换】输入框位置和大小
        self.input_field = QLineEdit(self)
        self.input_field.setGeometry(75, 420, 200, 35)
        self.input_field.setStyleSheet("border-radius:15px; padding:5px; background:white;")  # 【可替换】输入框样式
        self.input_field.returnPressed.connect(self.handle_chat)
        self.show()

    # ── 工具方法模块 【可替换心情等级和图片映射】 ──
    def get_emo_lvl(self):
        # 【可替换】心情等级划分规则
        return 0 if self.emotion_value < 30 else (2 if self.emotion_value > 60 else 1)

    def update_pose(self, state_type):
        lvl = self.get_emo_lvl()
        # 【可替换】状态与图片的映射关系，必须与你准备的图片文件名一致
        mapping = {
            "Normal":   ["normal3.png",  "normal1.png",  "normal2.png"],
            "Thinking": ["thinking3.png","thinking1.png","thinking2.png"],
            "Drag":     ["drag3.png",    "drag1.png",    "drag2.png"]
        }
        path = os.path.join(PATH, mapping[state_type][lvl])
        if os.path.exists(path):
            self.role_label.setPixmap(QPixmap(path).scaled(260, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # ── AI调用模块 【可替换上下文提示】 ──
    def call_ai(self, msg, is_auto=False):
        self.is_thinking = True
        self.update_pose("Thinking")
        # 【可替换】不同心情下的提示语
        mood_hint = [
            "【当前心情极其糟糕：回复带有明显的攻击性。】",
            "【当前心情正常：保持角色原本的性格。】",
            "【当前心情非常愉悦：回复会变得稍微温柔。】"
        ][self.get_emo_lvl()]
        # 【可替换】传给AI的上下文信息
        ctx = (
            f"{self.system_prompt}\n"
            f"主人信息：{self.master_info}\n"
            f"当前状态：好感{self.affinity}, 心情值{self.emotion_value}\n"
            f"{mood_hint}"
        )
        # 【可替换】不同大模型的请求Payload格式
        payload = {
            "model": ENDPOINT_ID,
            "messages": [
                {"role": "system", "content": ctx},
                {"role": "user",   "content": msg}
            ]
        }
        self.worker = ApiWorker(payload)
        self.worker.finished_signal.connect(lambda t: self.on_reply(t, is_auto))
        self.worker.start()

    # ── AI回复处理模块 【可替换错误提示语】 ──
    def on_reply(self, text, is_auto):
        self.is_thinking = False
        if "ERR_" not in text:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M')}] AI: {text}\n")
            if self.is_speaking:
                self._speech_queue.append(text)
            else:
                self._play_response(text)
            try:
                if self.memory and self.last_user_msg:
                    self.memory.save_memory(self.last_user_msg, text)
            except Exception as e:
                print(f"记忆存储失败: {e}")
        else:
            # 【可替换】API错误提示语
            error_msg = "（信号受到干扰...）"
            if self.is_speaking:
                self._speech_queue.append(error_msg)
            else:
                self._play_response(error_msg)

    def _play_response(self, text):
        self.start_speaking(text)
        try:
            if self.tts:
                self.tts.speak(text)
        except Exception as e:
            print(f"语音播放出错: {e}")

    def start_speaking(self, text):
        self.current_text_full, self.current_text_idx, self.is_speaking = text, 0, True
        self.scroll_area.show()
        self.type_timer.start(50)  # 【可替换】打字速度（毫秒/字）

    def type_tick(self):
        if self.is_dragging:
            return
        if self.current_text_idx < len(self.current_text_full):
            self.current_text_idx += 1
            self.bubble_content.setText(self.current_text_full[:self.current_text_idx])
            # 【可替换】说话状态的图片前缀
            p = ["3_speaking", "1_speaking", "2_speaking"][self.get_emo_lvl()]
            path = os.path.join(PATH, f"{p}{self.anim_frame + 1}.png")
            if os.path.exists(path):
                self.role_label.setPixmap(QPixmap(path).scaled(260, 260))
            self.anim_frame += self.anim_dir
            if self.anim_frame >= 2 or self.anim_frame <= 0:
                self.anim_dir *= -1
        else:
            self.type_timer.stop()
            self.is_speaking = False
            self.update_pose("Normal")
            if self._speech_queue:
                next_text = self._speech_queue.pop(0)
                QTimer.singleShot(600, lambda t=next_text: self._play_response(t))
            else:
                QTimer.singleShot(8000, self.scroll_area.hide)  # 【可替换】气泡自动隐藏时间

    # ── 情感分析系统 【可替换计算规则和专属关键词】 ──
    def analyze_sentiment(self, text, weight=1.0):
        worker = SentimentWorker(text, weight)
        worker.finished_signal.connect(self._on_sentiment_result)
        self._sentiment_workers.append(worker)
        worker.finished.connect(lambda: self._sentiment_workers.remove(worker) 
                                if worker in self._sentiment_workers else None)
        worker.start()

    def _on_sentiment_result(self, json_str, original_text, weight):
        try:
            clean = json_str.strip().replace('```json', '').replace('```', '').strip()
            data = json.loads(clean)
            score     = float(data.get("score", 0))
            emo_type  = data.get("type", "中性")
            intensity = float(data.get("intensity", 1))
        except Exception as e:
            print(f"[情感分析] JSON解析失败: {e}，原始响应: {json_str}")
            score, emo_type, intensity = 0.0, "中性", 1.0
        print(f"[情感分析] 原文:「{original_text[:20]}」 | 分数:{score} | 类型:{emo_type} | 强度:{intensity} | 权重:{weight}")

        # 【可替换】基础情感和好感变化系数
        emotion_change  = score * intensity * 0.5 * weight
        affinity_change = score * intensity * 0.3 * weight

        # 【可替换】极端情感额外调整规则
        if emo_type == "负面" and intensity >= 4:
            affinity_change -= 5 * weight
            print(f"[极端负面] 好感额外 -{5 * weight:.1f}")
        elif emo_type == "正面" and intensity >= 4:
            affinity_change += 3 * weight
            print(f"[极端正面] 好感额外 +{3 * weight:.1f}")

        # 【可替换】角色专属规则，根据你的人设修改关键词和变化量
        char_e, char_a = self._check_character_rules(original_text)
        emotion_change  += char_e
        affinity_change += char_a

        # 【可替换】字数影响规则
        if weight == 1.0:
            text_len = len(original_text)
            if text_len <= 3:
                emotion_change -= 5
                print("[字数判定] 敷衍回复（≤3字）：心情额外 -5")
            elif text_len > 20:
                emotion_change += 3
                print("[字数判定] 认真交流（>20字）：心情额外 +3")
            else:
                rand_val = random.uniform(-1, 1)
                emotion_change += rand_val
                print(f"[字数判定] 普通字数：心情随机波动 {rand_val:+.2f}")

        print(f"[变化汇总] 心情变化:{emotion_change:+.2f}，好感变化:{affinity_change:+.2f}")
        self.emotion_value = max(0, min(100, int(round(self.emotion_value + emotion_change))))
        self.affinity      = max(0, min(100, int(round(self.affinity      + affinity_change))))
        print(f"[更新结果] 心情值:{self.emotion_value}  好感度:{self.affinity}")

    def _check_character_rules(self, text):
        """【可替换】角色专属情感规则，返回(心情变化, 好感变化)"""
        emotion_delta  = 0
        affinity_delta = 0
        # 示例规则：根据你的角色性格修改关键词和数值
        if any(kw in text for kw in ["讨厌", "滚", "烦"]):
            emotion_delta  -= 10
            affinity_delta -= 8
            print("[角色规则] 负面词汇触发：心情-10，好感-8")
        if any(kw in text for kw in ["喜欢", "爱你", "抱抱"]):
            emotion_delta  += 10
            affinity_delta += 8
            print("[角色规则] 正面词汇触发：心情+10，好感+8")
        return emotion_delta, affinity_delta

    # ── 聊天处理模块 ──
    def handle_chat(self):
        msg = self.input_field.text().strip()
        self.input_field.clear()
        if msg:
            self.last_interact_time = time.time()
            self.last_user_msg = msg
            self.analyze_sentiment(msg, weight=1.0)
            self.call_ai(msg)

    # ── 随机小剧场模块 【可替换小剧场Prompt】 ──
    def trigger_random_theater(self):
        if self._theater_active:
            return
        self._theater_active = True
        # 【可替换】小剧场生成Prompt，根据你的角色人设调整
        prompt = (
            "指令：构思一个你（你的角色名）和我（主人）的日常小片段。 "
            "【关键要求】：禁止重复情节。请从以下维度随机选择一个：\n"
            "1. 意外事件（如：打翻水杯、迷路、下雨）。\n"
            "2. 日常互动（如：一起吃饭、看电影、散步）。\n"
            "3. 趣味对话（如：猜谜语、讲冷笑话、吐槽）。\n"
            "请严格按格式返回：情景描述|选项A|选项B。 "
            "保持你的角色人设不变。"
        )
        self.ew_worker = ApiWorker(
            {"model": ENDPOINT_ID, "messages": [{"role": "user", "content": prompt}]}
        )
        self.ew_worker.finished_signal.connect(self.show_event_window)
        self.ew_worker.start()

    def show_event_window(self, raw_text):
        try:
            print(f"小剧场回复：{raw_text}")
            parts = raw_text.split('|')
            if len(parts) >= 3:
                scene = parts[0].strip()
                opt_a = parts[1].strip()
                opt_b = parts[2].strip()
                self.ew = EventWindow(self, scene, opt_a, opt_b)
                self.ew.choice_made.connect(self.handle_theater_choice)
                self.ew.finished.connect(lambda _: setattr(self, '_theater_active', False))
                self.ew.show()
            else:
                print("AI回复格式错误，未检测到足够的分隔符")
                self._theater_active = False
        except Exception as e:
            print(f"触发小剧场出错: {e}")
            self._theater_active = False

    def handle_theater_choice(self, choice, scene):
        print(f"[剧场选择] 用户选择:「{choice}」，权重:1.5")
        self.analyze_sentiment(choice, weight=1.5)
        # 【可替换】小剧场回复提示
        self.call_ai(
            f"【互动场景：{scene}，主人选了：{choice}】请根据场景发表评论。回复字数限制在20字以内。",
            is_auto=True
        )

    # ── 剪贴板监听模块 【可替换触发提示】 ──
    def check_clip(self):
        c = pyperclip.paste().strip()
        if c and c != self.old_clipboard and not self.is_speaking and not self.is_thinking:
            self.old_clipboard = c
            # 【可替换】剪贴板内容触发的提示语
            self.call_ai(f"【主人复制了内容：{c[:30]}，请对此发表看法。回复字数限制在15字以内。】", is_auto=True)

    # ── 定时器模块 【可替换时间间隔】 ──
    def init_timers(self):
        self.type_timer = QTimer()
        self.type_timer.timeout.connect(self.type_tick)
        self.theater_timer = QTimer()
        self.theater_timer.timeout.connect(self.trigger_random_theater)
        self.theater_timer.start(18000000)  # 【可替换】小剧场触发间隔（毫秒），默认5小时
        self.clip_timer = QTimer()
        self.clip_timer.timeout.connect(self.check_clip)
        self.clip_timer.start(3000)  # 【可替换】剪贴板检查间隔（毫秒），默认3秒
        self.save_timer = QTimer()
        self.save_timer.timeout.connect(self.save_cfg)
        self.save_timer.start(30000)  # 【可替换】自动保存间隔（毫秒），默认30秒

    # ── 右键菜单模块 【可替换菜单文字】 ──
    def contextMenuEvent(self, event):
        m = QMenu(self)
        m.addAction(f"❤️ 好感: {self.affinity} | 🎭 情绪: {self.emotion_value}")  # 【可替换】状态显示文字
        m.addSeparator()
        a_hist   = m.addAction("📜 记忆回溯")  # 【可替换】菜单文字
        a_prof   = m.addAction("👤 主人档案")  # 【可替换】菜单文字
        a_set    = m.addAction("🧠 核心设定")  # 【可替换】菜单文字
        a_vision = m.addAction("👁️ 观察屏幕")  # 【可替换】菜单文字
        m.addSeparator()
        a_quit = m.addAction("🚪 退出")  # 【可替换】菜单文字
        act = m.exec_(self.mapToGlobal(event.pos()))
        if act == a_quit:
            self.save_cfg()
            qApp.quit()
        elif act == a_hist:
            self.hw = HistoryPanel(self, LOG_FILE)
            self.hw.show()
        elif act == a_prof:
            self.edit_p()
        elif act == a_set:
            self.edit_s()
        elif act == a_vision:
            if self.vision:
                self.vision.analyze_screen()
            else:
                self.start_speaking("（视觉插件尚未加载...）")  # 【可替换】插件未加载提示

    def edit_p(self):
        n, ok1 = QInputDialog.getText(self, "档案", "修改昵称:", text=self.master_info.get("nickname", ""))
        if ok1:
            r, ok2 = QInputDialog.getText(self, "档案", "修改关系:", text=self.master_info.get("relation", ""))
            if ok2:
                self.master_info = {"nickname": n, "relation": r}
                self.save_cfg()

    def edit_s(self):
        s, ok = QInputDialog.getMultiLineText(self, "设定", "修改性格:", self.system_prompt)
        if ok:
            self.system_prompt = s
            self.save_cfg()

    def save_cfg(self):
        try:
            d = {
                "affinity":  self.affinity,
                "emotion":   self.emotion_value,
                "prompt":    self.system_prompt,
                "master":    self.master_info
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(d, f, ensure_ascii=False)
        except:
            pass

    # ── 鼠标事件模块 ──
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.is_dragging = True
            self.drag_pos = e.globalPos() - self.pos()
            self.update_pose("Drag")

    def mouseMoveEvent(self, e):
        if self.is_dragging:
            self.move(e.globalPos() - self.drag_pos)

    def mouseReleaseEvent(self, e):
        self.is_dragging = False
        self.update_pose("Normal")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    pet = AIPet()  # 【可替换】与类名保持一致
    sys.exit(app.exec_())