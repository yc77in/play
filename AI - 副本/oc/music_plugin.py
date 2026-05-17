# =============================================================================
# music_plugin.py
# 通用AI助手媒体音乐嗅探插件（仅支持Windows系统）
# 与主程序完全解耦：删除本文件后主程序无报错，仅失去音乐评论功能
#
# 核心特性
# --------
# 1. 双路媒体检测：优先使用Windows Media Session API，失败则用窗口标题解析
# 2. 后台常驻运行：独立线程监测，不阻塞主程序UI
# 3. 防重复触发：同一首歌只评论一次，需连续播放指定时长才触发
# 4. 状态同步：API请求期间自动切换到Thinking立绘，完成后恢复
# 5. 多平台适配：支持网易云、QQ音乐、Spotify、YouTube等主流媒体软件
# =============================================================================
import os
import re
import time
import threading
import requests
from PyQt5.QtCore import QObject, pyqtSignal, Qt

# =============================== 【可替换】核心配置区 ===============================
#
# 大模型API配置
MUSIC_API_KEY      = "YOUR_MUSIC_API_KEY_HERE"  # ⚠️ 你的大模型API密钥
MUSIC_ENDPOINT_ID  = "YOUR_MUSIC_ENDPOINT_ID_HERE"  # ⚠️ 你的大模型端点ID
MUSIC_API_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"  # 【可替换】API地址

# 项目路径（一般无需修改）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 嗅探参数
POLL_INTERVAL = 5.0   # 【可替换】媒体状态轮询间隔（秒）
MIN_PLAY_SEC  = 8.0   # 【可替换】曲目需连续播放超过此秒数才触发评论
REQUEST_TIMEOUT = 15  # 【可替换】API请求超时时间（秒）

# 【可替换】角色人设固定提示词（根据你的角色修改）
CHARACTER_PROMPT = (
    "你扮演【你的角色名】。【角色核心性格描述】。"
    "说话风格：【角色说话风格，如：简洁、毒舌、温柔等】。"
)

# 【可替换】窗口标题解析规则（可添加更多媒体平台）
# 格式：(正则表达式, 歌曲名分组索引, 艺术家名分组索引)
TITLE_RULES = [
    (r"^(.+?)\s*[-–]\s*(.+?)\s*[-–]\s*网易云音乐$", 1, 2),
    (r"^(.+?)\s*[-–]\s*(.+?)\s*[-–]\s*QQ音乐$",    1, 2),
    (r"^(.+?)\s*[-–]\s*(.+?)\s*[-–]\s*Spotify$",   1, 2),
    (r"^(.+?)\s*[-–]\s*YouTube",                    1, None),
    (r"^(.+?)\s*[-–]\s*Windows Media Player$",      1, None),
    (r"^(.+?)\s*[-–]\s*(.+)$",                      1, 2),
]

# 【可替换】需要跳过的窗口标题关键词
SKIP_KEYWORDS = [
    "Google Chrome", "Microsoft Edge", "Firefox", "Explorer",
    "Visual Studio", "PyCharm", "任务管理器", "设置",
    "新标签页", "New Tab", "about:blank",
]
# ==============================================================================

class MusicPlugin(QObject):
    # 线程安全信号（后台线程→主线程通信）
    _sig_show_reaction = pyqtSignal(str)   # 显示听歌感想
    _sig_set_thinking  = pyqtSignal(bool)  # 切换思考状态

    def __init__(self, pet):
        super().__init__()
        self.pet            = pet  # 主程序窗口实例
        self._running       = True  # 插件运行状态
        self._current_track = None  # 当前播放的曲目
        self._track_since   = 0.0   # 当前曲目开始播放的时间
        self._reacted_to    = set()  # 已经评论过的曲目集合

        # 连接信号到主线程槽（使用QueuedConnection保证线程安全）
        self._sig_show_reaction.connect(self._slot_show_reaction, Qt.QueuedConnection)
        self._sig_set_thinking.connect(self._slot_set_thinking,   Qt.QueuedConnection)

        # 检测winsdk可用性
        self._has_winsdk = self._check_winsdk()

        # 启动后台监测线程
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="MusicSniffer"
        )
        self._thread.start()
        print(f"[音乐插件] 已启动（检测方式：{'winsdk' if self._has_winsdk else '窗口标题解析'}）")

    # ── 主线程槽函数（UI操作必须在主线程执行） ──
    def _slot_set_thinking(self, state: bool):
        """切换思考状态和对应立绘"""
        self.pet.is_thinking = state
        if state:
            self.pet.update_pose("Thinking")

    def _slot_show_reaction(self, reaction_text: str):
        """显示听歌感想，触发气泡和TTS"""
        # 先重置思考状态
        self.pet.is_thinking = False
        
        # 如果正在说话或思考中，静默跳过本次播报
        if self.pet.is_speaking or self.pet.is_thinking:
            return
        
        # 复用主程序的回复播放逻辑，保证行为一致
        try:
            self.pet._play_response(reaction_text)
        except Exception as e:
            print(f"[音乐插件] 播报失败（不影响插件运行）: {e}")

    # ── 后台监测主循环 ──
    def _monitor_loop(self):
        while self._running:
            try:
                title, artist = self._get_current_media()
                if title:
                    track_key = f"{title}|{artist or ''}"
                    
                    # 检测到新曲目
                    if track_key != self._current_track:
                        self._current_track = track_key
                        self._track_since   = time.time()
                        print(f"[音乐插件] 检测到新曲目: 《{title}》{'- ' + artist if artist else ''}")
                    
                    # 连续播放超过指定时长且未评论过，触发感想生成
                    elif (
                        track_key not in self._reacted_to
                        and time.time() - self._track_since >= MIN_PLAY_SEC
                    ):
                        self._reacted_to.add(track_key)
                        self._generate_and_emit_reaction(title, artist)
                        
            except Exception as e:
                print(f"[音乐插件] 监测异常（已忽略）: {e}")
            
            time.sleep(POLL_INTERVAL)

    # ── 媒体信息获取（双路检测） ──
    def _get_current_media(self):
        """获取当前播放的媒体信息，优先使用winsdk"""
        if self._has_winsdk:
            result = self._get_media_via_winsdk()
            if result[0]:
                return result
        return self._get_media_via_win32()

    def _check_winsdk(self) -> bool:
        """检查winsdk是否可用"""
        try:
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager
            )
            return True
        except ImportError:
            print("[音乐插件] winsdk未安装，将使用窗口标题解析作为备用方案")
            return False

    def _get_media_via_winsdk(self):
        """通过Windows Media Session API获取媒体信息（最可靠）"""
        try:
            import asyncio
            from winsdk.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as MediaManager
            )

            async def _fetch():
                manager = await MediaManager.request_async()
                session = manager.get_current_session()
                if session is None:
                    return None, None
                info = await session.try_get_media_properties_async()
                if info is None:
                    return None, None
                title  = (info.title  or "").strip() or None
                artist = (info.artist or "").strip() or None
                return title, artist

            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_fetch())
            finally:
                loop.close()
                
        except Exception as e:
            print(f"[音乐插件] winsdk获取媒体信息失败: {e}")
            return None, None

    def _get_media_via_win32(self):
        """通过解析窗口标题获取媒体信息（备用方案）"""
        try:
            import win32gui
            titles = []

            def _enum_cb(hwnd, result):
                if win32gui.IsWindowVisible(hwnd):
                    t = win32gui.GetWindowText(hwnd)
                    if t and len(t) > 3:
                        result.append(t)

            win32gui.EnumWindows(_enum_cb, titles)

            for title_str in titles:
                # 跳过包含关键词的窗口（除非是YouTube）
                if any(kw in title_str for kw in SKIP_KEYWORDS):
                    if "YouTube" not in title_str:
                        continue
                
                # 匹配窗口标题规则
                for pattern, t_idx, a_idx in TITLE_RULES:
                    m = re.match(pattern, title_str)
                    if m:
                        track  = m.group(t_idx).strip()
                        artist = m.group(a_idx).strip() if a_idx and len(m.groups()) >= a_idx else None
                        if track and len(track) > 1:
                            return track, artist
            
            return None, None
            
        except ImportError:
            print("[音乐插件] pywin32未安装，窗口标题解析不可用")
            return None, None
        except Exception as e:
            print(f"[音乐插件] 窗口标题解析失败: {e}")
            return None, None

    # ── API调用与感想生成 ──
    def _generate_and_emit_reaction(self, title: str, artist: str | None):
        """生成听歌感想并触发显示"""
        # 切换到思考状态
        self._sig_set_thinking.emit(True)

        artist_str  = f"- {artist}" if artist else ""
        # 【可替换】听歌感想生成提示词
        user_prompt = (
            f"现在正在播放：《{title}》{artist_str}。\n"
            "请你以你的人设，针对这首歌发表简短的听歌感想或评论。"
            "要求：保持角色人设，语言简洁，不超过20字。"
        )

        reaction = self._call_lite_api(user_prompt)
        if reaction:
            print(f"[音乐插件] 生成感想: {reaction}")
            self._sig_show_reaction.emit(reaction)
        else:
            print("[音乐插件] API返回为空，跳过本次播报")
            # API失败时必须重置思考状态，否则立绘会永久卡在Thinking
            self._sig_set_thinking.emit(False)

    def _call_lite_api(self, user_msg: str) -> str | None:
        """调用大模型API生成回复"""
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {MUSIC_API_KEY}",
        }
        payload = {
            "model":    MUSIC_ENDPOINT_ID,
            "messages": [
                {"role": "system", "content": CHARACTER_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            "max_tokens":  40,
            "temperature": 0.9,
        }

        try:
            resp = requests.post(
                MUSIC_API_BASE_URL,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.exceptions.Timeout:
            print("[音乐插件] API请求超时（不影响主程序）")
            return None
        except Exception as e:
            print(f"[音乐插件] API调用异常（不影响主程序）: {e}")
            return None

    # ── 插件生命周期 ──
    def stop(self):
        """停止插件运行"""
        self._running = False