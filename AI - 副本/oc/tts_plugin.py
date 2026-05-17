# =============================================================================
# tts_plugin.py
# 通用AI助手语音插件（适配GPT-SoVITS本地API）
# 与主程序完全解耦：删除本文件后主程序无报错，仅失去语音功能
#
# ------------------------
# 1. 使用127.0.0.1替代localhost
# 2. 请求超时改为120s（本机GPT-SoVITS推理约需40~60s，过短会截断连接）
# 3. 异步方案：文字气泡立刻显示，音频后台生成完成后自动播放
# 4. 说话状态与音频同步：播放期间持续刷新说话帧，播完自动恢复Normal
# =============================================================================
import os
import time
import wave
import threading
import requests
from PyQt5.QtCore import QTimer, QObject, pyqtSignal
from PyQt5.QtGui  import QPixmap

# =============================== 【可替换】核心配置区 ===============================
# 
# GPT-SoVITS API配置
TTS_API_URL   = "http://127.0.0.1:9880"  # 【可替换】本地API地址和端口
REQUEST_TIMEOUT_SEC = 120  # 【可替换】API请求超时时间（本机推理建议≥60s）

# 音频缓存配置
AUDIO_CACHE   = os.path.dirname(os.path.abspath(__file__))  # 【可替换】音频缓存目录
OC_PATH       = os.path.dirname(os.path.abspath(__file__))  # 【可替换】角色图片资源目录

# GPT-SoVITS参考音频配置（必须替换为你自己的）
REF_WAV_PATH  = r"YOUR_REFERENCE_AUDIO_PATH.wav"  # ⚠️ 你的角色参考音频绝对路径
REF_TEXT      = "你好，我是你的AI助手"  # 【可替换】⚠️参考音频对应的文本内容
REF_LANG      = "zh"  # 【可替换】⚠️参考音频语言（zh/ja/en）
TEXT_LANG     = "zh"  # 【可替换】合成文本语言（zh/ja/en）

# 动画配置
ANIM_MS = 160  # 【可替换】说话帧刷新间隔（毫秒），数值越小动画越快
# ==============================================================================

class TTSPlugin(QObject):
    """
    通用异步TTS语音插件
    执行时序
    --------
    主程序调用 speak(text)
        └─ 后台线程：向本地API发送请求（最多等待REQUEST_TIMEOUT_SEC秒）
              ├─ 成功：发送_sig_play信号，携带生成的音频路径
              │       └─ 主线程：启动说话帧动画 + 后台播放线程
              │                   播放结束：发送_sig_stop信号
              │                         └─ 主线程：停止动画，恢复Normal姿态
              └─ 失败/超时：静默打印日志，不影响主程序运行
    """
    _sig_play = pyqtSignal(str)   # 音频生成完成 -> 主线程启动播放和动画
    _sig_stop = pyqtSignal()      # 音频播放结束 -> 主线程恢复正常状态

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pw         = parent  # 主程序窗口实例
        self._is_playing = False   # 是否正在播放音频
        self._frame_idx  = 0       # 当前说话帧索引
        self._frame_dir  = 1       # 帧播放方向（1=正向，-1=反向）
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(ANIM_MS)
        self._anim_timer.timeout.connect(self._tick_frame)
        
        # 连接信号槽
        self._sig_play.connect(self._on_play)
        self._sig_stop.connect(self._on_stop)
        
        # 创建音频缓存目录
        os.makedirs(AUDIO_CACHE, exist_ok=True)

    # ------------------------------------------------------------------
    # 接口
    # ------------------------------------------------------------------
    def speak(self, text: str):
        """
        异步触发语音合成与播放
        文字气泡会立刻显示，音频后台生成完成后自动播放
        """
        if not text or not text.strip():
            return
        threading.Thread(
            target=self._worker,
            args=(text,),
            daemon=True,
            name="TTSWorker"
        ).start()

    # ------------------------------------------------------------------
    # 后台线程：音频生成
    # ------------------------------------------------------------------
    def _worker(self, text: str):
        """后台工作线程：负责调用API生成音频"""
        try:
            wav_path = self._generate_wav(text)
            if wav_path:
                self._sig_play.emit(wav_path)
        except Exception as e:
            print(f"[TTS] 工作线程异常: {e}")

    def _generate_wav(self, text: str):
        """
        调用GPT-SoVITS API生成WAV音频
        成功返回音频文件路径，失败返回None
        """
        try:
            payload = {
                "refer_wav_path":  REF_WAV_PATH,
                "prompt_text":     REF_TEXT,
                "prompt_language": REF_LANG,
                "text":            text,
                "text_language":   TEXT_LANG,
            }
            print(f"[TTS] 开始生成音频，等待服务响应（最多 {REQUEST_TIMEOUT_SEC}s）...")
            resp = requests.post(
                TTS_API_URL,
                json=payload,
                timeout=REQUEST_TIMEOUT_SEC
            )
            if resp.status_code != 200:
                print(f"[TTS] API返回异常状态码: {resp.status_code} | {resp.text[:200]}")
                return None
            
            # 用时间戳命名避免文件名冲突
            ts       = int(time.time() * 1000)
            wav_path = os.path.join(AUDIO_CACHE, f"tts_{ts}.wav")
            with open(wav_path, "wb") as f:
                f.write(resp.content)
            print(f"[TTS] 音频生成成功 -> {wav_path}")
            return wav_path
            
        except requests.exceptions.Timeout:
            print(f"[TTS] 超过 {REQUEST_TIMEOUT_SEC}s 未响应，跳过本次语音")
            return None
        except requests.exceptions.ConnectionError as e:
            print(f"[TTS] 无法连接到API服务 {TTS_API_URL}")
            print("[TTS] 请检查：① GPT-SoVITS的api-webui.bat是否已启动 ② 端口是否正确")
            return None
        except Exception as e:
            print(f"[TTS] 音频生成失败: {e}")
            return None

    # ------------------------------------------------------------------
    # 主线程槽函数
    # ------------------------------------------------------------------
    def _on_play(self, wav_path: str):
        """音频生成完成：启动说话帧动画 + 后台播放线程"""
        self._frame_idx  = 0
        self._frame_dir  = 1
        self._is_playing = True
        self._anim_timer.start()
        
        threading.Thread(
            target=self._play_then_stop,
            args=(wav_path,),
            daemon=True,
            name="TTSPlayer"
        ).start()

    def _on_stop(self):
        """音频播放结束：停止动画，恢复Normal姿态"""
        self._anim_timer.stop()
        self._restore_normal()

    # ------------------------------------------------------------------
    # 后台线程：音频播放
    # ------------------------------------------------------------------
    def _play_then_stop(self, wav_path: str):
        """播放音频，播放完成后发送停止信号"""
        try:
            self._play_wav(wav_path)
        except Exception as e:
            print(f"[TTS] 音频播放异常: {e}")
        finally:
            self._is_playing = False
            self._sig_stop.emit()

    def _play_wav(self, wav_path: str):
        """
        双播放器 fallback 方案
        优先使用pygame（跨平台），失败则使用Windows自带的winsound
        """
        played = False
        
        # 方案1：pygame.mixer（推荐，跨平台）
        if not played:
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(wav_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.05)
                pygame.mixer.music.unload()
                played = True
            except ImportError:
                print("[TTS] 未安装pygame，尝试使用winsound")
            except Exception as e:
                print(f"[TTS] pygame播放失败: {e}，尝试使用winsound")
        
        # 方案2：Windows winsound（仅Windows系统可用）
        if not played:
            try:
                import winsound
                duration = self._wav_duration(wav_path)
                winsound.PlaySound(
                    wav_path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NOWAIT
                )
                time.sleep(max(duration + 0.3, 0.5))
                winsound.PlaySound(None, winsound.SND_PURGE)
                played = True
            except Exception as e:
                print(f"[TTS] winsound播放失败: {e}")
        
        if not played:
            print("[TTS] 所有播放方案均失败，跳过本次音频")

    @staticmethod
    def _wav_duration(wav_path: str) -> float:
        """计算WAV音频文件的时长（秒）"""
        try:
            with wave.open(wav_path, 'rb') as wf:
                return wf.getnframes() / float(wf.getframerate())
        except Exception:
            return 3.0  # 计算失败时返回默认3秒

    # ------------------------------------------------------------------
    # 说话帧动画（主线程QTimer驱动）
    # ------------------------------------------------------------------
    def _tick_frame(self):
        """刷新说话动画帧"""
        pw = self._pw
        if pw is None:
            self._anim_timer.stop()
            return
        try:
            # 拖拽时暂停动画
            if getattr(pw, 'is_dragging', False):
                return
            
            # 【可替换】说话帧图片前缀，必须与主程序中的命名一致
            emo_lvl  = pw.get_emo_lvl()
            prefix   = ["3_speaking", "1_speaking", "2_speaking"][emo_lvl]
            img_path = os.path.join(OC_PATH, f"{prefix}{self._frame_idx + 1}.png")
            
            if os.path.exists(img_path):
                pw.role_label.setPixmap(QPixmap(img_path).scaled(260, 260))
            
            # 帧循环逻辑（0→1→2→1→0...）
            self._frame_idx += self._frame_dir
            if self._frame_idx >= 2 or self._frame_idx <= 0:
                self._frame_dir *= -1
                
        except Exception as e:
            print(f"[TTS] 帧更新异常: {e}")
            self._anim_timer.stop()

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def _restore_normal(self):
        """恢复到Normal姿态"""
        pw = self._pw
        if pw is None:
            return
        try:
            if not getattr(pw, 'is_dragging', False):
                pw.update_pose("Normal")
        except Exception as e:
            print(f"[TTS] 恢复Normal姿态失败: {e}")