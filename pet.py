# -*- coding: utf-8 -*-
"""
桌面宠物 2D 精致版
=================
猫耳娘桌宠：精美立绘 + 多表情/多动作 + Live2D 级动效 + 台词气泡
  · 表情：待机 / 开心 / 卖萌 / 惊讶 / 困倦 / 生气
  · 动作：走路 / 被拎起 / 挥手打招呼
  · 动效：待机呼吸起伏、点击弹跳、拖拽摆动、走路摇摆
  · 台词：混搭风格（软萌+元气），随机气泡，游戏免打扰时不弹
  · 菜单：右键呼出"她自己那张"粉色小卡片菜单（自绘，不是系统灰菜单），
         番茄钟的专注时长也能在菜单里改成 15/25/45/60 或任意分钟
  · 提醒：番茄钟结束 / 待办到点弹【常驻提醒卡片】+ 提示音，不点"知道啦"不消失
  · 大小：立绘按 PET_SCALE 整体缩放（当前 0.5 = 等比例缩到一半）
  · 保留：番茄钟、待办提醒、系统托盘、好感度、持久化

运行：  python pet.py
依赖：  pygame  pystray  Pillow
"""
import os
import sys
import json
import time
import random
import math
import threading
import ctypes

import pygame


def _now():
    """统一的时间源。

    全部定时逻辑都走这里取时间，自测里把它换成假时钟就能确定性地
    验证"到点了没有"，不用真的等一分钟。
    """
    return time.time()


def _play_sound(alias):
    """播放一个 Windows 系统提示音。

    用它而不是自己带 wav：系统音效一定有、不用打包音频文件，音量也跟随
    系统的"通知"音量（用户觉得吵可以直接在设置里关掉提醒声音）。
    SND_ASYNC = 不阻塞主循环；播不出来（非 Windows / 没有音频设备）就静默跳过。
    """
    if sys.platform != "win32":
        return
    try:
        import winsound
        winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
APP_NAME = "猫耳娘桌宠"
VERSION = "v20-icon"             # 版本号：用于确认运行中的代码版本
WIN_W, WIN_H = 240, 300          # 窗口尺寸（整体缩小 25%，更小巧不占屏）
# 立绘缩放：1.0 = 原来大小，0.5 = 等比例缩到一半。
# 注意缩放的是【她的立绘】，窗口尺寸不变 —— 窗口还得装得下右键菜单和
# 提醒卡片（那些是按像素写死的，跟着缩就没法看了）。她缩了之后窗口多出来的
# 透明边距由 _apply_window_region 裁成轮廓，照样点得到底下的窗口。
PET_SCALE = 0.5
BUBBLE_FONT = 13                 # 气泡字号（随窗口同步缩小，保持协调）
BUBBLE_LH = 19                   # 气泡行高
FPS = 60
EDGE_OVERLAP = 8                 # 贴边时窗口越出工作区的像素（把"裁切断口"藏到屏幕外）
EDGE_BAND = 30                   # 距贴边位置多少像素内算"贴上了"
EDGE_LIMIT = 24                  # 拖拽时最多允许越出工作区多少像素

# 启动落位："" = 记住上次位置；否则启动时自动贴到这条屏幕边
DEFAULT_START_EDGE = "right"
START_EDGES = ("left", "right", "top", "bottom", "")

# 自动变化：每隔多少秒她自己换个姿势/说句话（0 = 关闭，只有你点她才有反应）
# 到点自己动，不用你点；贴屏幕边的时候会变成"缩回去躲一下、再探出来看你"
DEFAULT_AUTO_SECS = 60
AUTO_CHOICES = [(0, "关闭"), (15, "15 秒"), (30, "30 秒"),
                (60, "1 分钟"), (180, "3 分钟"), (300, "5 分钟")]
# 贴边"缩回去"的最大位移（像素，按各自素材的内容宽度定，约遮住 3/4）：
# 看上去是"缩回屏幕边后面躲了一下"，然后再探出来看你
PEEK_RETREAT = {"peek_l": 105, "peek_r": 105, "peek_top": 145, "peek_bottom": 130}

# 提醒卡片挂着的时候，她站在窗口下半边、把上半边让给卡片；
# 这块矩形是"她所在的地方"（left, top, width, height），窗口区域要并上它。
ALERT_PET_ROOM = (78, 150, 84, 150)

# 右键菜单里"躲起来一会儿"的时长（秒）：只是临时藏一下，到点自己回来。
# 做成定时的原因：右键菜单能让她消失，但消失后就点不到她了，
# 万一忘了托盘图标在哪儿就"找不回来"，所以不提供无限期隐藏。
HIDE_SECS = 60

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE_DIR, "assets", "2d", "out")
# 快捷方式用的图标（make_icon.py 生成，多尺寸 ico）。
# 不指定的话 .lnk 会退化成 pythonw.exe 的"文档+蟒蛇"，缩到 48px 像只黄鸭子。
ICON_FILE = os.path.join(BASE_DIR, "assets", "icon.ico")
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "pet_data.json")
AUTOSTART_LNK = os.path.join(
    os.environ.get("APPDATA", ""),
    "Microsoft", "Windows", "Start Menu", "Programs", "Startup",
    APP_NAME + ".lnk")

# 番茄钟：专注时长不再写死，可以在右键菜单里挑 15/25/45/60 分钟，
# 也能输入任意分钟数（1~180），选完记进存档，下次开还是这个时长。
DEFAULT_POMO_WORK = 25
POMO_WORK_CHOICES = (15, 25, 45, 60)
POMO_WORK_MIN, POMO_WORK_MAX = 1, 180
POMODORO_BREAK = 5 * 60          # 专注结束后"休息一会儿"的时长

# ---- 到点提醒（番茄钟结束 / 待办到点）----
# 为什么不用台词气泡：气泡只在屏幕上挂几秒，人没看屏幕就彻底错过了；
# 贴边（默认就是贴屏幕右边缘）时窗口还会被裁成一条轮廓，气泡能不能露出来全看运气。
# 所以改成一张常驻卡片：不点"知道啦"就不走，还会隔几秒轻轻"叮"一声。
ALERT_BEEP_GAP = 3.0             # 每隔几秒响一次提示音
ALERT_BEEP_MAX = 6               # 最多响几声（不会没完没了地吵）
# 立绘本身已经缩到 PET_SCALE 了，提醒时不必再叠一层缩放，
# 只要把她挪到窗口下半边（卡片在窗口上部，两者刚好不打架）。
ALERT_PET_SCALE = 1.0
SNOOZE_SECS = 10 * 60            # 待办提醒里"再等一会儿"的时长

# 新建待办：内容与提醒时间的几个快捷选择（最后一个都是"自定义"）
TODO_TEXT_CHOICES = ("休息眼睛", "起来活动", "喝口水")
TODO_MIN_CHOICES = (10, 30, 60)
TODO_SHOW_MAX = 2                # 待办清单最多列几条（多了面板装不下）
TODO_TEXT_MAX = 10               # 自定义待办内容的字数上限
TODO_MINS_MIN, TODO_MINS_MAX = 1, 1440   # 自定义提醒时间的范围（分钟）

# ---------------------------------------------------------------------------
# 台词库（混搭：软萌 + 元气）
# ---------------------------------------------------------------------------
LINES = {
    "greet": [
        "主人回来啦～想我了没？",
        "今天也要加油鸭！(ง •_•)ง",
        "嘿嘿，我一直在等你哦～",
        "元气满满的一天开始啦！",
    ],
    "click": [
        "哇！被发现了～",
        "摸摸头嘛～",
        "嘿嘿，好痒～",
        "要点什么吗？",
        "咕咕咕？",
        "今天也要元气满满！",
    ],
    "moe": [
        "主人~摸摸头嘛(撒娇)",
        "要抱抱~",
        "陪我玩一会儿嘛～",
        "人家想你啦～",
    ],
    "drag": [
        "哇啊——飞起来啦！",
        "放、放我下来啦～",
        "喵呜？！",
        "轻一点轻一点～",
    ],
    "throw": [
        "呜哇——好晕……",
        "你是个坏人！(气鼓鼓)",
        "晕乎乎……",
    ],
    "idle": [
        "在忙什么呢？",
        "要不要休息一下呀～",
        "我会一直陪着你的哦",
        "困了的话就睡一会儿嘛",
        "偷偷告诉你：你今天超棒！",
    ],
    "sleep": ["呼…呼…(睡着了)", "Zzz…", "让我再睡五分钟…"],
    "squat": [
        "蹲一会儿…脚有点酸啦",
        "这样比较有安全感～",
        "你也在忙吗？我陪你蹲着",
    ],
    "sit": [
        "坐下来歇一会儿～",
        "地上凉凉的，还挺舒服",
        "过来坐嘛，陪我说说话～",
    ],
    "prone": [
        "趴着好舒服…要摸摸背吗？",
        "呼…这样看着你工作～",
        "嘿嘿，偷偷看你",
    ],
    "lie": [
        "躺一会儿…有点困了",
        "呼…呼…(蜷成一团睡着了)",
        "别吵我啦，我眯五分钟…",
    ],
    "stretch": [
        "伸——懒——腰——啊～舒服！",
        "久坐要活动一下哦！",
        "唔…骨头都在响啦～",
    ],
    "eat": [
        "小鱼干！最喜欢啦～",
        "啊呜～好吃！谢谢主人！",
        "吧唧吧唧…还要一条～",
    ],
    # 贴屏幕四边的姿势台词
    "peek_left": [
        "咦？被你发现啦～",
        "躲在这儿偷偷看你…",
        "嘿嘿，我藏好了哦",
    ],
    "peek_right": [
        "在这边！看我看我～",
        "从右边探头看看你在干嘛",
        "嘘——我在偷偷观察你",
    ],
    "peek_top": [
        "我从上面往下看你哦～",
        "低头看你，脖子有点酸…",
        "呼——爬上来好累呀",
    ],
    "peek_bottom": [
        "我从下面探个头～",
        "喂，带我一起玩嘛～",
        "这里视野不错哦",
    ],
    "peek_click": [
        "嘿嘿，被摸到啦～",
        "别戳啦，好痒～",
        "在的在的！",
    ],
    "hide": [
        "那我先躲一分钟，别忘了我哦～",
        "藏起来啦～一会儿见！",
        "嘘…我下线一下下",
    ],
    "back": [
        "我回来啦！想我了没～",
        "呼——休息好啦！",
        "哒哒！重新登场～",
    ],
    "angry": [
        "哼！不理你了…",
        "都多久没理我啦！",
        "生气了哦，快点摸摸头～",
    ],
    "pomodoro_start": ["开始专注 {} 分钟！我给你加油～", "专注 {} 分钟，冲呀！"],
    "pomodoro_work_done": ["专注结束！休息一下吧～", "辛苦啦！起来活动活动～"],
    "pomodoro_break_done": ["休息结束，继续加油鸭！", "元气恢复！开工！"],
    "todo_add": ["已记住待办：{}", "好嘞，到点我会提醒你的：{}"],
}

# ---------------------------------------------------------------------------
# 数据持久化
# ---------------------------------------------------------------------------
class PetData:
    def __init__(self):
        self.affection = 0
        self.todos = []
        self.pos = (100, 100)
        self.start_edge = DEFAULT_START_EDGE   # 启动时贴哪条屏幕边（""=记住上次位置）
        self.auto_secs = DEFAULT_AUTO_SECS     # 自动变化间隔（秒），0=关闭
        self.pomo_work = DEFAULT_POMO_WORK     # 番茄钟专注时长（分钟），可自己调
        self.alert_sound = True                # 到点提醒要不要"叮"一声
        os.makedirs(DATA_DIR, exist_ok=True)
        self.load()

    def load(self):
        if not os.path.exists(DATA_FILE):
            return
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.affection = int(d.get("affection", 0))
            self.todos = d.get("todos", [])
            p = d.get("pos", [100, 100])
            self.pos = (int(p[0]), int(p[1]))
            se = d.get("start_edge", DEFAULT_START_EDGE)
            self.start_edge = se if se in START_EDGES else DEFAULT_START_EDGE
            a = int(d.get("auto_secs", DEFAULT_AUTO_SECS))
            self.auto_secs = a if a >= 0 else DEFAULT_AUTO_SECS
            pw = int(d.get("pomo_work", DEFAULT_POMO_WORK))
            self.pomo_work = max(POMO_WORK_MIN, min(POMO_WORK_MAX, pw))
            self.alert_sound = bool(d.get("alert_sound", True))
        except Exception:
            pass

    def save(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"affection": self.affection, "todos": self.todos,
                           "pos": list(self.pos), "start_edge": self.start_edge,
                           "auto_secs": self.auto_secs,
                           "pomo_work": self.pomo_work,
                           "alert_sound": self.alert_sound},
                          f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 开机自启（往【启动】文件夹放一个快捷方式，登录即自动拉起）
# ---------------------------------------------------------------------------
def _powershell(cmd):
    """静默执行一段 PowerShell（不弹黑窗）。"""
    import subprocess
    p = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", cmd],
        capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def autostart_enabled():
    """是否已经登记开机自启。"""
    return os.path.exists(AUTOSTART_LNK)


def set_autostart(on):
    """开启/关闭开机自启。返回 (成功?, 提示文字)。

    快捷方式的目标用 pythonw.exe（没有控制台窗口），所以开机时她安安静静
    地出现在桌面上，不会闪一个黑框。
    """
    if not on:
        try:
            if os.path.exists(AUTOSTART_LNK):
                os.remove(AUTOSTART_LNK)
            return True, "已关闭开机自启"
        except Exception as e:
            return False, "关闭失败：%s" % e

    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(exe):
        exe = sys.executable
    script = os.path.join(BASE_DIR, "pet.py")
    if not os.path.exists(script):
        return False, "找不到 pet.py"
    ps = (
        "$w = New-Object -ComObject WScript.Shell;"
        "$s = $w.CreateShortcut('%s');"
        "$s.TargetPath = '%s';"
        "$s.Arguments = '\"%s\"';"
        "$s.WorkingDirectory = '%s';"
        "$s.WindowStyle = 7;"
        "$s.Description = '%s';"
        "$s.IconLocation = '%s,0';"
        "$s.Save()"
    ) % (AUTOSTART_LNK, exe, script, BASE_DIR, APP_NAME, ICON_FILE)
    code, out = _powershell(ps)
    if os.path.exists(AUTOSTART_LNK):
        return True, "已开启开机自启"
    return False, "开启失败：%s" % (out.strip()[:120] or "code=%d" % code)


# ---------------------------------------------------------------------------
# 图片帧加载
# ---------------------------------------------------------------------------
class Frames:
    """加载所有立绘帧。

    所有素材都是 512x512 画布，贴边姿势的"裁切断口"已经贴死在画布的某条边上，
    所以 pet.py 只要把整张画布贴到窗口对应的那条边，断面就正好落在屏幕边缘。
    """
    STATE_MAP = {
        "idle": "base_idle", "happy": "happy", "moe": "moe",
        "surprised": "surprised", "sleepy": "sleepy", "angry": "angry",
        "walk": "walk", "dragged": "dragged", "wave": "wave",
        # 新增姿势
        "squat": "squat", "sit": "sit", "prone": "prone",
        "lie": "lie", "stretch": "stretch", "eat": "eat",
        # 贴屏幕四边的姿势
        "peek_l": "edge_peek_l",          # 左：躲屏幕边探头（双手扒边、探出上半身）
        "peek_r": "edge_peek_l_r",        # 右：镜像
        "peek_top": "edge_peek_top",      # 上：从上边探出脑袋
        "peek_bottom": "edge_peek_bottom",  # 下：从下边探出上半身
    }

    def __init__(self):
        self.imgs = {}
        for state, fname in self.STATE_MAP.items():
            path = os.path.join(IMG_DIR, fname + ".png")
            if os.path.exists(path):
                img = pygame.image.load(path).convert_alpha()
                # 512x512 画布 → 窗口内的大小，再乘 PET_SCALE（等比例缩小）。
                # 画布等比例缩小时，画布里"贴死在某条边上的裁切断口"也跟着走，
                # 所以四边贴边姿势的断面依旧落在屏幕（工作区）边缘上。
                img = pygame.transform.smoothscale(
                    img, (max(1, round((WIN_W - 20) * PET_SCALE)),
                          max(1, round((WIN_H - 20) * PET_SCALE))))
                self.imgs[state] = img
            else:
                # 兜底：缺图时画个色块，不至于崩溃
                s = pygame.Surface((100, 100), pygame.SRCALPHA)
                pygame.draw.circle(s, (255, 170, 200), (50, 50), 48)
                self.imgs[state] = s

    def get(self, state):
        return self.imgs.get(state, self.imgs["idle"])


# ---------------------------------------------------------------------------
# 台词系统
# ---------------------------------------------------------------------------
class Voice:
    def __init__(self):
        self.text = ""
        self.until = 0

    def say(self, key, secs=3.5, fmt=None):
        lines = LINES.get(key)
        if not lines:
            return
        text = random.choice(lines)
        if fmt:
            text = text.format(fmt)
        self.text = text
        self.until = _now() + secs

    def say_text(self, text, secs=3.5):
        """直接说一句指定的话（用于系统提示，如"已开启开机自启"）。"""
        self.text = text
        self.until = _now() + secs

    def visible(self):
        return self.text and _now() < self.until


# ---------------------------------------------------------------------------
# 桌宠本体（状态机 + Live2D 级动效参数）
# ---------------------------------------------------------------------------
class Pet:
    IDLE = "idle"; HAPPY = "happy"; MOE = "moe"; SURPRISED = "surprised"
    SLEEPY = "sleepy"; ANGRY = "angry"; WALK = "walk"; DRAGGED = "dragged"; WAVE = "wave"
    # 新增姿势
    SQUAT = "squat"; SIT = "sit"; PRONE = "prone"
    LIE = "lie"; STRETCH = "stretch"; EAT = "eat"
    # 贴屏幕四边的姿势
    PEEK_L = "peek_l"; PEEK_R = "peek_r"; PEEK_TOP = "peek_top"; PEEK_BOTTOM = "peek_bottom"
    EDGE_POSE = {"left": PEEK_L, "right": PEEK_R, "top": PEEK_TOP, "bottom": PEEK_BOTTOM}

    # "自动变化"时随机挑的小动作：(状态, 台词键, 最短时长, 最长时长)
    #   状态为 None = 姿势不变、单纯说句话
    AUTO_TABLE = [
        (WALK,      None,      3.0, 4.5),   # 走来走去
        (WAVE,      "greet",   2.5, 2.5),
        (MOE,       "moe",     2.5, 2.5),
        (HAPPY,     "click",   2.2, 2.2),
        (SQUAT,     "squat",   3.5, 5.0),
        (SIT,       "sit",     3.5, 5.0),
        (PRONE,     "prone",   3.5, 5.0),
        (LIE,       "lie",     3.5, 5.0),
        (STRETCH,   "stretch", 2.5, 3.0),
        (EAT,       "eat",     3.5, 4.0),
        (SLEEPY,    "sleep",   3.0, 4.0),
        (SURPRISED, "click",   1.8, 1.8),
        (None,      "idle",    3.5, 3.5),
    ]

    def __init__(self, data, voice):
        self.data = data
        self.voice = voice
        self.state = self.IDLE
        self.state_until = _now() + 3
        self.edge = None           # 当前贴在哪条屏幕边：None/left/right/top/bottom
        # 动效参数
        self.breath = 0.0          # 呼吸相位
        self.bounce = 0.0          # 弹跳值（点击时触发，衰减）
        self.tilt = 0.0            # 拖拽倾斜
        self.walk_dir = 1
        self.walk_phase = 0.0
        self._just_grabbed = False
        self._dragging = False     # 是否正被拎着（拖动期间不自动变化）
        # 自动变化（定时自己动一下）
        self._next_auto = _now() + self._first_gap()
        self.peek_anim = 0.0       # 贴边"缩回去"的进度：0=正常探头，1=缩回屏幕外
        self._peek_t = -1.0        # 贴边动画计时（<0 表示没在演）
        self._peek_said = False
        # 番茄钟
        self.pomodoro_active = False
        self.pomodoro_mode = "work"
        self.pomodoro_end = 0
        self.pomodoro_work_secs = 0    # 本次专注的总时长（算进度条用）
        # 到点提醒：由 App 注入一个回调（"我这边有事要告诉你"），Pet 只负责报事。
        # 这样 Pet 不用知道窗口/卡片/音效那些事，自测里也能塞个假的收集一下。
        self.notify = None
        # 提醒卡片显示期间：挂起"贴边姿势必须保持"这条规矩。
        # 否则她会被立刻拉回贴边姿势，缩小的让位动作也就白做了。
        self.alert_hold = False

    def set_state(self, state, dur=None, now=None):
        self.state = state
        if dur:
            self.state_until = (now if now is not None else _now()) + dur

    def set_edge(self, side):
        """贴到某条屏幕边（None = 离开边缘）。第一次贴上去会说句话。"""
        if side == self.edge:
            return
        self.edge = side
        if side:
            self.set_state(self.EDGE_POSE[side], 9999)
            self.voice.say("peek_" + side, 3.0)
        else:
            # 离开边缘：取消演到一半的"探头"，稍等片刻再回到普通待机，避免状态突变
            self._peek_t = -1.0
            self.peek_anim = 0.0
            if self.state in self.EDGE_POSE.values():
                self.state_until = _now() + 0.6

    # ---- 自动变化：每隔一段时间她自己动一下（换姿势 / 说话 / 贴边露个脸）----
    def _first_gap(self):
        """启动后第一次变化的等待时间：别让她一上来就干等一分钟。"""
        s = int(self.data.auto_secs)
        return float(min(s, 15)) if s > 0 else 15.0

    def _auto_gap(self):
        """本次到下次的间隔，带一点随机抖动，免得像机械钟一样准点。"""
        s = int(self.data.auto_secs)
        return s * random.uniform(0.85, 1.15) if s > 0 else 0.0

    def reset_auto_timer(self):
        """设置里改了间隔之后重新起算。"""
        self._next_auto = _now() + self._first_gap()
        self._peek_t = -1.0
        self.peek_anim = 0.0

    def update(self, dt, now):
        self.breath += dt
        self.bounce = max(0.0, self.bounce - dt * 3.5)
        # 未被拖拽时倾斜回正
        self.tilt *= 0.9

        if self.pomodoro_active and now >= self.pomodoro_end:
            self._pomodoro_finish()

        if self.edge is not None and not self.alert_hold:
            # 贴边期间固定用贴边姿势；若被投喂/番茄钟等临时动作顶掉，动作结束自动拉回
            if self.state != self.EDGE_POSE[self.edge] and now >= self.state_until:
                self.set_state(self.EDGE_POSE[self.edge], 9999, now)
        elif now >= self.state_until and self.state != self.DRAGGED:
            # 动作演完（点击/托盘指定的姿势也算）→ 回到安静待机。
            # 之后什么时候再动，交给下面的"自动变化"到点触发。
            self.set_state(self.IDLE, 3600, now)

        # 走路相位
        if self.state == self.WALK:
            self.walk_phase += dt * 8

        self._update_auto(dt, now)

    def _update_auto(self, dt, now):
        """每帧问一句：到点了没？该她自己动一下了。"""
        # 贴边的"缩回去"动画优先演完，演出期间不叠加新动作
        if self._peek_t >= 0:
            self._step_peek_anim(dt)
            return
        if self.alert_hold:
            # 提醒卡片正挂在窗口上：这几秒别自己乱动，把注意力留给卡片
            self._next_auto = now + 2.0
            return
        if self.data.auto_secs <= 0 or now < self._next_auto:
            return
        if self._dragging:
            self._next_auto = now + 3.0       # 正被拎着：先别动，等放下
            return
        if self.voice.visible():
            self._next_auto = now + 2.0       # 正在说话（待办提醒/番茄钟/被摸头）：让她把话说完
            return
        self._auto_change(now)

    def _auto_change(self, now):
        """到点了：随机挑一个小动作 + 一句台词。贴边时改成"露个脸"。"""
        self._next_auto = now + self._auto_gap()
        if self.edge is not None:
            # 贴着屏幕边：缩回去躲一下、再探出来看你（台词在探头那一刻说）
            self._peek_t = 0.0
            self._peek_said = False
            return
        state, key, lo, hi = random.choice(self.AUTO_TABLE)
        if state is not None:
            self.set_state(state, random.uniform(lo, hi), now)
            if state == self.WALK:
                self.walk_dir = random.choice([-1, 1])
        if key:
            self.voice.say(key, 3.0)

    def _step_peek_anim(self, dt):
        """贴边探头的时间线：缩回去 0.35s → 躲一下 0.6s → 探出来 0.5s。"""
        self._peek_t += dt
        t = self._peek_t
        if t < 0.35:
            a = t / 0.35
        elif t < 0.95:
            a = 1.0
        elif t < 1.45:
            a = 1.0 - (t - 0.95) / 0.50
            if not self._peek_said:           # 探头出来的瞬间说话，像"嗨～我在这儿"
                self._peek_said = True
                self.voice.say("peek_" + self.edge, 3.0)
        else:
            self._peek_t = -1.0
            a = 0.0
        self.peek_anim = max(0.0, min(1.0, a))

    def on_click(self):
        self.data.affection = min(100, self.data.affection + 1)
        self.bounce = 1.0
        if self.edge is not None:
            # 贴边时保持贴边姿势，只摸头回应（否则会突然换成笑脸、姿势断掉）
            self.voice.say("peek_click", 2.5)
            self.data.save()
            return
        r = random.random()
        if r < 0.42:
            self.set_state(self.HAPPY, 2)
        elif r < 0.68:
            self.set_state(self.MOE, 2)
        elif r < 0.86:
            self.set_state(self.SURPRISED, 1.5)
        elif r < 0.94:
            self.feed()          # 偶尔被点到就去吃小鱼干
            return
        else:
            self.set_state(self.SQUAT, 3)
            self.voice.say("squat", 2.5)
            self.data.save()
            return
        self.voice.say("click", 2.5)
        self.data.save()

    def feed(self):
        """投喂小鱼干：切到吃东西的姿势。"""
        self.set_state(self.EAT, 4)
        self.voice.say("eat", 3.5)

    def pose_once(self, state, key=None):
        """托盘/快捷键直接摆一个指定姿势。"""
        self.set_state(state, 5)
        if key:
            self.voice.say(key, 3)

    def random_pose(self):
        """随机摆一个新姿势（蹲/坐/趴/躺/伸懒腰/吃）。"""
        keys = {self.SQUAT: "squat", self.SIT: "sit", self.PRONE: "prone",
                self.LIE: "lie", self.STRETCH: "stretch", self.EAT: "eat"}
        st = random.choice(list(keys.keys()))
        self.pose_once(st, keys[st])

    def on_drag(self, dx):
        # 拖动时不再改变状态（保持原表情不切到慌张脸），倾斜也设为 0（防止晃动感）
        self.tilt = 0
        if self._just_grabbed:
            self._just_grabbed = False
            if random.random() < 0.3:
                self.voice.say("drag", 1.5)

    def on_grab(self):
        """按下瞬间调用一次，触发被抓台词。"""
        self._just_grabbed = True
        self._dragging = True

    def on_release(self, moved):
        self._dragging = False       # 放下之后才允许"自动变化"继续
        self.reset_auto_timer()      # 重新起算，免得刚放下就立刻动
        if moved:
            if self.edge is None:
                self.set_state(self.SURPRISED, 1.2)
            if random.random() < 0.5:
                self.voice.say("throw", 2)
        else:
            self.on_click()

    def start_pomodoro(self, minutes=None):
        """开始专注。

        时长默认取存档里设定的（默认 25 分钟，右键菜单可改），
        也允许临时指定一个（便于测试/托盘快捷方式）。
        """
        m = int(minutes if minutes is not None else self.data.pomo_work)
        m = max(POMO_WORK_MIN, min(POMO_WORK_MAX, m))
        self.pomodoro_active = True
        self.pomodoro_mode = "work"
        self.pomodoro_end = _now() + m * 60
        self.pomodoro_work_secs = m * 60      # 本次时长（菜单里画进度用）
        self.set_state(self.WAVE, 2)
        self.voice.say("pomodoro_start", 3.5, fmt=m)

    def pomodoro_left(self):
        """本次专注还剩多少秒（没在专注时返回 0）。右键菜单里显示倒计时用。"""
        if not self.pomodoro_active:
            return 0
        return max(0, int(self.pomodoro_end - _now()))

    def stop_pomodoro(self):
        """提前收工（右键菜单用）。"""
        if not self.pomodoro_active:
            return False
        self.pomodoro_active = False
        self.voice.say_text("番茄钟停掉啦～想休息就休息吧", 3.0)
        return True

    def start_break(self, seconds=POMODORO_BREAK):
        """专注结束后的"休息一会儿"（提醒卡片上的按钮）。"""
        seconds = max(60, int(seconds))
        self.pomodoro_active = True
        self.pomodoro_mode = "break"
        self.pomodoro_end = _now() + seconds
        self.pomodoro_work_secs = seconds
        self.set_state(self.MOE, 3)
        self.voice.say_text("好～休息 %d 分钟，起来动动、看看远处～" % (seconds // 60), 3.5)

    def _pomodoro_finish(self):
        """到点了。

        以前这里只是说一句话就完事，几秒后气泡消失、人一低头看代码就
        彻底错过了。现在改成报给 App 弹【常驻提醒卡片】，不点"知道啦"不走。
        """
        self.pomodoro_active = False
        if self.pomodoro_mode == "work":
            self.voice.say("pomodoro_work_done", 4)
            if self.notify:
                self.notify("pomo_done", self.pomodoro_work_secs // 60)
        else:
            self.voice.say("pomodoro_break_done", 4)
            if self.notify:
                self.notify("break_done", 0)
        self.set_state(self.WAVE, 2.5)
        self.bounce = 1.0

    def add_todo(self, text, due):
        text = (text or "").strip()[:TODO_TEXT_MAX] or "待办"
        self.data.todos.append({"text": text, "due": due})
        self.data.save()
        left = int(due - _now())
        when = ("%d 分钟后" % max(1, left // 60)) if left > 60 else "一会儿"
        self.voice.say_text("好嘞，%s提醒你：%s" % (when, text), 3.5)
        return self.data.todos[-1]

    def check_todos(self):
        """到点的待办 → 交给提醒卡片。返回这次到点的条目（没有就返回空表）。

        注意：这里【不再】把到点的待办删掉。以前是"响一下就丢"，万一那几秒
        没看屏幕，这条待办就静悄悄地没了。现在改由提醒卡片上的按钮决定：
        "知道啦"才划掉，"再等 10 分钟"就把时间往后挪。
        """
        now = _now()
        fired = []
        for t in self.data.todos:
            try:
                due = float(t.get("due", 0) or 0)
            except (TypeError, ValueError):
                continue
            if 0 < due <= now:
                fired.append(t)
        if not fired:
            return []
        if self.alert_hold:
            # 已经有提醒卡片挂在窗口上了（alert_hold 就是"卡片在"的标记），
            # 别再弹第二张 —— 主循环也拦了一道，这里是兜底。
            return []
        if self.notify:
            self.notify("todo_due", fired)
        else:
            # 没有卡片可弹（理论上不会）：退回老做法，免得待办永远响不完
            self.voice.say_text("待办提醒：" + fired[0].get("text", ""), 6)
            self.data.todos = [t for t in self.data.todos
                               if not any(t is f for f in fired)]
            self.data.save()
        return fired

    def back_from_alert(self):
        """提醒卡片关掉之后：立刻回到她本来该有的姿势。"""
        self.alert_hold = False
        if self.edge is not None:
            self.set_state(self.EDGE_POSE[self.edge], 9999)   # 继续贴边探头
        else:
            self.set_state(self.IDLE, 0.5)


# ---------------------------------------------------------------------------
# 游戏免打扰
# ---------------------------------------------------------------------------
class GameDetector:
    def __init__(self):
        self._last = 0
        self._cached = False

    def is_gaming(self):
        now = time.time()
        if now - self._last < 1.0:
            return self._cached
        self._last = now
        gaming = False
        if sys.platform == "win32":
            gaming = self._fullscreen()
        self._cached = gaming
        return gaming

    def _fullscreen(self):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return False
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w, h = rect.right - rect.left, rect.bottom - rect.top
            sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
            return w >= sw - 10 and h >= sh - 10
        except Exception:
            return False


# ---------------------------------------------------------------------------
# 托盘
# ---------------------------------------------------------------------------
class Tray:
    def __init__(self, app):
        self.app = app

    def start(self):
        """托盘线程入口。

        开机自启时是刚登录就跑，explorer 可能还没就绪，这时 pystray 建图标
        会失败；重试几次就不会出现"窗口在、托盘里却没图标"的情况。
        """
        for attempt in range(1, 7):
            try:
                self._run()
                return
            except Exception as e:
                print("[托盘] 第 %d 次创建图标失败：%s" % (attempt, e))
                time.sleep(3)

    def _run(self):
        import pystray
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((10, 14, 54, 58), fill=(255, 200, 220, 255), outline=(180, 120, 150, 255), width=2)
        d.polygon([(12, 20), (6, 4), (28, 14)], fill=(255, 245, 250, 255))
        d.polygon([(52, 20), (58, 4), (36, 14)], fill=(255, 245, 250, 255))
        d.ellipse((20, 30, 28, 38), fill=(90, 90, 120, 255))
        d.ellipse((36, 30, 44, 38), fill=(90, 90, 120, 255))

        def side_action(s):
            return lambda i, it: self.app.set_start_edge(s)

        def side_checked(s):
            return lambda it: self.app.data.start_edge == s

        def auto_action(secs):
            return lambda i, it: self.app.set_auto_secs(secs)

        def auto_checked(secs):
            return lambda it: self.app.data.auto_secs == secs

        def pomo_action(mins):
            return lambda i, it: self.app.set_pomo_work(mins)

        def pomo_checked(mins):
            return lambda it: self.app.data.pomo_work == mins

        menu = pystray.Menu(
            pystray.MenuItem("显示/隐藏", lambda i, it: self.app.toggle_visible(), default=True),
            pystray.MenuItem("投喂小鱼干", lambda i, it: self.app.pet.feed()),
            pystray.MenuItem("随机换个姿势", lambda i, it: self.app.pet.random_pose()),
            pystray.MenuItem("姿势", pystray.Menu(
                pystray.MenuItem("蹲着", lambda i, it: self.app.pet.pose_once(Pet.SQUAT, "squat")),
                pystray.MenuItem("坐着", lambda i, it: self.app.pet.pose_once(Pet.SIT, "sit")),
                pystray.MenuItem("趴着", lambda i, it: self.app.pet.pose_once(Pet.PRONE, "prone")),
                pystray.MenuItem("躺着", lambda i, it: self.app.pet.pose_once(Pet.LIE, "lie")),
                pystray.MenuItem("伸懒腰", lambda i, it: self.app.pet.pose_once(Pet.STRETCH, "stretch")),
                pystray.MenuItem("吃东西", lambda i, it: self.app.pet.feed()),
            )),
            pystray.MenuItem("自动变化", pystray.Menu(*[
                pystray.MenuItem(label, auto_action(secs),
                                 checked=auto_checked(secs), radio=True)
                for secs, label in AUTO_CHOICES
            ])),
            pystray.MenuItem("启动位置", pystray.Menu(
                pystray.MenuItem("贴屏幕右边缘", side_action("right"),
                                 checked=side_checked("right"), radio=True),
                pystray.MenuItem("贴屏幕左边缘", side_action("left"),
                                 checked=side_checked("left"), radio=True),
                pystray.MenuItem("贴屏幕上边缘", side_action("top"),
                                 checked=side_checked("top"), radio=True),
                pystray.MenuItem("贴屏幕下边缘", side_action("bottom"),
                                 checked=side_checked("bottom"), radio=True),
                pystray.MenuItem("记住上次位置", side_action(""),
                                 checked=side_checked(""), radio=True),
            )),
            pystray.MenuItem("开机自动启动", lambda i, it: self.app.toggle_autostart(i),
                             checked=lambda it: autostart_enabled()),
            pystray.MenuItem("开启番茄钟", lambda i, it: self.app.pet.start_pomodoro()),
            pystray.MenuItem("专注时长", pystray.Menu(*[
                pystray.MenuItem("%d 分钟" % m, pomo_action(m),
                                 checked=pomo_checked(m), radio=True)
                for m in POMO_WORK_CHOICES
            ])),
            pystray.MenuItem("添加待办(30分钟后)",
                             lambda i, it: self.app.pet.add_todo(
                                 TODO_TEXT_CHOICES[0], time.time() + 1800)),
            pystray.MenuItem("退出", lambda i, it: self.app.quit()),
        )
        pystray.Icon("pet", img, APP_NAME, menu).run()


# ---------------------------------------------------------------------------
# 桌面右键菜单（自己画，和她的形象是一套）
# ---------------------------------------------------------------------------
def _mi(label, key=None, mark=None, enabled=True, checked=False, kind="item",
        items=None):
    """菜单里的一行。

    kind：item=可点、text/note=只显示（note 更小更矮）、chips=一排小圆钮、
          bar=进度条、input=输入框、tip=灰提示。
    items：只有 chips 用，内容为 [(按钮文案, 动作键, 是否选中), ...]。
    """
    return {"label": label, "key": key, "mark": mark,
            "enabled": enabled, "checked": checked, "kind": kind,
            "items": items}


class PetMenu:
    """在她身上点右键 → 弹出"她自己的"菜单。

    为什么自己画，不用系统右键菜单：系统菜单是灰白色的办公风格，和她
    摆在一起像两个软件拼起来的。自己画就能做成"奶白卡片 + 粉色描边 +
    她的圆头像"的样子，悬停高亮、勾选圆点、一行小圆钮这些也都能跟着走。

    画在哪儿：直接画在桌宠自己的窗口里（240x300），不额外开窗口、不跨进程。
    一页塞不下就按页切（姿势/番茄钟/待办/设置/自动变化/启动位置各一页），
    一页最多 8 行，连标题栏一起正好装得下。打开菜单那一帧把窗口区域恢复成
    整块矩形，就不会被贴边用的轮廓裁剪切掉。

    操作：移动高亮、左键选中、点面板外或按 Esc 收起、再按右键也收起。
    选中的结果只记成一个动作键，由主循环执行（换姿势/搬窗口只能在主线程做）。
    """

    PANEL_X, PANEL_Y = 8, 8
    PANEL_W = WIN_W - 16           # 224
    HEAD_H = 34                    # 标题栏高度
    ITEM_H = 28
    GAP = 6                        # 分组之间的空隙

    # 配色：和台词气泡同一套粉白，放一起才像"一个人"
    C_SHADOW = (236, 148, 190, 60)
    C_PANEL = (255, 252, 254, 252)
    C_EDGE = (246, 176, 206, 255)
    C_HEAD = (255, 231, 241, 255)
    C_TEXT = (110, 80, 96)
    C_TEXT_OFF = (194, 176, 186)
    C_TEXT_HI = (203, 70, 122)
    C_HOVER = (255, 238, 246, 255)
    C_PINK = (246, 158, 198, 255)
    C_PINK_DK = (198, 96, 140, 255)
    C_SEP = (250, 214, 228, 255)

    PAGE_TITLE = {"root": "猫耳娘", "pose": "换个姿势", "pomo": "番茄钟",
                  "todo": "待办", "set": "设置", "auto": "自动变化",
                  "edge": "启动位置"}

    # 姿势子页：菜单文案 → 动作键
    POSE_ITEMS = [
        ("蹲着", "squat"),
        ("坐着", "sit"),
        ("趴着", "prone"),
        ("躺着", "lie"),
        ("伸个懒腰", "stretch"),
        ("挥手打招呼", "wave"),
    ]

    def __init__(self, app):
        self.app = app
        self.open = False
        self.page = "root"
        self.stack = ["root"]      # 页面栈：进子页 push，返回 pop
        self.hover = None          # 鼠标悬停在哪一项（存动作键）
        # 正在输入框里敲字时是哪个模式：None / "pomo_work" / "todo_text" / "todo_mins"
        self.input_mode = None
        self.input_text = ""
        self.todo_text = TODO_TEXT_CHOICES[0]   # 待办页当前选好的内容
        self._ava = -1             # 头像缓存（-1 = 还没算过）

    # ---- 对外：打开 / 收起 ----
    def open_at(self, gx, gy):
        """右键点在屏幕 (gx, gy)：把菜单打开。"""
        self.open = True
        self.page = "root"
        self.stack = ["root"]
        self.hover = None
        self.input_mode = None
        self.input_text = ""
        try:
            pygame.key.start_text_input()      # 自定义时长要打字，先开启文字输入
        except Exception:
            pass
        # 窗口得能收键盘（否则输入框敲不进字），顺带保证点面板外面能自动收起
        if sys.platform == "win32" and self.app.hwnd:
            try:
                ctypes.windll.user32.SetForegroundWindow(self.app.hwnd)
            except Exception:
                pass
        self.app._log("[菜单] 打开于 (%d,%d)" % (gx, gy))

    def close(self):
        if not self.open:
            return
        self.open = False
        self.hover = None
        self.input_mode = None
        self.input_text = ""
        try:
            pygame.key.stop_text_input()
        except Exception:
            pass

    # ---- 页面内容 ----
    def _chips(self, values, key_fmt, current, custom_key):
        """一排小圆钮：values 里最后补一个"自定义"。返回 chips 行的 items。"""
        items = [("%s" % lab, key_fmt % lab, current == lab) for lab in values]
        items.append(("自定义", custom_key, False))
        return items

    def _rows(self, page):
        """当前页的内容行，None = 分隔线。勾选/可用每帧现算，跟着存档走。"""
        data, pet = self.app.data, self.app.pet
        if page == "root":
            return [
                _mi("摸摸头", "pat"),
                _mi("投喂小鱼干", "feed"),
                _mi("换个姿势", "nav:pose", mark="arrow"),
                _mi("番茄钟", "nav:pomo", mark="arrow"),
                _mi("待办", "nav:todo", mark="arrow"),
                _mi("设置", "nav:set", mark="arrow"),
                _mi("躲起来 %d 秒" % HIDE_SECS, "hide"),
            ]
        if page == "pose":
            rows = [_mi("返回", "back", mark="back"), None,
                    _mi("随机来一个", "pose:random")]
            return rows + [_mi(label, "pose:" + k) for label, k in self.POSE_ITEMS]
        if page == "pomo":
            if pet.pomodoro_active:
                left = pet.pomodoro_left()
                what = "专注中" if pet.pomodoro_mode == "work" else "休息中"
                status = "%s · 还剩 %d:%02d" % (what, left // 60, left % 60)
            else:
                status = "现在没在专注哦"
            rows = [_mi("返回", "back", mark="back"), None,
                    _mi(status, kind="text")]
            if pet.pomodoro_active:
                rows.append(_mi("", kind="bar"))       # 进度条，一眼看到还剩多少
            return rows + [
                _mi("开始专注（%d 分钟）" % data.pomo_work, "pomodoro:start",
                    enabled=not pet.pomodoro_active),
                _mi("停止", "pomodoro:stop", enabled=pet.pomodoro_active),
                None,
                _mi("专注时长（分钟）", kind="text"),
                _mi("", kind="chips", items=self._chips(
                    POMO_WORK_CHOICES, "pomo_work:%d", data.pomo_work,
                    "__custom__:pomo_work")),
            ]
        if page == "todo":
            rows = [_mi("返回", "back", mark="back"), None,
                    _mi("待办清单", kind="text")]
            now = _now()
            todos = data.todos
            if not todos:
                rows.append(_mi("（现在没有待办）", kind="note"))
            else:
                for t in todos[:TODO_SHOW_MAX]:
                    left = int(float(t.get("due", 0) or 0) - now)
                    when = "还有 %d 分钟" % max(1, (left + 59) // 60) if left > 0 else "时间到了"
                    rows.append(_mi("· %s · %s" % (t.get("text", ""), when), kind="note"))
                if len(todos) > TODO_SHOW_MAX:
                    rows.append(_mi("…另外还有 %d 条" % (len(todos) - TODO_SHOW_MAX),
                                    kind="note"))
            # 输入自定义内容/时间的时候，清单就让位（面板总共只有 240x300）
            if self.input_mode in ("todo_text", "todo_mins"):
                # 输入框和提示行由 layout 自动补上（跟着 y 往下排）
                label = ("新建待办 · 输入内容" if self.input_mode == "todo_text"
                         else "新建待办 · 输入提醒分钟数")
                return [_mi("返回", "back", mark="back"), None,
                        _mi(label, kind="text")]
            rows.append(None)
            rows.append(_mi("新建 · 内容", kind="text"))
            rows.append(_mi("", kind="chips", items=self._chips(
                TODO_TEXT_CHOICES, "todo_text:%s", self.todo_text,
                "__custom__:todo_text")))
            rows.append(_mi("新建 · 提醒时间", kind="text"))
            rows.append(_mi("", kind="chips", items=[
                ("%d 分" % m, "todo:add:%d" % m, False) for m in TODO_MIN_CHOICES]
                + [("自定义", "__custom__:todo_mins", False)]))
            rows.append(None)
            rows.append(_mi("清空全部待办（%d 条）" % len(todos), "todo:clear",
                            enabled=bool(todos)))
            return rows
        if page == "set":
            return [
                _mi("返回", "back", mark="back"), None,
                _mi("自动变化", "nav:auto", mark="arrow"),
                _mi("启动位置", "nav:edge", mark="arrow"),
                _mi("开机自动启动", "autostart", mark="check",
                    checked=autostart_enabled()),
                _mi("提醒声音", "alert_sound", mark="check",
                    checked=data.alert_sound),
                None,
                _mi("关于我", "about"),
                _mi("拜拜（退出）", "quit"),
            ]
        if page == "auto":
            rows = [_mi("返回", "back", mark="back"), None]
            return rows + [_mi(label if secs else "安安静静待着", "auto:%d" % secs,
                               mark="radio", checked=data.auto_secs == secs)
                           for secs, label in AUTO_CHOICES]
        if page == "edge":
            rows = [_mi("返回", "back", mark="back"), None]
            for side, label in (("right", "贴屏幕右边"), ("left", "贴屏幕左边"),
                                ("top", "贴屏幕上面"), ("bottom", "贴屏幕下面"),
                                ("", "记住上次的位置")):
                rows.append(_mi(label, "edge:" + side, mark="radio",
                                checked=data.start_edge == side))
            return rows
        return [_mi("返回", "back", mark="back")]

    def layout(self):
        """算出这一页每一行的矩形（每帧算：勾选、待办条数都在变）。

        返回 (行列表, 面板高度)；行里的 dict 直接给命中判定和绘制用。
        """
        x0 = self.PANEL_X + 12
        w = self.PANEL_W - 24
        y = self.PANEL_Y + self.HEAD_H + 2
        items = []
        for row in self._rows(self.page):
            if row is None:
                cy = y + self.GAP // 2
                items.append({"kind": "sep", "key": None, "label": "", "mark": None,
                              "enabled": False, "checked": False,
                              "rect": pygame.Rect(x0, cy - 1, w, 2)})
                y += self.GAP
                continue
            if row["kind"] == "bar":
                items.append(dict(row, rect=pygame.Rect(x0, y, w, 8)))
                y += 14
                continue
            if row["kind"] in ("text", "note"):
                # 只显示的行：note（清单条目）比 text（小标题）更矮一点
                hh = 17 if row["kind"] == "note" else 19
                items.append(dict(row, rect=pygame.Rect(x0, y, w, hh)))
                y += hh
                continue
            if row["kind"] == "chips":
                # 一排等宽小圆钮（专注时长 / 待办内容 / 待办时间都用它）
                chips = row.get("items") or []
                n = max(1, len(chips))
                gap, ch = 4, 26
                cw = (w - gap * (n - 1)) // n
                for i, (lab, key, on) in enumerate(chips):
                    items.append(dict(row, kind="chip", label=lab, enabled=True,
                                      key=key, checked=on,
                                      rect=pygame.Rect(x0 + i * (cw + gap), y, cw, ch)))
                y += ch + 4
                continue
            items.append(dict(row, rect=pygame.Rect(x0, y, w, self.ITEM_H)))
            y += self.ITEM_H
        if self.input_mode:
            items.append({"kind": "input", "key": None, "label": "", "mark": None,
                          "enabled": True, "checked": False, "items": None,
                          "rect": pygame.Rect(x0, y, w, 28)})
            y += 30
            items.append({"kind": "tip", "key": None, "mark": None,
                          "label": ("1-180 分钟 · 回车确定 · Esc 取消"
                                    if self.input_mode == "pomo_work"
                                    else "回车确定 · Esc 取消"),
                          "enabled": True, "checked": False, "items": None,
                          "rect": pygame.Rect(x0, y, w, 16)})
            y += 16
        return items, (y - self.PANEL_Y + 8)

    # ---- 交互 ----
    def _at(self, pos):
        items, _ = self.layout()
        for it in items:
            if it["kind"] in ("item", "chip", "close") and it["rect"].collidepoint(pos):
                return it
        return None

    def on_move(self, pos):
        it = self._at(pos)
        if it is not None:
            self.hover = it["key"] if it.get("enabled", True) else None
        else:
            self.hover = None

    def on_click(self, pos):
        """左键抬起 → 返回要执行的动作键；返回 None = 只是翻页或收起菜单。"""
        if self._close_rect().collidepoint(pos):
            self.close()
            return None
        it = self._at(pos)
        if it is None:
            _items, h = self.layout()
            if pygame.Rect(self.PANEL_X, self.PANEL_Y,
                           self.PANEL_W, h).collidepoint(pos):
                return None            # 卡片里的空白：菜单留着，别误关
            self.close()               # 卡片外面（窗口下沿那块空白）：收起
            return None
        if not it.get("enabled", True):
            return None                # 灰掉的项点不动
        key = it["key"]
        if it["kind"] == "chip":
            if key.startswith("__custom__"):
                self.input_mode = key.split(":", 1)[1]   # 展开输入框接着敲
                self.input_text = ""
                return None
            if key.startswith("todo_text:"):
                self.todo_text = key[len("todo_text:"):]  # 只是挑内容，还得挑时间
                return None
            self.close()
            return key
        if key.startswith("nav:"):
            self.page = key[4:]
            self.stack.append(self.page)
            self.hover = None
            self.input_mode = None
            return None
        if key == "back":
            if len(self.stack) > 1:
                self.stack.pop()
            self.page = self.stack[-1]
            self.hover = None
            self.input_mode = None
            return None
        self.close()
        return key

    def on_key(self, e):
        """键盘：Esc 收起（输入中先退出输入），回车确定输入框里的内容。"""
        if e.key == pygame.K_ESCAPE:
            if self.input_mode:
                self.input_mode = None
                self.input_text = ""
            else:
                self.close()
            return None
        if self.input_mode and e.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            return self._commit_input()
        if self.input_mode and e.key == pygame.K_BACKSPACE:
            self.input_text = self.input_text[:-1]
        return None

    def on_text(self, text):
        """文字输入：时长只收数字，待办内容随便写。"""
        if not self.input_mode:
            return
        digits = self.input_mode in ("pomo_work", "todo_mins")
        limit = 4 if digits else TODO_TEXT_MAX
        for ch in text:
            if not ch.isprintable() or len(self.input_text) >= limit:
                continue
            if digits and not ch.isdigit():
                continue
            self.input_text += ch

    def _commit_input(self):
        """输入框回车：按当前是哪种输入决定后续。"""
        mode, text = self.input_mode, self.input_text.strip()
        self.input_mode = None
        self.input_text = ""
        if mode == "pomo_work":
            if not text.isdigit():
                return None
            m = max(POMO_WORK_MIN, min(POMO_WORK_MAX, int(text)))
            self.close()
            return "pomo_work:%d" % m
        if mode == "todo_text":
            if text:
                self.todo_text = text[:TODO_TEXT_MAX]
            return None                # 不关菜单：内容定了，接着挑提醒时间
        if mode == "todo_mins":
            if not text.isdigit():
                return None
            mins = max(TODO_MINS_MIN, min(TODO_MINS_MAX, int(text)))
            self.close()
            return "todo:add:%d" % mins
        return None

    # ---- 绘制 ----
    def _close_rect(self):
        return pygame.Rect(self.PANEL_X + self.PANEL_W - 32, self.PANEL_Y + 6, 24, 24)

    def _avatar(self):
        """标题栏上的圆头像：从原立绘上裁一块"脸"。

        不能整张缩：会变成一根小人干。也不能用 Frames 里那张——它已经按
        窗口尺寸拉伸过（比例变了）。所以直接读 512 的原图，按比例取脸那一块，
        看起来才像她本人。
        """
        if self._ava != -1:
            return self._ava
        self._ava = None
        try:
            src = os.path.join(IMG_DIR, "base_idle.png")
            img = (pygame.image.load(src).convert_alpha()
                   if os.path.exists(src) else self.app.frames.get(Pet.IDLE))
            w, h = img.get_size()
            side = int(w * 0.30)
            rect = pygame.Rect(int(w * 0.455) - side // 2, int(h * 0.05),
                               side, side).clip(img.get_rect())
            crop = pygame.transform.smoothscale(img.subsurface(rect).copy(), (30, 30))
            out = pygame.Surface((30, 30), pygame.SRCALPHA)
            out.blit(crop, (0, 0))
            mask = pygame.Surface((30, 30), pygame.SRCALPHA)
            pygame.draw.circle(mask, (255, 255, 255, 255), (15, 15), 15)
            out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self._ava = out
        except Exception:
            self._ava = None
        return self._ava

    def draw(self, surf):
        """把整个菜单画进窗口 surface，返回面板矩形（窗口区域要用）。"""
        items, panel_h = self.layout()
        panel = pygame.Rect(self.PANEL_X, self.PANEL_Y, self.PANEL_W, panel_h)
        font_t = self.app._get_font(16)
        font_i = self.app._get_font(14)
        font_s = self.app._get_font(11)

        # 卡片：柔和阴影 + 奶白底 + 粉描边（和台词气泡一个调子）
        pygame.draw.rect(surf, self.C_SHADOW, panel.move(2, 4), border_radius=16)
        pygame.draw.rect(surf, self.C_PANEL, panel, border_radius=16)
        head = pygame.Rect(panel.x + 2, panel.y + 2, panel.w - 4, self.HEAD_H - 3)
        pygame.draw.rect(surf, self.C_HEAD, head,
                         border_top_left_radius=14, border_top_right_radius=14)
        pygame.draw.rect(surf, self.C_EDGE, panel, 2, border_radius=16)

        # 头像 + 标题
        ava = self._avatar()
        if ava is not None:
            surf.blit(ava, (panel.x + 9, panel.y + 4))
            pygame.draw.circle(surf, self.C_EDGE, (panel.x + 24, panel.y + 19), 15, 2)
        title = font_t.render(self.PAGE_TITLE.get(self.page, APP_NAME),
                              True, self.C_PINK_DK)
        surf.blit(title, (panel.x + 46, panel.y + 11))

        # 右上角关闭小圆
        cr = self._close_rect()
        hi = self.hover == "__close__"
        pygame.draw.circle(surf, (255, 199, 221) if hi else (252, 235, 243),
                           cr.center, 10)
        cx, cy = cr.center
        pygame.draw.line(surf, self.C_PINK_DK, (cx - 4, cy - 4), (cx + 4, cy + 4), 2)
        pygame.draw.line(surf, self.C_PINK_DK, (cx + 4, cy - 4), (cx - 4, cy + 4), 2)

        for it in items:
            self._draw_row(surf, it, font_i, font_s)
        return panel

    def _draw_row(self, surf, it, font_i, font_s):
        kind, r = it["kind"], it["rect"]
        if kind == "sep":
            pygame.draw.line(surf, self.C_SEP, (r.x, r.centery),
                             (r.right, r.centery), 2)
            return
        if kind == "text":
            t = font_s.render(it["label"], True, (156, 126, 142))
            surf.blit(t, (r.x + 2, r.centery - t.get_height() // 2))
            return
        if kind == "note":
            # 待办清单的一条：小一号、再淡一点，跟可点的项区分开
            t = font_s.render(it["label"], True, (176, 146, 162))
            surf.blit(t, (r.x + 4, r.centery - t.get_height() // 2))
            return
        if kind == "chips":
            return
        if kind == "bar":
            total = max(1, int(getattr(self.app.pet, "pomodoro_work_secs", 0)))
            done = 1.0 - self.app.pet.pomodoro_left() / total
            done = max(0.0, min(1.0, done))
            pygame.draw.rect(surf, (252, 228, 238), r, border_radius=4)
            if done > 0:
                pygame.draw.rect(surf, self.C_PINK,
                                 pygame.Rect(r.x, r.y, max(4, int(r.w * done)), r.h),
                                 border_radius=4)
            return
        if kind == "chip":
            on = it["checked"]
            pygame.draw.rect(surf, self.C_PINK if on else (255, 255, 255, 255),
                             r, border_radius=9)
            pygame.draw.rect(surf, self.C_PINK, r, 1, border_radius=9)
            t = font_s.render(it["label"], True,
                              (255, 255, 255) if on else self.C_PINK_DK)
            surf.blit(t, (r.centerx - t.get_width() // 2,
                          r.centery - t.get_height() // 2))
            return
        if kind == "input":
            pygame.draw.rect(surf, (255, 255, 255, 255), r, border_radius=9)
            pygame.draw.rect(surf, self.C_PINK, r, 2, border_radius=9)
            suffix = {"pomo_work": " 分钟", "todo_mins": " 分钟后提醒",
                      "todo_text": ""}.get(self.input_mode, "")
            t = font_i.render(self.input_text + "|" + suffix, True, (150, 88, 122))
            surf.blit(t, (r.x + 10, r.centery - t.get_height() // 2))
            return
        if kind == "tip":
            t = font_s.render(it["label"], True, (176, 146, 162))
            surf.blit(t, (r.x + 2, r.y))
            return
        # ---- 普通项 ----
        key, on = it["key"], it.get("enabled", True)
        hi = on and key is not None and self.hover == key
        ink = self.C_PINK_DK if on else self.C_TEXT_OFF
        if hi:
            pygame.draw.rect(surf, self.C_HOVER, r, border_radius=9)
            pygame.draw.rect(surf, (252, 216, 232), r, 1, border_radius=9)
        col = self.C_TEXT_HI if hi else (self.C_TEXT if on else self.C_TEXT_OFF)
        tx = r.x + 10
        if it["mark"] in ("back", "radio"):
            cx, cy = r.x + 15, r.centery
            if it["mark"] == "back":
                pygame.draw.line(surf, ink, (cx + 4, cy - 5), (cx - 3, cy), 2)
                pygame.draw.line(surf, ink, (cx - 3, cy), (cx + 4, cy + 5), 2)
            elif it["checked"]:
                pygame.draw.circle(surf, self.C_PINK, (cx, cy), 6)
                pygame.draw.circle(surf, (255, 255, 255), (cx, cy), 2)
            else:
                pygame.draw.circle(surf, (238, 205, 222), (cx, cy), 6, 2)
            tx = r.x + 28
        t = font_i.render(it["label"], True, col)
        surf.blit(t, (tx, r.centery - t.get_height() // 2))
        if it["mark"] == "arrow":
            cx, cy = r.right - 14, r.centery
            pygame.draw.polygon(surf, ink,
                                [(cx - 3, cy - 5), (cx + 3, cy), (cx - 3, cy + 5)])
        elif it["mark"] == "check" and it["checked"]:
            cx, cy = r.right - 16, r.centery
            pygame.draw.lines(surf, self.C_PINK_DK, False,
                              [(cx - 5, cy), (cx - 1, cy + 4), (cx + 5, cy - 5)], 3)


# ---------------------------------------------------------------------------
# 到点提醒（番茄钟结束 / 待办到点）
# ---------------------------------------------------------------------------
class Alert:
    """到点提醒卡片 —— 常驻、显眼、不点它不消失。

    为什么不再只让气泡说一句话：气泡只在屏幕上挂几秒，人一低头看代码就
    彻底错过；贴边（默认就是贴屏幕右边缘）时窗口还会被 SetWindowRgn 裁成
    一条轮廓，气泡能不能露出来全看运气。
    所以改成一张卡片：
      · 大标题 + 正文 + 两个按钮，一眼看出"谁、什么事、现在该干嘛"
      · 每隔几秒轻轻"叮"一声（最多 6 声），吵的话能在设置里关掉
      · 不点「知道啦」就一直挂在窗口上 —— 这才是"明显"的关键
      · 卡片占窗口上半部，同时把她缩到 0.6 倍挪到下半部，互不遮挡

    画在哪儿：还是桌宠自己的窗口（240x300），不另外开窗口。
    因为贴边时窗口区域被裁过，这里会把【卡片 + 她】两块矩形并进窗口区域，
    卡片才显示得出来、也点得到（其余空白继续鼠标穿透）。
    """

    ALIAS = {"pomo": "SystemExclamation", "break": "SystemAsterisk",
             "todo": "SystemExclamation"}

    W = WIN_W - 24            # 卡片宽 216
    X = 12
    Y = 8
    PAD = 10
    HEAD_H = 24
    LINE_H = 18
    BTN_H = 28
    BTN_GAP = 8

    # 配色跟台词气泡、右键菜单同一套（奶白 + 粉），放一起才像"一个人"
    C_PANEL = (255, 252, 254, 253)
    C_HEAD = (250, 168, 204, 255)
    C_EDGE = (233, 118, 168, 255)
    C_TEXT = (108, 76, 94)
    C_SHADOW = (226, 126, 172, 80)
    C_BTN = (246, 158, 198, 255)
    C_BTN_HI = (231, 118, 170, 255)

    def __init__(self, app):
        self.app = app
        self.active = False
        self.kind = "pomo"
        self.title = ""
        self.text = ""
        self.icon = "clock"
        self.buttons = []          # [(按钮文案, 动作键)]
        self.payload = None        # 待办提醒带着"哪几条到点了"
        self.hover = None
        self.born = 0.0
        self.beeps = 0
        self._next_beep = 0.0

    # ---- 弹出 / 收起 ----
    def show(self, kind, title, text, buttons, icon="clock", payload=None):
        if self.app.menu.open:
            self.app.menu.close()     # 菜单给提醒让位，别两层卡片叠着
        self.active = True
        self.kind = kind
        self.title = title
        self.text = text
        self.icon = icon
        self.buttons = list(buttons)
        self.payload = payload
        self.hover = None
        now = _now()
        self.born = now
        self.beeps = 0
        self._next_beep = now        # 立刻先"叮"第一声
        pet = self.app.pet
        pet.alert_hold = True        # 期间别再自己换姿势/乱动
        if pet.state in pet.EDGE_POSE.values():
            # 贴边时她只有半个身子探在外面，表情看不清 —— 提醒时先"转出来站好"
            pet.set_state(pet.HAPPY, 9999)
        pet.bounce = 1.0             # 弹一下，动静大一点
        self.app._log("[提醒] %s：%s" % (kind, title))

    def close(self):
        if not self.active:
            return
        self.active = False
        self.hover = None
        self.app.pet.back_from_alert()

    def tick(self, now):
        """每帧一次：隔几秒"叮"一声，响够次数就安静（但卡片还挂着）。"""
        if not self.active:
            return
        if self.beeps >= ALERT_BEEP_MAX or now < self._next_beep:
            return
        self.beeps += 1
        self._next_beep = now + ALERT_BEEP_GAP
        if self.app.data.alert_sound:
            _play_sound(self.ALIAS.get(self.kind, "SystemAsterisk"))

    # ---- 布局（每帧算：正文行数会随文字长度变）----
    def _wrap(self, font, text, width):
        lines, cur = [], ""
        for ch in text:
            if cur and font.size(cur + ch)[0] > width:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
        return lines

    def rects(self):
        """返回 (卡片矩形, [按钮矩形], 正文行)。"""
        font_b = self.app._get_font(12)
        body = self._wrap(font_b, self.text, self.W - self.PAD * 2)
        h = (self.PAD + self.HEAD_H + 4 + len(body) * self.LINE_H
             + 8 + self.BTN_H + self.PAD)
        card = pygame.Rect(self.X, self.Y, self.W, h)
        n = max(1, len(self.buttons))
        bw = (self.W - self.PAD * 2 - self.BTN_GAP * (n - 1)) // n
        by = card.bottom - self.PAD - self.BTN_H
        btns = [pygame.Rect(card.x + self.PAD + i * (bw + self.BTN_GAP), by, bw,
                            self.BTN_H) for i in range(n)]
        return card, btns, body

    def hit(self, pos):
        card, _b, _t = self.rects()
        return self.active and card.collidepoint(pos)

    def on_click(self, pos):
        """返回点到的按钮动作键；点在卡片空白处返回 None（卡片留着，别误关）。"""
        _card, btns, _body = self.rects()
        for r, (_label, key) in zip(btns, self.buttons):
            if r.collidepoint(pos):
                return key
        return None

    def on_move(self, pos):
        _card, btns, _body = self.rects()
        self.hover = None
        for r, (_l, key) in zip(btns, self.buttons):
            if r.collidepoint(pos):
                self.hover = key

    # ---- 绘制 ----
    def draw(self, surf):
        card, btns, body = self.rects()
        font_t = self.app._get_font(14)
        font_b = self.app._get_font(12)
        pulse = 0.5 + 0.5 * math.sin((_now() - self.born) * 5.0)

        pygame.draw.rect(surf, self.C_SHADOW, card.move(2, 4), border_radius=15)
        pygame.draw.rect(surf, self.C_PANEL, card, border_radius=15)
        head = pygame.Rect(card.x + 2, card.y + 2, card.w - 4, self.HEAD_H)
        pygame.draw.rect(surf, self.C_HEAD, head,
                         border_top_left_radius=13, border_top_right_radius=13)
        pygame.draw.rect(surf, self.C_EDGE, card, 2, border_radius=15)

        # 标题带左侧的小图标（闹钟 / 铃铛），不让它只是一块色条
        icx, icy = head.x + 15, head.centery
        if self.icon == "bell":
            pygame.draw.circle(surf, (255, 255, 255), (icx, icy + 1), 7)
            pygame.draw.rect(surf, (255, 255, 255), (icx - 7, icy + 2, 14, 3))
            pygame.draw.circle(surf, (255, 255, 255), (icx, icy + 7), 2)
        else:
            pygame.draw.circle(surf, (255, 255, 255), (icx, icy), 8)
            pygame.draw.line(surf, self.C_EDGE, (icx, icy), (icx, icy - 5), 2)
            pygame.draw.line(surf, self.C_EDGE, (icx, icy), (icx + 4, icy), 2)

        ti = font_t.render(self.title, True, (255, 255, 255))
        surf.blit(ti, (head.x + 30, head.centery - ti.get_height() // 2))

        y = card.y + self.PAD + self.HEAD_H + 4
        for line in body:
            tx = font_b.render(line, True, self.C_TEXT)
            surf.blit(tx, (card.x + self.PAD, y))
            y += self.LINE_H

        for r, (label, key) in zip(btns, self.buttons):
            primary = (key != "ok")     # 左边的实心按钮是"建议你做的事"
            hi = self.hover == key
            if primary:
                pygame.draw.rect(surf, self.C_BTN_HI if hi else self.C_BTN,
                                 r, border_radius=9)
                ink = (255, 255, 255)
            else:
                pygame.draw.rect(surf, (255, 238, 246) if hi else (255, 250, 252),
                                 r, border_radius=9)
                pygame.draw.rect(surf, self.C_EDGE, r, 1, border_radius=9)
                ink = self.C_EDGE
            tx = font_b.render(label, True, ink)
            surf.blit(tx, (r.centerx - tx.get_width() // 2,
                           r.centery - tx.get_height() // 2))

        if pulse > 0.55:               # 描边轻微呼吸，扫一眼就知道有东西在等你
            pygame.draw.rect(surf, (255, 214, 232, 200), card, 2, border_radius=15)
        return card


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------
class App:
    def __init__(self):
        self.data = PetData()
        self._work = None             # 工作区缓存
        self._work_at = 0
        self._pending_edge = None     # 托盘改了"启动位置"，交给主循环执行（不能跨线程绘制）
        self._pending_auto = None     # 托盘改了"自动变化"间隔，同样交给主循环
        self._pending_pomo = None     # 托盘改了"专注时长"，同样交给主循环
        self._apply_startup_pos()     # 启动落位：贴到设定好的那条屏幕边（默认右边缘）

        # 让 SDL 创建窗口时就直接落在目标位置，避免开机瞬间先闪一下屏幕中间
        os.environ["SDL_VIDEO_WINDOW_POS"] = "%d,%d" % self.data.pos
        pygame.init()
        self.voice = Voice()
        self.pet = Pet(self.data, self.voice)
        self.detector = GameDetector()

        # 无边框窗口
        self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.NOFRAME)
        pygame.display.set_caption(APP_NAME)
        self.frames = Frames()
        self.hwnd = pygame.display.get_wm_info().get("window")
        self._make_transparent()
        self._set_topmost()

        self.clock = pygame.time.Clock()
        self.running = True
        self.visible = True
        self.dragging = False
        self._down = (0, 0)
        self._moved = False
        self._grab_global = (0, 0)    # 按下时的屏幕绝对坐标
        self._grab_offset = (0, 0)    # 光标相对窗口左上角的偏移
        self._last_todo_check = 0
        self._last_img = None         # 最近一次绘制用的图（用于点击穿透判定）
        self._last_pos = (0, 0)
        self._last_alert = None       # 提醒卡片 + 她所在的两块矩形（自测要看）
        self._sil_cache = {}          # 各状态的角色轮廓（窗口区域用）
        self._region_key = None
        self._hrgn = None             # 保存 region 句柄，防止被回收
        self._last_bubble = None      # 气泡矩形（右键菜单命中范围要用）
        self._pending_menu = None     # 右键菜单选中了哪一项，交给主循环执行
        self._show_at = 0             # "躲起来一会儿"的到点时间（0 = 没在躲）
        self._hide_at = 0             # 说完那句"我先躲一下"之后才真的藏起来
        self.menu = PetMenu(self)
        self.alert = Alert(self)
        self.pet.notify = self._pet_notify   # 她那边"到点了"就报过来
        self._apply_edge(snap=True)   # 启动时若位置贴边，直接进贴边姿势
        self._win_pos = self.data.pos  # 真正提交给窗口的位置（菜单打开时会临时挪一下）
        self.data.save()              # 把实际落位写回存档

        threading.Thread(target=Tray(self).start, daemon=True).start()

    # ---- 启动落位 ----
    def _apply_startup_pos(self):
        """按存档里的"启动位置"决定开机后她在哪。

        默认贴屏幕右边缘；垂直方向沿用上次的位置（换了分辨率/显示器跑出屏幕
        就自动居中）。把设置改成"记住上次位置"就完全按存档坐标恢复。
        """
        wl, wt, wr, wb = self.work_area()
        side = self.data.start_edge
        x, y = self.data.pos
        if side in ("left", "right", "top", "bottom"):
            self._snap_to_edge(side)
            x, y = self.data.pos
            if side in ("left", "right"):
                if not (wt <= y <= wb - WIN_H):
                    y = wt + max(0, (wb - wt - WIN_H) // 2)
            else:
                if not (wl <= x <= wr - WIN_W):
                    x = wl + max(0, (wr - wl - WIN_W) // 2)
        else:
            # 记住上次位置：保证窗口至少有一部分留在工作区里
            x = max(wl - EDGE_LIMIT, min(x, wr - WIN_W + EDGE_LIMIT))
            y = max(wt - EDGE_LIMIT, min(y, wb - WIN_H + EDGE_LIMIT))
        self.data.pos = (int(x), int(y))

    def set_start_edge(self, side):
        """托盘菜单用：设置开机落位。实际搬窗口交给主循环做（跨线程不能绘制）。"""
        self.data.start_edge = side
        self._pending_edge = side

    def set_auto_secs(self, secs):
        """托盘菜单用：设置"自动变化"的间隔（秒，0 = 关闭）。"""
        self.data.auto_secs = int(secs)
        self._pending_auto = int(secs)

    def set_pomo_work(self, mins):
        """菜单/托盘用：设置番茄钟的专注时长（分钟，1~180）。

        只对"下一次开始专注"生效——正在跑的那一轮不打断，免得人正看着
        倒计时，时长忽然被改了。落盘和回话交给主循环做。
        """
        m = max(POMO_WORK_MIN, min(POMO_WORK_MAX, int(mins)))
        self.data.pomo_work = m
        self._pending_pomo = m

    # ---- Win32 透明窗口（逐像素 alpha 分层窗口）----
    def _make_transparent(self):
        """设置 WS_EX_LAYERED，后续每帧用 UpdateLayeredWindow 提交带 alpha 的像素。"""
        if sys.platform != "win32" or not self.hwnd:
            return
        import ctypes
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x80000
        ex = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)

    def _update_layered(self, surf):
        """把 pygame SRCALPHA surface 以逐像素 alpha 提交给窗口（真透明）。

        同时用 pptDst 指定窗口左上角屏幕坐标——分层窗口必须用本函数移动，
        不能用 SetWindowPos（否则位置不同步导致拖拽漂移/残影）。
        """
        if sys.platform != "win32" or not self.hwnd:
            return
        import ctypes
        from ctypes import wintypes

        class BLENDFUNCTION(ctypes.Structure):
            _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                        ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        w, h = surf.get_size()

        # 取出 RGBA 字节：预乘 alpha + R/B 通道交换
        # （Windows UpdateLayeredWindow 的 32bpp DIB 字节序是 B-G-R-A，
        #  pygame tobytes("RGBA") 是 R-G-B-A，不交换会粉变蓝！）
        raw = pygame.image.tobytes(surf, "RGBA")
        buf = bytearray(raw)
        for i in range(0, len(buf), 4):
            a = buf[i + 3]
            r, b = buf[i], buf[i + 2]
            if a != 255:
                r = r * a // 255
                b = b * a // 255
                buf[i + 1] = buf[i + 1] * a // 255
            buf[i] = b          # B
            buf[i + 2] = r      # R
        cbuf = (ctypes.c_ubyte * len(buf)).from_buffer_copy(bytes(buf))

        # 创建 32bpp 顶层 DIB
        class BMIHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                        ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        bi = BMIHEADER()
        bi.biSize = ctypes.sizeof(BMIHEADER)
        bi.biWidth = w
        bi.biHeight = -h          # 负值 = 自上而下
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0      # BI_RGB

        hdc_screen = user32.GetDC(None)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        bits = ctypes.c_void_p()
        hbm = gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bi), 0,
                                     ctypes.byref(bits), None, 0)
        ctypes.memmove(bits, cbuf, len(buf))
        gdi32.SelectObject(hdc_mem, hbm)

        px, py = int(self._win_pos[0]), int(self._win_pos[1])
        pt_dst = wintypes.POINT(px, py)
        pt_src = wintypes.POINT(0, 0)
        size = wintypes.SIZE(w, h)
        bf = BLENDFUNCTION(0, 0, 255, 1)   # AC_SRC_OVER, 不透明度255, AC_SRC_ALPHA
        ok = user32.UpdateLayeredWindow(self.hwnd, hdc_screen, ctypes.byref(pt_dst),
                                        ctypes.byref(size), hdc_mem,
                                        ctypes.byref(pt_src), 0,
                                        ctypes.byref(bf), 2)  # ULW_ALPHA=2
        if not ok:
            err = ctypes.get_last_error()
            if not hasattr(self, "_ulw_err"):
                self._ulw_err = True
                print("UpdateLayeredWindow 失败, GetLastError =", err)

        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)

    def _set_topmost(self):
        if self.hwnd and sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.SetWindowPos(self.hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)

    def set_visible(self, v):
        if self.visible == v:
            return
        self.visible = v
        if self.hwnd and sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.ShowWindow(self.hwnd, 5 if v else 0)

    def toggle_visible(self):
        self.set_visible(not self.visible)

    def hide_for(self, secs):
        """右键菜单：临时躲起来一会儿，到点自己回来。

        先说一句再躲——直接消失会让人以为程序崩了。
        也不提供"永久隐藏"：她一旦藏起来就点不到她了，
        想找回来只能去托盘图标，容易让人以为她挂了。
        """
        self.voice.say("hide", 1.5)
        self._hide_at = _now() + 1.5
        self._show_at = _now() + 1.5 + secs

    # ---- 右键菜单命令（在主循环里执行，能安全搬窗口/画帧）----
    def _tick_visibility(self, now):
        """"躲起来一会儿"的计时：先把那句话说完，再真的藏起来，到点自己回来。"""
        if self._hide_at and now >= self._hide_at:
            self._hide_at = 0
            self.set_visible(False)
        if self._show_at and now >= self._show_at:
            self._show_at = 0
            self.set_visible(True)
            self.voice.say("back", 3.0)

    # ---- 到点提醒：她报事 → 弹卡片 → 点完按钮再收尾 ----
    def _pet_notify(self, kind, payload=None):
        """Pet 那边"到点了"就报到这里，统一弹一张卡片。

        为什么绕一圈：Pet 只管"到没到点"，窗口、卡片、音效都是 App 的事；
        分开之后自测可以只塞一个假的回调，不用真的等 25 分钟。
        """
        if kind == "pomo_done":
            m = int(payload or self.data.pomo_work)
            self.alert.show(
                "pomo", "专注结束啦！",
                "%d 分钟专注完成，起来活动一下、看看远处吧～" % m,
                [("休息 5 分钟", "break"), ("知道啦", "ok")], icon="clock")
        elif kind == "break_done":
            self.alert.show(
                "break", "休息结束～",
                "元气恢复！要接着专注一轮吗？",
                [("继续专注", "work"), ("知道啦", "ok")], icon="clock")
        elif kind == "todo_due":
            fired = list(payload or [])
            if not fired:
                return
            first = fired[0].get("text", "待办")
            body = ("该做啦：%s" % first if len(fired) == 1
                    else "到点 %d 条：%s 等" % (len(fired), first))
            self.alert.show(
                "todo", "待办时间到！", body,
                [("再等 %d 分钟" % (SNOOZE_SECS // 60), "snooze"), ("知道啦", "ok")],
                icon="bell", payload=fired)

    def _resolve_alert(self, key):
        """提醒卡片上按了按钮（或她"知道啦"）：先收卡片，再做按钮的事。

        待办到点后【不会自动消失】：只有"知道啦"才划掉，"再等 10 分钟"就
        把时间往后挪 —— 以前是响一下就把条目删了，没看到就永远错过了。
        """
        a = self.alert
        kind, payload = a.kind, a.payload
        a.close()
        if kind in ("pomo", "break"):
            if key == "break":
                self.pet.start_break()
            elif key == "work":
                self.pet.start_pomodoro()
            return
        if kind == "todo":
            fired = list(payload or [])
            if key == "snooze":
                for t in fired:
                    t["due"] = _now() + SNOOZE_SECS
                self.voice.say_text("好～那我 %d 分钟后再提醒你" % (SNOOZE_SECS // 60),
                                    3.0)
            else:
                self.data.todos = [t for t in self.data.todos
                                   if not any(t is f for f in fired)]
                self.voice.say_text("好嘞，划掉啦～辛苦啦！", 2.5)
            self.data.save()

    def _do_menu(self, key):
        if key == "pat":
            self.pet.on_click()
        elif key == "feed":
            self.pet.feed()
        elif key == "hide":
            self.hide_for(HIDE_SECS)
        elif key == "pomodoro:start":
            self.pet.start_pomodoro()
        elif key == "pomodoro:stop":
            self.pet.stop_pomodoro()
        elif key.startswith("todo:add:"):
            mins = int(key[len("todo:add:"):])
            self.pet.add_todo(self.menu.todo_text, _now() + mins * 60)
        elif key == "todo:clear":
            n = len(self.data.todos)
            self.data.todos = []
            self.data.save()
            self.voice.say_text("待办都清掉啦（%d 条）～" % n, 3.0)
        elif key == "alert_sound":
            self.data.alert_sound = not self.data.alert_sound
            self.data.save()
            if self.data.alert_sound:
                _play_sound("SystemAsterisk")
                self.voice.say_text("好～到点我会「叮」你一下", 3.0)
            else:
                self.voice.say_text("好，那我安安静静地提醒你", 3.0)
        elif key == "autostart":
            self.toggle_autostart()
        elif key == "about":
            self.voice.say_text(
                "%s %s ｜ 好感度 %d ｜ 待办 %d 条 ｜ 每 %s 自己动一下 ｜ 专注 %d 分钟"
                % (APP_NAME, VERSION, self.data.affection, len(self.data.todos),
                   dict(AUTO_CHOICES).get(self.data.auto_secs,
                                          "%d 秒" % self.data.auto_secs),
                   self.data.pomo_work),
                5.0)
        elif key == "quit":
            self.quit()
        elif key.startswith("pomo_work:"):
            self.set_pomo_work(int(key[10:]))
        elif key.startswith("pose:"):
            name = key[5:]
            if name == "random":
                self.pet.random_pose()
                return
            poses = {"squat": (self.pet.SQUAT, "squat"),
                     "sit": (self.pet.SIT, "sit"),
                     "prone": (self.pet.PRONE, "prone"),
                     "lie": (self.pet.LIE, "lie"),
                     "stretch": (self.pet.STRETCH, "stretch"),
                     "wave": (self.pet.WAVE, "greet")}
            if name in poses:
                self.pet.pose_once(*poses[name])
        elif key.startswith("auto:"):
            self.set_auto_secs(int(key[5:]))
        elif key.startswith("edge:"):
            self.set_start_edge(key[5:])

    def toggle_autostart(self, icon=None):
        """切换开机自启（托盘菜单项）。"""
        on = not autostart_enabled()
        ok, msg = set_autostart(on)
        self.voice.say_text(msg, 3.5)
        if icon is not None:
            try:
                icon.notify(msg, APP_NAME)
                icon.update_menu()
            except Exception:
                pass
        print("[自启] %s" % msg)
        return ok

    # ---- 屏幕（工作区）边缘：贴边姿势 ----
    def work_area(self):
        """可用桌面区域 (left, top, right, bottom)——已排除任务栏/停靠栏。"""
        now = time.time()
        if self._work and now - self._work_at < 5:
            return self._work
        r = (0, 0, 1920, 1080)
        if sys.platform == "win32":
            try:
                from ctypes import wintypes
                rc = wintypes.RECT()
                if ctypes.windll.user32.SystemParametersInfoW(
                        0x0030, 0, ctypes.byref(rc), 0):   # SPI_GETWORKAREA
                    r = (rc.left, rc.top, rc.right, rc.bottom)
            except Exception:
                pass
        self._work, self._work_at = r, now
        return r

    def _edge_dists(self):
        """窗口当前位置到"四条边贴边位"的距离。"""
        wl, wt, wr, wb = self.work_area()
        x, y = self.data.pos
        return {
            "left":   abs(x - (wl - EDGE_OVERLAP)),
            "right":  abs(x - (wr - WIN_W + EDGE_OVERLAP)),
            "top":    abs(y - (wt - EDGE_OVERLAP)),
            "bottom": abs(y - (wb - WIN_H + EDGE_OVERLAP)),
        }

    def _detect_edge(self):
        """判断当前贴在哪条边（不贴边返回 None）。带一点滞回，避免角落来回跳。"""
        d = self._edge_dists()
        best = min(d, key=d.get)
        if d[best] > EDGE_BAND:
            return None
        cur = self.pet.edge
        if cur and d[cur] <= EDGE_BAND and d[cur] - d[best] <= 8:
            return cur          # 滞回：当前这条边仍成立就别换
        return best

    def _snap_to_edge(self, side):
        """把窗口严丝合缝地贴到对应边（含 EDGE_OVERLAP 的让位）。"""
        wl, wt, wr, wb = self.work_area()
        x, y = self.data.pos
        if side == "left":
            x = wl - EDGE_OVERLAP
        elif side == "right":
            x = wr - WIN_W + EDGE_OVERLAP
        elif side == "top":
            y = wt - EDGE_OVERLAP
        elif side == "bottom":
            y = wb - WIN_H + EDGE_OVERLAP
        self.data.pos = (int(x), int(y))

    def _apply_edge(self, snap=True):
        """每帧调用：贴边 → 吸附位置 + 换成贴边姿势；离开 → 回到普通待机。"""
        side = self._detect_edge()
        if side and snap and not self.dragging:
            self._snap_to_edge(side)
        self.pet.set_edge(side)

    def quit(self):
        self.running = False

    # ---- 拖动所需：屏幕绝对坐标 + 鼠标捕获 ----
    def _get_cursor_pos(self):
        """取光标的【屏幕绝对坐标】。这是拖动平滑的关键——
        绝对坐标与窗口位置无关，不会形成"窗口动→相对坐标变→再动窗口"的振荡。
        """
        if sys.platform == "win32":
            from ctypes import wintypes
            pt = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            return (pt.x, pt.y)
        return pygame.mouse.get_pos()

    def _cursor_local(self):
        """光标在窗口内的坐标 = 屏幕绝对坐标 - 当前窗口位置。

        不用 pygame 事件里的 e.pos：鼠标跑到窗口外（贴边、拖动）时它不一定
        跟着更新，用系统光标换算更稳。
        """
        gx, gy = self._get_cursor_pos()
        return (int(gx) - int(self._win_pos[0]), int(gy) - int(self._win_pos[1]))

    def _set_capture(self, on):
        """拖动时捕获鼠标，保证光标移出窗口也能收到松手事件（同系统拖窗行为）。"""
        if sys.platform == "win32" and self.hwnd:
            if on:
                ctypes.windll.user32.SetCapture(self.hwnd)
            else:
                ctypes.windll.user32.ReleaseCapture()

    def _log(self, msg):
        """调试日志：写入 data/event.log，用于诊断拖动事件流。"""
        try:
            with open(os.path.join(DATA_DIR, "event.log"), "a", encoding="utf-8") as f:
                f.write("[%d.%03d] %s\n" % (time.time(), (time.time()*1000)%1000, msg))
        except Exception:
            pass

    def _hit_character(self, gx, gy):
        """点击是否落在角色身上（按 alpha 判定）。

        贴边姿势只占窗口一条边，窗口其余部分是空的；如果不判定，
        用户点到那一片"空气"也会把桌宠抓起来。透明处直接不响应。
        """
        if self._last_img is None:
            return True
        lx = gx - self.data.pos[0] - self._last_pos[0]
        ly = gy - self.data.pos[1] - self._last_pos[1]
        try:
            if 0 <= lx < self._last_img.get_width() and 0 <= ly < self._last_img.get_height():
                return self._last_img.get_at((lx, ly))[3] > 24
        except Exception:
            return True
        return False

    def _hit_pet(self, gx, gy):
        """右键菜单的命中范围：角色本体 + 正在显示的台词气泡。

        气泡画在窗口里、不在 _last_img 上，所以要单独算一次，
        否则她正在说话时右键点气泡会没反应。
        """
        if self._hit_character(gx, gy):
            return True
        b = self._last_bubble
        if b:
            lx = gx - self.data.pos[0]
            ly = gy - self.data.pos[1]
            return b[0] <= lx < b[2] and b[1] <= ly < b[3]
        return False

    # ---- 窗口区域：贴边时空白处鼠标穿透 ----
    def _silhouette(self, state):
        """某个状态图像的逐行左右边界（图像局部坐标），用于生成窗口区域。"""
        if state in self._sil_cache:
            return self._sil_cache[state]
        img = self.frames.get(state)
        w, h = img.get_size()
        raw = pygame.image.tobytes(img, "RGBA")
        rows = []
        for y in range(h):
            a = raw[y * w * 4 + 3: (y + 1) * w * 4: 4]
            x0 = x1 = -1
            for i, v in enumerate(a):
                if v > 24:
                    if x0 < 0:
                        x0 = i
                    x1 = i
            if x0 >= 0:
                rows.append((y, x0, x1))
        self._sil_cache[state] = rows
        return rows

    def _apply_window_region(self, state, blit, bubble_rect, menu_rect=None,
                             alert_boxes=None):
        """把窗口形状裁成角色轮廓、菜单面板或提醒卡片。

        【所有姿势】都裁成角色轮廓：立绘缩到 PET_SCALE 之后，窗口四周留了一圈
        看不见的边距，不裁的话这一圈会把底下（浏览器标签、桌面图标…）的鼠标点击
        吃掉。裁剪后空白处直接穿透，点哪儿是哪儿。

        菜单打开时要反过来：整窗得恢复成矩形，否则菜单会被轮廓切掉；
        顺带把区域缩成面板本身，面板下面那块空白继续穿透。

        提醒卡片同理：卡片 + 她站在窗口下半边的那块地方，两个矩形并起来。
        """
        if sys.platform != "win32" or not self.hwnd:
            return
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        if menu_rect is not None:
            key = ("menu", menu_rect.width, menu_rect.height)
            if key == self._region_key:
                return
            self._region_key = key
            hrgn = gdi32.CreateRectRgn(int(menu_rect.left), int(menu_rect.top),
                                       int(menu_rect.right), int(menu_rect.bottom))
            user32.SetWindowRgn(self.hwnd, hrgn, True)
            self._hrgn = hrgn
            return
        if alert_boxes is not None:
            # 卡片固定在窗口上部（位置不变），她缩到下半边 —— 两个矩形都不随
            # 呼吸变化，所以 key 恒定，整个提醒期间只会设一次区域。
            card, room = alert_boxes
            key = ("alert", card.left, card.top, card.width, card.height,
                   room.left, room.top, room.width, room.height)
            if key == self._region_key:
                return
            self._region_key = key
            hrgn = gdi32.CreateRectRgn(card.left - 2, card.top - 2,
                                       card.right + 2, card.bottom + 2)
            tmp = gdi32.CreateRectRgn(room.left - 3, room.top - 4,
                                      room.right + 3, room.bottom + 4)
            gdi32.CombineRgn(hrgn, hrgn, tmp, 2)          # RGN_OR
            gdi32.DeleteObject(tmp)
            user32.SetWindowRgn(self.hwnd, hrgn, True)
            self._hrgn = hrgn
            return
        # 贴图位置量化到 10px 一档：既让区域跟着她走（探头/拖动的位移），
        # 又不会每帧重建（重建一次是几百次 GDI 调用）。拖动时已经 SetCapture，
        # 区域滞后个 10px 也不影响拖。
        bx, by = blit
        bx -= bx % 10
        by -= by % 10
        key = (state, bx, by, bool(bubble_rect))
        if key == self._region_key:
            return
        rows = self._silhouette(state)
        if not rows:
            # 万一这张图画不出轮廓（缺素材等），退回整窗矩形，别把窗口裁没了
            self._region_key = None
            user32.SetWindowRgn(self.hwnd, None, True)
            self._hrgn = None
            return
        self._region_key = key
        hrgn = gdi32.CreateRectRgn(0, 0, 0, 0)
        tmp = gdi32.CreateRectRgn(0, 0, 0, 0)
        for (y, x0, x1) in rows:
            # 留出边距：她还有轻微浮动/呼吸位移，区域要略大于轮廓
            gdi32.SetRectRgn(tmp, bx + x0 - 3, by + y - 6, bx + x1 + 4, by + y + 7)
            gdi32.CombineRgn(hrgn, hrgn, tmp, 2)           # RGN_OR
        if bubble_rect:
            gdi32.SetRectRgn(tmp, bubble_rect[0] - 2, bubble_rect[1] - 2,
                             bubble_rect[2] + 2, bubble_rect[3] + 2)
            gdi32.CombineRgn(hrgn, hrgn, tmp, 2)
        gdi32.DeleteObject(tmp)
        user32.SetWindowRgn(self.hwnd, hrgn, True)
        self._hrgn = hrgn

    # ---- 字体（绕开 SysFont 扫描 bug）----
    def _get_font(self, size):
        """按 size 返回字体对象，优先用微软雅黑，失败则回退默认字体。"""
        if not hasattr(self, "_font_cache"):
            self._font_cache = {}
        if size in self._font_cache:
            return self._font_cache[size]
        candidates = [
            "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
            "C:/Windows/Fonts/msyh.ttf",
            "C:/Windows/Fonts/simhei.ttf",    # 黑体
            "C:/Windows/Fonts/simsun.ttc",    # 宋体
        ]
        font = None
        for path in candidates:
            if os.path.exists(path):
                try:
                    font = pygame.font.Font(path, size)
                    break
                except Exception:
                    continue
        if font is None:
            font = pygame.font.Font(None, size)  # pygame 内置默认字体
        self._font_cache[size] = font
        return font

    # ---- 渲染 ----
    def _draw_menu(self, surf):
        """菜单打开时的一帧：这个窗口只画菜单卡片。

        卡片要整张落在工作区里（贴屏幕边时窗口本来故意越出 8px，卡片
        右上角的关闭按钮会被推出屏幕），所以这里只挪"窗口"，不动 data.pos
        ——她的位置始终不变，菜单一收起她就回到原处。
        """
        panel = self.menu.draw(surf)
        wl, wt, wr, wb = self.work_area()
        bx = min(max(self.data.pos[0], wl), max(wl, wr - WIN_W))
        by = min(max(self.data.pos[1], wt), max(wt, wb - WIN_H))
        self._win_pos = (int(bx), int(by))
        self._apply_window_region(None, None, None, menu_rect=panel)
        self._update_layered(surf)

    def _draw(self):
        # 全透明起点，每帧全新 surface → 无残影
        surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))

        if self.menu.open:
            self._draw_menu(surf)
            return

        state = self.pet.state
        img = self.frames.get(state)
        w, h = img.get_size()
        # 贴左右时只做纵向缩放（左右断面必须贴死屏幕边）；贴上下时只做横向缩放
        edge_x = state in (Pet.PEEK_L, Pet.PEEK_R)
        edge_y = state in (Pet.PEEK_TOP, Pet.PEEK_BOTTOM)
        # 提醒卡片挂着的时候（ALERT_PET_SCALE，立绘本身已缩过，这里是 1.0）
        scale = ALERT_PET_SCALE if (self.alert.active and not self.dragging) else 1.0

        # Live2D 动效：呼吸 + 弹跳 + 走路摇摆
        # 拖动时冻结所有动效（呼吸/弹跳/摇摆），保证与窗口移动完全同步、不晃动
        if self.dragging:
            breath = 1.0
            bounce = 0
            walk_sway = 0
            sway = 0
        else:
            breath = (1.0 + math.sin(self.pet.breath * 2.2) * 0.012) * scale
            bounce = self.pet.bounce * 10            # 随窗口缩小，弹跳幅度同步收敛
            walk_sway = math.sin(self.pet.walk_phase) * 3 if state == Pet.WALK else 0
            # 贴上下边时改成左右轻微摇摆（上下断面不能动）
            sway = math.sin(self.pet.breath * 1.6) * 3 if edge_y else 0

        # 贴边姿势不做缩放（断面必须严格贴死屏幕边），只做轻微的平移浮动
        if edge_x:
            nw, nh = w, h
            # 只向下浮动：她的身体下端是"延伸出画面被裁掉"的，
            # 若向上浮会在窗口下沿露出一条生硬的切断边
            bob = 0 if self.dragging else min(0.0, math.sin(self.pet.breath * 2.2) * 3)
        elif edge_y:
            nw, nh = w, h
            bob = 0
        else:
            nw, nh = max(1, int(w * breath)), max(1, int(h * breath))
            bob = 0
        img_s = pygame.transform.smoothscale(img, (nw, nh))
        if abs(self.pet.tilt) > 0.5:
            img_s = pygame.transform.rotate(img_s, self.pet.tilt)

        # 贴边"露个脸"：朝着屏幕外侧平移，越移越多就把她藏回屏幕边后面
        retreat = 0 if self.dragging else int(round(
            self.pet.peek_anim * PEEK_RETREAT.get(state, 0)))

        # 立绘缩到 PET_SCALE 后窗口四周留出了边距，位置得按"她的中心还在原处"算：
        # 原来立绘几乎铺满窗口（留 8px 底边），中心就在窗口竖直中线上，
        # 所以缩了之后照旧把她的中心放在这条线上，她才不会明显跑位。
        mid_y = (WIN_H - nh) // 2

        # 贴边姿势：整张画布贴到窗口对应的那条边，画面里的"裁切断口"
        # 就正好落在屏幕（工作区）边缘上，形成"她藏在屏幕边后面"的错觉。
        # 注意贴上下边时断面就在竖直方向，竖直位置必须严格贴死屏幕边（不能居中）；
        # 贴左右边时竖直方向是自由的，按 mid_y 保证她不跑位。
        if state == Pet.PEEK_L:
            x, y = -retreat, mid_y - int(bounce) - int(bob)
        elif state == Pet.PEEK_R:
            x, y = WIN_W - nw + retreat, mid_y - int(bounce) - int(bob)
        elif state == Pet.PEEK_TOP:
            x, y = (WIN_W - nw) // 2 + int(sway), -retreat
        elif state == Pet.PEEK_BOTTOM:
            x, y = (WIN_W - nw) // 2 + int(sway), WIN_H - nh + retreat
        else:
            x = (WIN_W - nw) // 2 + int(walk_sway)
            if self.alert.active and not self.dragging:
                # 提醒时她贴到窗口最底下，把上半边整个让给卡片
                y = WIN_H - nh - int(bounce)
            else:
                y = mid_y - int(bounce)
        surf.blit(img_s, (x, y))
        self._last_img, self._last_pos = img_s, (x, y)

        # 提醒卡片：画在她上面（卡片才是这一屏的主角），卡片在时气泡就别挤了
        alert_boxes = None
        bubble_rect = None
        if self.alert.active:
            card = self.alert.draw(surf)
            alert_boxes = (card, pygame.Rect(*ALERT_PET_ROOM))
        elif self.voice.visible() and not self.detector.is_gaming():
            bubble_rect = self._draw_bubble(surf, self.voice.text, state)
        self._last_alert = alert_boxes         # 提醒期间窗口区域用的两块矩形
        self._last_bubble = bubble_rect        # 右键菜单允许点在气泡上

        # 贴边姿势：把窗口裁剪成角色轮廓，空白处鼠标穿透（不挡底下的点击）
        self._apply_window_region(state, (x, y), bubble_rect, alert_boxes=alert_boxes)

        # 平时窗口就压在她的位置上（只有菜单打开时才会临时挪开）
        self._win_pos = self.data.pos

        # 逐像素 alpha 提交给分层窗口（真透明，无黑底无色边）
        self._update_layered(surf)

    def _draw_bubble(self, surf, text, state=None):
        # 用指定字体文件，绕开 SysFont 在中文 Windows 下的扫描 bug
        font = self._get_font(BUBBLE_FONT)
        lines, cur = [], ""
        for ch in text:
            if font.size(cur + ch)[0] > WIN_W - 46:
                lines.append(cur); cur = ch
            else:
                cur += ch
        lines.append(cur)
        bw = max(font.size(l)[0] for l in lines) + 20
        bh = len(lines) * BUBBLE_LH + 12
        # 气泡贴着【她本人】摆，而不是贴着窗口边：立绘缩到一半后窗口留了边距，
        # 再按窗口顶边算的话气泡会飘在她头顶上方老远处。贴上下边放对面、
        # 贴左右边挪到另一侧，这些"让开她"的规则不变。
        ix, iy = self._last_pos
        ih = self._last_img.get_height() if self._last_img is not None else 0

        def _vy(v):
            return max(6, min(int(v), WIN_H - bh - 6))     # 夹在窗口里，别被切掉

        if state == Pet.PEEK_L:
            bx, by = WIN_W - bw - 6, _vy(iy - bh - 6)
        elif state == Pet.PEEK_R:
            bx, by = 6, _vy(iy - bh - 6)
        elif state == Pet.PEEK_TOP:
            bx, by = (WIN_W - bw) // 2, _vy(iy + ih + 6)
        else:
            bx, by = (WIN_W - bw) // 2, _vy(iy - bh - 6)
        pygame.draw.rect(surf, (255, 255, 255, 235), (bx, by, bw, bh), border_radius=10)
        pygame.draw.rect(surf, (230, 150, 180, 255), (bx, by, bw, bh), 2, border_radius=10)
        for i, l in enumerate(lines):
            t = font.render(l, True, (80, 60, 70))
            surf.blit(t, (bx + 10, by + 6 + i * BUBBLE_LH))
        return (bx, by, bx + bw, by + bh)

    # ---- 主循环 ----
    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            now = time.time()
            for e in pygame.event.get():
                # 菜单打开时，事件全先喂给菜单：拖动、贴边判定都给它让路
                if self.menu.open:
                    if e.type == pygame.MOUSEMOTION:
                        self.menu.on_move(e.pos)
                    elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                        key = self.menu.on_click(e.pos)   # 抬起才选中，避免误触
                        if key:
                            self._pending_menu = key
                    elif e.type == pygame.MOUSEBUTTONUP and e.button == 3:
                        self.menu.close()          # 再点一下右键也能收起
                    elif e.type == pygame.KEYDOWN:
                        key = self.menu.on_key(e)
                        if key:
                            self._pending_menu = key
                    elif e.type == getattr(pygame, "TEXTINPUT", -1):
                        self.menu.on_text(e.text)  # 自定义时长敲的数字
                    elif e.type == getattr(pygame, "WINDOWFOCUSLOST", -1):
                        self.menu.close()          # 点到别处 → 自动收起
                    continue

                # 提醒卡片挂着时，事件先给它 —— "到点了"比什么都优先
                if self.alert.active:
                    if e.type == pygame.MOUSEMOTION:
                        self.alert.on_move(self._cursor_local())
                    elif e.type == pygame.MOUSEBUTTONUP and e.button in (1, 3):
                        pos = self._cursor_local()
                        if self.alert.hit(pos):
                            self._resolve_alert(self.alert.on_click(pos) or "ok")
                        else:
                            # 点在卡片外面：顺手摸她也算"知道啦"
                            gx, gy = self._get_cursor_pos()
                            if self._hit_pet(gx, gy):
                                self._resolve_alert("ok")
                    elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                        self._resolve_alert("ok")
                    elif e.type == pygame.MOUSEBUTTONDOWN:
                        pass          # 提醒期间不拖她（免得手滑把窗口拖走）
                    continue

                # 注意：无边框窗口点角色不应触发退出；
                # 只有托盘「退出」或系统退出才停止。这里忽略 QUIT 事件来源不明的情况，
                # 用 Alt+F4 之类会被 pygame.QUIT 捕获，我们只在托盘退出时置 running=False。
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    gx, gy = self._get_cursor_pos()
                    if not self._hit_character(gx, gy):
                        continue          # 点在透明区域：不响应，避免"抓空气"
                    self.dragging = True
                    self._moved = False
                    self._grab_global = (gx, gy)                 # 按下时的屏幕绝对坐标
                    self._grab_offset = (gx - self.data.pos[0],  # 光标相对窗口的偏移
                                         gy - self.data.pos[1])
                    self.pet.on_grab()
                    self._set_capture(True)
                    self._log("DOWN grab=%s pos=%s" % (self._grab_global, self.data.pos))
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    self._log("UP moved=%s pos=%s" % (self._moved, self.data.pos))
                    self._set_capture(False)
                    if self.dragging:
                        self.pet.on_release(self._moved)
                    self.dragging = False
                    self._apply_edge()        # 松手立刻判定是否贴到屏幕边
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 3:
                    # 右键【抬起】时才开菜单（按下就开会连同这一下抬起一起被吃掉）
                    # 只有点在她身上/气泡上才算
                    gx, gy = self._get_cursor_pos()
                    if not self.dragging and self._hit_pet(gx, gy):
                        self._log("RCLICK at=(%d,%d)" % (gx, gy))
                        self.menu.open_at(gx, gy)
                # 注意：拖动位移不再依赖 MOUSEMOTION 的相对量（那样会振荡），
                # 改为在主循环里按屏幕绝对坐标每帧同步窗口位置。

            # 拖动：每帧用屏幕绝对坐标同步窗口位置（与系统拖窗原理一致，无累积误差）
            if self.dragging:
                gx, gy = self._get_cursor_pos()
                if (abs(gx - self._grab_global[0]) > 3
                        or abs(gy - self._grab_global[1]) > 3):
                    self._moved = True
                wl, wt, wr, wb = self.work_area()
                nx = gx - self._grab_offset[0]
                ny = gy - self._grab_offset[1]
                # 限制越出工作区的幅度：既防止桌宠被拖到看不见的地方，
                # 又保证拖到边缘时一定落在贴边判定范围内（贴边才能被吸附）
                nx = max(wl - EDGE_LIMIT, min(nx, wr - WIN_W + EDGE_LIMIT))
                ny = max(wt - EDGE_LIMIT, min(ny, wb - WIN_H + EDGE_LIMIT))
                self.data.pos = (nx, ny)

            # 托盘里改了"启动位置" → 在这里按新设定搬一次窗口（绘制只能在主线程做）
            if self._pending_edge is not None:
                self._apply_startup_pos()
                self._pending_edge = None
                self._apply_edge(snap=True)
                self.data.save()

            # 托盘里改了"自动变化"的间隔 → 重新起算并回一句话
            if self._pending_auto is not None:
                secs = self._pending_auto
                self._pending_auto = None
                self.pet.reset_auto_timer()
                self.data.save()
                if secs > 0:
                    self.voice.say_text(
                        "好呀，我每 %s 自己动一下～"
                        % dict(AUTO_CHOICES).get(secs, "%d 秒" % secs), 3.0)
                else:
                    self.voice.say_text("那我乖乖待着，等你来点我～", 3.0)
            # 托盘/菜单改了"专注时长" → 落盘并回一句话
            if self._pending_pomo is not None:
                m = self._pending_pomo
                self._pending_pomo = None
                self.data.save()
                self.voice.say_text("好呀，专注 %d 分钟～" % m, 3.0)

            # 右键菜单选了一项 → 在这里执行（搬窗口/换姿势都只能在主线程做）
            if self._pending_menu is not None:
                key = self._pending_menu
                self._pending_menu = None
                self._log("MENU %s" % key)
                self._do_menu(key)

            self._tick_visibility(now)
            if not self.menu.open:
                # 菜单开着的时候先别吸附/换姿势，免得卡片跟着窗口一起跳
                self._apply_edge()
            self.pet.update(dt, now)      # 到点（番茄钟/待办）会在这里报出来
            self.alert.tick(now)          # 到点提醒：隔几秒"叮"一声
            # 提醒还挂着就先别再查待办了，免得两条待办叠成两张卡片
            if not self.alert.active and now - self._last_todo_check > 2:
                self._last_todo_check = now
                if not self.detector.is_gaming():
                    self.pet.check_todos()
            self._draw()

        self.data.save()
        pygame.quit()


_LOCK_HANDLE = None


def _acquire_single_instance_lock():
    """单实例锁：用文件独占句柄实现（进程死即自动释放，不会残留）。

    命名互斥量在进程被强杀时可能残留于内核，导致误判。文件锁依赖
    操作系统句柄，进程结束句柄必然关闭，最可靠。
    """
    global _LOCK_HANDLE
    lock_path = os.path.join(DATA_DIR, ".single_instance.lock")
    if sys.platform == "win32":
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = ctypes.c_void_p
        handle = k32.CreateFileW(
            lock_path,
            0x40000000,  # GENERIC_WRITE
            0,           # 不共享：其他进程无法再打开
            None,
            2,           # OPEN_ALWAYS
            0x80,        # FILE_ATTRIBUTE_NORMAL
            None,
        )
        if not handle or handle == -1:  # INVALID_HANDLE_VALUE
            return False
        _LOCK_HANDLE = handle
        return True
    # 非 Windows：用 O_CREAT|O_EXCL 原子创建
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, b"1")
        _LOCK_HANDLE = fd
        return True
    except FileExistsError:
        return False


def _append_log(path, text):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def main():
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    if not _acquire_single_instance_lock():
        print("桌宠已在运行中，本次启动被忽略（避免多开叠影）。")
        _append_log(os.path.join(DATA_DIR, "start.log"),
                    "%s  [跳过] 已有实例在运行\n" % stamp)
        return
    # 启动留痕：开机自启时没有控制台，靠这个文件确认她到底有没有被拉起来
    _append_log(os.path.join(DATA_DIR, "start.log"),
                "%s  [启动] %s  pid=%d\n" % (stamp, VERSION, os.getpid()))
    print(f"桌宠启动 {VERSION}")
    if sys.platform == "win32":
        try:
            hdc = ctypes.windll.user32.GetDC(None)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(None, hdc)
            print(f"系统DPI: {dpi} (缩放 {dpi*100//96}%)")
        except Exception:
            pass
    App().run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # 开机自启用的是 pythonw（没有控制台），把崩溃信息落到 data/crash.log 便于排查
        try:
            import traceback
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(os.path.join(DATA_DIR, "crash.log"), "a", encoding="utf-8") as f:
                f.write("\n===== %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
                traceback.print_exc(file=f)
        except Exception:
            pass
        raise
