# -*- coding: utf-8 -*-
"""
梦幻之星网络版 (PSOBB) · PC一键单机终极启动器
================================================================================
作者：哔哩哔哩：metalmouse
更新：全功能单机生态整合版 (运行日志自查系统、PyInstaller冻结路径修复、全量INI持久化、紧凑自适应排版)

核心特性与设计规范：
  1. 【PyInstaller 冻结路径自适应 (核心 Bug 修复)】：
     - 打包为单文件 exe 时，通过 sys.executable 正确解析工作目录，彻底杜绝找不到文件与 INI 丢失问题；
  2. 【全量参数与窗口记忆 (launcher_ui.ini)】：
     - 窗口尺寸、位置、最大化状态与所有滑块、下拉框、复选框在退出时全自动保存，重开 100% 恢复；
  3. 【底栏永不遮挡与自适应排版】：
     - 底部【一键启动】按钮栏优先布局，永远锁定在最下方可见区域，绝对不被压缩或遮挡；
  4. 【详细运行与报错自查日志 (launcher.log)】：
     - 自动记录启动器运行、服务拉起、网络监听、游戏唤起、DEP状态与异常 Traceback，一键呼出日志文件；
  5. 【红盒概率 原表至约 30% / 全能魔法 / 炫彩名字 / 现代着色器 / 造物工具直连】。
"""

import os
import sys
import time
import socket
import shutil
import hashlib
import struct
import threading
import subprocess
import traceback
import winreg
import ctypes
from ctypes import wintypes
import configparser
import secrets
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from launcher_display import (MODES, DEFAULT_MODE, display_profile, desktop_size,
                              update_dgvoodoo, update_ini, position_window)

# ==============================================================================
# 路径自适应（关键：适配 PyInstaller 打包环境与源码开发环境）
# ==============================================================================
from project_paths import game_root
BASE_DIR = str(game_root())

CLIENT_DIR = os.path.join(BASE_DIR, "Client")
SERVER_DIR = os.path.join(BASE_DIR, "Server")
SAVES_BACKUP_DIR = os.path.join(BASE_DIR, "Saves_Backup")
SHIP_INI_PATH = os.path.join(SERVER_DIR, "ship.ini")
TETHEALLA_INI_PATH = os.path.join(SERVER_DIR, "tethealla.ini")
SHIP_INI_DEFAULT = os.path.join(SERVER_DIR, "ship.ini.default")
TETHEALLA_INI_DEFAULT = os.path.join(SERVER_DIR, "tethealla.ini.default")
TECH_INI_PATH = os.path.join(SERVER_DIR, "param", "tech.ini")
TECH_INI_DEFAULT = os.path.join(SERVER_DIR, "param", "tech.ini.default")
SHIP_EXE_PATH = os.path.join(SERVER_DIR, "ship_server.exe")
DGVOODOO_CONF_PATH = os.path.join(CLIENT_DIR, "dgVoodoo.conf")
WIDESCREEN_CFG_PATH = os.path.join(CLIENT_DIR, "widescreen.cfg")
WIDESCREEN_CFG_DEFAULT = os.path.join(CLIENT_DIR, "widescreen.cfg.default")
PSOBB_EXE = os.path.join(CLIENT_DIR, "PsoBB.exe")
ACCOUNT_DAT_PATH = os.path.join(SERVER_DIR, "account.dat")
UI_INI_PATH = os.path.join(BASE_DIR, "launcher_ui.ini")
LOG_FILE_PATH = os.path.join(BASE_DIR, "launcher.log")
ITEM_MAKER_EXE = os.path.join(SERVER_DIR, "tools", "Item_Maker.exe")
TETHMAN_EXE = os.path.join(SERVER_DIR, "tools", "tethman.exe")

# ==============================================================================
# 日志记录系统（自动持久化到 launcher.log，方便用户与开发者自查排错）
# ==============================================================================
def write_log(level, message, exc=None):
    """写入带时间戳和调用栈的运行日志"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}\n"
    if exc:
        log_line += f"--- 异常堆栈详情 ---\n{traceback.format_exc()}\n--------------------\n"
    try:
        # 文件超过 5MB 自动备份轮换
        if os.path.exists(LOG_FILE_PATH) and os.path.getsize(LOG_FILE_PATH) > 5 * 1024 * 1024:
            bak = LOG_FILE_PATH + ".bak"
            if os.path.exists(bak): os.remove(bak)
            os.rename(LOG_FILE_PATH, bak)
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception:
        pass


EVENT_MAP = {
    0: "无活动 (常规大厅)",
    1: "圣诞节 (Christmas)",
    3: "情人节 (Valentine)",
    4: "复活节 (Easter)",
    5: "万圣节 (Halloween)",
    6: "索尼克周年 (Sonic)",
    7: "新年 (New Year)",
    8: "夏季 (Summer)",
    9: "白色情人节 (White Day)",
    10: "婚礼 (Wedding)",
    11: "秋季 (Fall)",
    12: "春季特别主题 (Spring Special)",
    13: "夏季特别主题 (Summer Special)",
    14: "樱花春季 (Spring)",
}
EVENT_REVERSE_MAP = {v: k for k, v in EVENT_MAP.items()}

DROP_SECTION_CHOICES = {"角色原有徽章（默认）": None}
DROP_SECTION_CHOICES.update({
    name: index for index, name in enumerate(
        ("翠绿（Viridia）", "嫩绿（Greennill）", "群青（Skyly）", "深蓝（Bluefull）",
         "紫罗兰（Purplenum）", "粉红（Pinkal）", "赤红（Redria）", "橙色（Oran）",
         "金黄（Yellowboze）", "纯白（Whitill）"))
})
DROP_SECTION_RANDOM = "随机（每次开始游戏抽取）"
DROP_SECTION_CHOICES[DROP_SECTION_RANDOM] = "random"


def resolve_drop_section(choice):
    if choice not in DROP_SECTION_CHOICES:
        raise ValueError("未知的掉落徽章选项")
    value = DROP_SECTION_CHOICES[choice]
    return secrets.randbelow(10) if value == "random" else value

COLOR_PRESETS = {
    "经典原版白 (#FFFFFF)": "FFFFFF",
    "耀眼土豪金 (#FFD700)": "FFD700",
    "赛博霓虹青 (#00FFFF)": "00FFFF",
    "霸气烈焰红 (#FF4500)": "FF4500",
    "魅惑幻影紫 (#DA70D6)": "DA70D6",
    "深邃天空蓝 (#1D94F7)": "1D94F7",
    "荧光翡翠绿 (#00FF7F)": "00FF7F",
}

WINDOW_SCALE_PRESETS = {
    "2X 高清窗口 (1280×960 推荐)": {"res_id": 3, "w": 1280, "h": 960, "mode": "window"},
    "1X 原版窗口 (640×480 经典)": {"res_id": 0, "w": 640, "h": 480, "mode": "window"},
    "1.25X 怀旧窗口 (800×600)": {"res_id": 1, "w": 800, "h": 600, "mode": "window"},
    "1.6X 平衡窗口 (1024×768)": {"res_id": 2, "w": 1024, "h": 768, "mode": "window"},
    "2.5X 大屏窗口 (1600×1200)": {"res_id": 5, "w": 1600, "h": 1200, "mode": "window"},
    "3X 超清窗口 (1920×1440 2K)": {"res_id": 3, "w": 1920, "h": 1440, "mode": "custom_window"},
    "4X 旗舰窗口 (2560×1920 4K)": {"res_id": 5, "w": 2560, "h": 1920, "mode": "custom_window"},
}

RENDER_API_PRESETS = {
    "DirectX 11 (流畅推荐)": "d3d11_fl11_0",
    "DirectX 12 (现代特性)": "d3d12_fl12_0",
    "系统最佳自适应": "bestavailable",
}

FONT_PRESETS = {
    "宋体 (像素点阵 超清晰推荐)": "SimSun",
    "微软雅黑 (矢量平滑 现代字体)": "Microsoft YaHei",
    "黑体 (标准黑体 清晰厚重)": "SimHei",
    "楷体 (经典国风 典雅正楷)": "KaiTi",
}

HUD_SCALE_PRESETS = [
    "1.0 (原生锐利清晰，推荐)",
    "1.25 (适度微调放大)",
    "1.5 (大界面缩放)",
]

STATS_MULT_PRESETS = [
    "4X (畅爽推荐)",
    "1X (原版数值)",
    "2X (轻度强化)",
    "6X (进阶狂暴)",
    "10X (割草无双)",
]

def parse_mult(val_str):
    if not val_str:
        return 4.0
    s = str(val_str).upper()
    if "10X" in s or s.startswith("10"):
        return 10.0
    if "6X" in s or s.startswith("6"):
        return 6.0
    if "4X" in s or s.startswith("4"):
        return 4.0
    if "2X" in s or s.startswith("2"):
        return 2.0
    if "1X" in s or s.startswith("1"):
        return 1.0
    try:
        return float(s.replace("X", "").strip())
    except Exception:
        return 4.0


# ==============================================================================
# 自包含 SEGA PRS 压缩与解压缩引擎 (LZ77 变种，用于 PlyLevelTbl.prs)
# ==============================================================================
class ControlStreamReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
        self.bits = 0

    def eof(self) -> bool:
        return self.pos >= len(self.data)

    def get_u8(self) -> int:
        if self.pos >= len(self.data):
            raise EOFError("PRS 数据流提前结束")
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_bit(self):
        if not (self.bits & 0x0100):
            if self.pos >= len(self.data):
                return None
            self.bits = 0xFF00 | self.get_u8()
        ret = self.bits & 1
        self.bits >>= 1
        return ret


def prs_decompress(data: bytes) -> bytes:
    """解压 SEGA PRS 数据流"""
    cr = ControlStreamReader(data)
    out = bytearray()
    while not cr.eof():
        b = cr.read_bit()
        if b is None:
            break
        if b == 1:
            out.append(cr.get_u8())
        else:
            b2 = cr.read_bit()
            if b2 is None:
                break
            if b2 == 1:
                low = cr.get_u8()
                high = cr.get_u8()
                a = low | (high << 8)
                raw_offset = a >> 3
                if raw_offset == 0:
                    break
                offset = raw_offset - 0x2000
                size_bits = a & 7
                count = (size_bits + 2) if size_bits != 0 else (cr.get_u8() + 1)
            else:
                bit1 = cr.read_bit()
                bit2 = cr.read_bit()
                count = ((bit1 << 1) | bit2) + 2
                offset = cr.get_u8() - 0x100

            read_pos = len(out) + offset
            if read_pos < 0 or read_pos >= len(out):
                break
            for _ in range(count):
                out.append(out[read_pos])
                read_pos += 1
    return bytes(out)


class PRSCompressor:
    def __init__(self):
        self.control_byte = 0
        self.control_bit_pos = 0
        self.output = bytearray()
        self.control_offset = 0

    def _start_control_byte(self):
        self.control_offset = len(self.output)
        self.output.append(0)
        self.control_byte = 0
        self.control_bit_pos = 0

    def put_control_bit(self, bit: int):
        if self.control_bit_pos == 0 and self.control_offset == len(self.output):
            self._start_control_byte()
        elif self.control_bit_pos == 8:
            self._start_control_byte()
        if bit:
            self.output[self.control_offset] |= (1 << self.control_bit_pos)
        self.control_bit_pos += 1

    def put_u8(self, b: int):
        self.output.append(b & 0xFF)

    def put_literal(self, b: int):
        self.put_control_bit(1)
        self.put_u8(b)

    def put_short_copy(self, offset: int, count: int):
        self.put_control_bit(0)
        self.put_control_bit(0)
        size_bits = count - 2
        self.put_control_bit((size_bits >> 1) & 1)
        self.put_control_bit(size_bits & 1)
        self.put_u8(offset & 0xFF)

    def put_long_copy(self, offset: int, count: int):
        self.put_control_bit(0)
        self.put_control_bit(1)
        raw_offset = offset & 0x1FFF
        if count <= 9:
            size_field = count - 2
            a = (raw_offset << 3) | size_field
            self.put_u8(a & 0xFF)
            self.put_u8((a >> 8) & 0xFF)
        else:
            a = raw_offset << 3
            self.put_u8(a & 0xFF)
            self.put_u8((a >> 8) & 0xFF)
            self.put_u8((count - 1) & 0xFF)

    def finish(self) -> bytes:
        self.put_control_bit(0)
        self.put_control_bit(1)
        self.put_u8(0)
        self.put_u8(0)
        return bytes(self.output)


def prs_compress(data: bytes) -> bytes:
    """使用 SEGA PRS LZ77 算法压缩数据流"""
    c = PRSCompressor()
    c._start_control_byte()
    pos = 0
    length = len(data)

    head = {}
    prev = [0] * length

    while pos < length:
        best_len = 0
        best_off = 0

        if pos + 3 <= length:
            match_key = (data[pos], data[pos+1], data[pos+2])
            match_pos = head.get(match_key, -1)
            search_depth = 0

            while match_pos != -1 and search_depth < 64:
                offset = match_pos - pos
                if offset < -8191:
                    break

                curr_len = 0
                max_check = min(length - pos, 256)
                while curr_len < max_check and data[pos + curr_len] == data[match_pos + curr_len]:
                    curr_len += 1

                if curr_len > best_len:
                    best_len = curr_len
                    best_off = offset
                    if best_len >= 256:
                        break

                match_pos = prev[match_pos]
                search_depth += 1

        if best_len >= 3:
            if best_off >= -256 and best_len <= 5:
                c.put_short_copy(best_off, best_len)
            else:
                c.put_long_copy(best_off, best_len)

            for i in range(best_len):
                if pos + i + 3 <= length:
                    k = (data[pos+i], data[pos+i+1], data[pos+i+2])
                    prev[pos+i] = head.get(k, -1)
                    head[k] = pos + i
            pos += best_len
        else:
            c.put_literal(data[pos])
            if pos + 3 <= length:
                k = (data[pos], data[pos+1], data[pos+2])
                prev[pos] = head.get(k, -1)
                head[k] = pos
            pos += 1

    return c.finish()



UNLOCKED_TECH = """Foie,30,30,0,30,0,0,30,30,30,0,30,30
Gifoie,30,30,0,30,0,0,30,30,30,0,30,30
Rafoie,30,30,0,30,0,0,30,30,30,0,30,30
Barta,30,30,0,30,0,0,30,30,30,0,30,30
Gibarta,30,30,0,30,0,0,30,30,30,0,30,30
Rabarta,30,30,0,30,0,0,30,30,30,0,30,30
Zonde,30,30,0,30,0,0,30,30,30,0,30,30
Gizonde,30,30,0,30,0,0,30,30,30,0,30,30
Razonde,30,30,0,30,0,0,30,30,30,0,30,30
Grants,30,30,0,30,0,0,30,30,30,0,30,30
Deband,30,30,0,30,0,0,30,30,30,0,30,30
Jellen,30,30,0,30,0,0,30,30,30,0,30,30
Zalure,30,30,0,30,0,0,30,30,30,0,30,30
Shifta,30,30,0,30,0,0,30,30,30,0,30,30
Ryuker,1,1,0,1,0,0,1,1,1,0,1,1
Resta,30,30,0,30,0,0,30,30,30,0,30,30
Anti,7,7,0,7,0,0,7,7,7,0,7,7
Reverser,1,1,0,1,0,0,1,1,1,0,1,1
Megid,30,30,0,30,0,0,30,30,30,0,30,30
"""

GM_COMMANDS_HELP = """
================================================================================
【梦幻之星网络版 (PSOBB) · 单机 GM 常用指令速查手册】
================================================================================
进入游戏后在聊天栏直接敲击以下指令即可生效（默认 admin 自带 GM 9级最高权限）：

1. 经验与瞬间升级：
   /levelup 150       - 瞬间升到指定等级（范围 1-200）

2. 爆率与红箱爆发模式：
   /redbox            - 在线临时切换红箱爆发模式（怪必爆红箱/稀有武器）

3. 全地图传送与脱离：
   /warpme 1          - 瞬间传送到指定地图（1-14 为森林/洞穴/坑道/遗迹/神殿/宇宙船等）
   /warpme 0          - 传回先驱者二号大厅

4. 物品与武器生成：
   /item <代码>        - 凭空生成指定武器/道具/防具（或直接点击启动器【造物神器】生成）

5. 角色变身与 NPC 外形：
   /npc 0             - 恢复自身原本外貌
   /npc 1 至 7        - 变身为法米通、丽子(Rico)、索尼克、纳克鲁斯、塔尔斯、弗洛文、艾莉等

6. 头顶光标炫彩装饰：
   /arrow 1 至 12     - 在头顶显示炫酷彩色箭头光标（1红 2蓝 3绿 4黄 5紫 6青...）

7. 玛古极速养成诀窍：
   - 使用启动器【打开造物神器 (Item Maker)】可直接一键生成 200 级满级完美玛古（如 Sato/Rati 等）！
"""

# ==============================================================================
# Win32 底层 API 结构与输入定义
# ==============================================================================
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PUL = ctypes.POINTER(ctypes.c_ulong)
class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ('wVk', wintypes.WORD),
        ('wScan', wintypes.WORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', PUL)
    ]

class HardwareInput(ctypes.Structure):
    _fields_ = [
        ('uMsg', wintypes.DWORD),
        ('wParamL', wintypes.WORD),
        ('wParamH', wintypes.WORD)
    ]

class MouseInput(ctypes.Structure):
    _fields_ = [
        ('dx', wintypes.LONG),
        ('dy', wintypes.LONG),
        ('mouseData', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', PUL)
    ]

class Input_I(ctypes.Union):
    _fields_ = [
        ('ki', KeyBdInput),
        ('mi', MouseInput),
        ('hi', HardwareInput)
    ]

class Input(ctypes.Structure):
    _fields_ = [
        ('type', wintypes.DWORD),
        ('ii', Input_I)
    ]

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
VK_RETURN = 0x0D
SCAN_ENTER = 0x1C

def force_activate_window(hwnd):
    """突破 Windows 前台锁定强制置顶并激活目标窗口"""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    try:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        cur_tid = kernel32.GetCurrentThreadId()
        fg_hwnd = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
        target_tid = user32.GetWindowThreadProcessId(hwnd, None)

        if fg_tid != target_tid:
            user32.AttachThreadInput(cur_tid, target_tid, True)
            if fg_tid != 0:
                user32.AttachThreadInput(fg_tid, target_tid, True)

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)

        if fg_tid != target_tid:
            user32.AttachThreadInput(cur_tid, target_tid, False)
            if fg_tid != 0:
                user32.AttachThreadInput(fg_tid, target_tid, False)
        return True
    except Exception as e:
        write_log("WARN", f"激活窗口异常 (hwnd={hwnd}): {e}")
        return False

def send_enter_keystroke(hwnd):
    """硬件级扫描码回车注入"""
    force_activate_window(hwnd)
    time.sleep(0.08)

    inp_down = Input()
    inp_down.type = INPUT_KEYBOARD
    inp_down.ii.ki.wVk = VK_RETURN
    inp_down.ii.ki.wScan = SCAN_ENTER
    inp_down.ii.ki.dwFlags = KEYEVENTF_SCANCODE

    inp_up = Input()
    inp_up.type = INPUT_KEYBOARD
    inp_up.ii.ki.wVk = VK_RETURN
    inp_up.ii.ki.wScan = SCAN_ENTER
    inp_up.ii.ki.dwFlags = KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP

    user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(inp_down))
    time.sleep(0.06)
    user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(inp_up))

    user32.PostMessageW(hwnd, 0x0100, VK_RETURN, 0x001C0001)
    time.sleep(0.04)
    user32.PostMessageW(hwnd, 0x0101, VK_RETURN, 0xC01C0001)

def is_psobb_process_alive():
    """检测 PsoBB.exe 进程是否正在运行"""
    try:
        res = subprocess.run(["tasklist", "/fi", "imagename eq PsoBB.exe"], capture_output=True, text=True, creationflags=0x08000000)
        return "psobb.exe" in res.stdout.lower()
    except Exception:
        return False


# ==============================================================================
# Windows 作业对象 (Job Object)
# ==============================================================================
class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('PerProcessUserTimeLimit', ctypes.c_int64),
        ('PerJobUserTimeLimit', ctypes.c_int64),
        ('LimitFlags', wintypes.DWORD),
        ('MinimumWorkingSetSize', ctypes.c_size_t),
        ('MaximumWorkingSetSize', ctypes.c_size_t),
        ('ActiveProcessLimit', wintypes.DWORD),
        ('Affinity', ctypes.c_size_t),
        ('PriorityClass', wintypes.DWORD),
        ('SchedulingClass', wintypes.DWORD),
    ]

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ('ReadOperationCount', ctypes.c_uint64),
        ('WriteOperationCount', ctypes.c_uint64),
        ('OtherOperationCount', ctypes.c_uint64),
        ('ReadTransferCount', ctypes.c_uint64),
        ('WriteTransferCount', ctypes.c_uint64),
        ('OtherTransferCount', ctypes.c_uint64),
    ]

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ('IoInfo', IO_COUNTERS),
        ('ProcessMemoryLimit', ctypes.c_size_t),
        ('JobMemoryLimit', ctypes.c_size_t),
        ('PeakProcessMemoryLimit', ctypes.c_size_t),
        ('PeakJobMemoryLimit', ctypes.c_size_t),
    ]

class Win32JobObject:
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

    def __init__(self):
        self.handle = None
        try:
            self.handle = kernel32.CreateJobObjectW(None, None)
            if self.handle:
                info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
                info.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                kernel32.SetInformationJobObject(
                    self.handle,
                    9,
                    ctypes.byref(info),
                    ctypes.sizeof(info)
                )
        except Exception as e:
            write_log("WARN", f"初始化 JobObject 失败: {e}")
            self.handle = None

    def assign_process(self, proc_handle):
        if self.handle and proc_handle:
            try:
                kernel32.AssignProcessToJobObject(self.handle, proc_handle)
            except Exception as e:
                write_log("WARN", f"分配进程至 JobObject 失败: {e}")

GLOBAL_JOB = Win32JobObject()


# ==============================================================================
# 配置管理类 (文件校验、原子写回、分层存档容灾与哈希去重)
# ==============================================================================
class ConfigManager:
    @staticmethod
    def ensure_default_backups():
        """若不存在原始模板，自动备份 .default"""
        if os.path.exists(SHIP_INI_PATH) and not os.path.exists(SHIP_INI_DEFAULT):
            try: shutil.copy2(SHIP_INI_PATH, SHIP_INI_DEFAULT)
            except Exception: pass
        if os.path.exists(TETHEALLA_INI_PATH) and not os.path.exists(TETHEALLA_INI_DEFAULT):
            try: shutil.copy2(TETHEALLA_INI_PATH, TETHEALLA_INI_DEFAULT)
            except Exception: pass
        if os.path.exists(TECH_INI_PATH) and not os.path.exists(TECH_INI_DEFAULT):
            try: shutil.copy2(TECH_INI_PATH, TECH_INI_DEFAULT)
            except Exception: pass
        if os.path.exists(WIDESCREEN_CFG_PATH) and not os.path.exists(WIDESCREEN_CFG_DEFAULT):
            try: shutil.copy2(WIDESCREEN_CFG_PATH, WIDESCREEN_CFG_DEFAULT)
            except Exception: pass

        # PlyLevelTbl 文件备份
        ply_files = [
            (os.path.join(CLIENT_DIR, "data", "PlyLevelTbl.bin"), os.path.join(CLIENT_DIR, "data", "PlyLevelTbl.bin.default")),
            (os.path.join(CLIENT_DIR, "data", "PlyLevelTbl.prs"), os.path.join(CLIENT_DIR, "data", "PlyLevelTbl.prs.default")),
            (os.path.join(SERVER_DIR, "param", "PlyLevelTbl.bin"), os.path.join(SERVER_DIR, "param", "PlyLevelTbl.bin.default")),
            (os.path.join(SERVER_DIR, "PlyLevelTbl.bin"), os.path.join(SERVER_DIR, "PlyLevelTbl.bin.default")),
            (os.path.join(SERVER_DIR, "PlyLevelTbl.prs"), os.path.join(SERVER_DIR, "PlyLevelTbl.prs.default")),
        ]
        for src, dst in ply_files:
            if os.path.exists(src) and not os.path.exists(dst):
                try: shutil.copy2(src, dst)
                except Exception: pass

    @staticmethod
    def restore_default_config():
        """从 .default 模板恢复原始配置"""
        ConfigManager.ensure_default_backups()
        if os.path.exists(SHIP_INI_DEFAULT):
            shutil.copy2(SHIP_INI_DEFAULT, SHIP_INI_PATH)
        if os.path.exists(TETHEALLA_INI_DEFAULT):
            shutil.copy2(TETHEALLA_INI_DEFAULT, TETHEALLA_INI_PATH)
        if os.path.exists(TECH_INI_DEFAULT):
            shutil.copy2(TECH_INI_DEFAULT, TECH_INI_PATH)
        if os.path.exists(WIDESCREEN_CFG_DEFAULT):
            shutil.copy2(WIDESCREEN_CFG_DEFAULT, WIDESCREEN_CFG_PATH)
        ConfigManager.set_drop_profile(20, None)
        ConfigManager.set_meseta_mult(1)
        ConfigManager.apply_stats_multipliers(1.0, 1.0, 1.0)
        write_log("INFO", "已成功恢复所有 INI、着色器与角色战斗倍率为原始默认值")

    @staticmethod
    def scale_ply_level_tbl(data: bytes, mult_dmg: float, mult_def: float, mult_hp: float) -> bytes:
        """缩放基础属性和 199 次升级成长，保留原生 REL 指针及经验阈值。"""
        if len(data) != 29184:
            raise ValueError(f"PlyLevelTbl.bin 尺寸异常 ({len(data)} 字节)，请恢复原版 .default 成长表")
        expected_tables = tuple(0xD8 + c * 200 * 12 for c in range(12))
        if (struct.unpack_from('<12I', data, 0x7158) != expected_tables
                or struct.unpack_from('<I', data, len(data) - 16)[0] != 0x7188
                or struct.unpack_from('<2I', data, 0x7188) != (0xA8, 0x7158)):
            raise ValueError("PlyLevelTbl.bin 的 REL 指针异常，请恢复原版 .default 成长表后重试")
        if mult_dmg == mult_def == mult_hp == 1.0:
            return bytes(data)
        buf = bytearray(data)
        # 1. 基础属性 (0 到 168: 12个职业，每职业 7 个 uint16 = 14 字节)
        # 结构: [atp, mst, evp, hp, dfp, ata, lck]
        for c in range(12):
            base_off = c * 14
            atp, mst, evp, hp, dfp, ata, lck = struct.unpack('<7H', buf[base_off:base_off+14])
            # 当开启伤害倍率时，基础 ATP 给予保底贯穿，并同步提升命中力 (ATA)，避免高难度/EP4打怪全Miss或破不了防(0伤害)
            bonus_atp = int(round((mult_dmg - 1.0) * 40)) if mult_dmg > 1.0 else 0
            new_atp = min(65535, max(1, int(round(atp * mult_dmg + bonus_atp))))
            new_mst = min(65535, max(1, int(round(mst * mult_dmg))))
            new_hp  = min(65535, max(1, int(round(hp * mult_hp))))
            new_dfp = min(65535, max(1, int(round(dfp * mult_def))))
            new_ata = min(65535, max(1, int(round(ata * (1.5 if mult_dmg > 1.0 else 1.0)))))
            struct.pack_into('<7H', buf, base_off, new_atp, new_mst, evp, new_hp, new_dfp, new_ata, lck)

        # 2. 每职业从 0xd8 起有 200 行：首行为等级 1 占位，随后 199 行为升级成长。
        # 从 0xe4 开始只能处理 199 行；多处理一行会在最后一职业覆盖 0x7158 的 REL 指针。
        # 每级 entry: [inc_atp, inc_mst, inc_evp, inc_hp, inc_dfp, inc_ata, inc_lck, inc_esp, exp(uint32)]
        table_off = 0xe4
        for c in range(12):
            for lvl in range(199):
                entry_off = table_off + (c * 200 + lvl) * 12
                inc_atp = buf[entry_off + 0]
                inc_mst = buf[entry_off + 1]
                inc_hp  = buf[entry_off + 3]
                inc_dfp = buf[entry_off + 4]
                inc_ata = buf[entry_off + 5]

                buf[entry_off + 0] = min(255, int(round(inc_atp * mult_dmg)))
                buf[entry_off + 1] = min(255, int(round(inc_mst * mult_dmg)))
                buf[entry_off + 3] = min(255, int(round(inc_hp * mult_hp)))
                buf[entry_off + 4] = min(255, int(round(inc_dfp * mult_def)))
                if mult_dmg > 1.0:
                    buf[entry_off + 5] = min(255, int(round(inc_ata * 1.5)))

        return bytes(buf)

    @staticmethod
    def apply_stats_multipliers(mult_dmg: float, mult_def: float, mult_hp: float):
        """将伤害(ATP/MST)、防御(DFP)、血量(HP)倍率原子应用至服务端与客户端全量 PlyLevelTbl"""
        default_bin = os.path.join(CLIENT_DIR, "data", "PlyLevelTbl.bin.default")
        client_bin = os.path.join(CLIENT_DIR, "data", "PlyLevelTbl.bin")
        client_prs = os.path.join(CLIENT_DIR, "data", "PlyLevelTbl.prs")
        server_bin = os.path.join(SERVER_DIR, "PlyLevelTbl.bin")
        server_prs = os.path.join(SERVER_DIR, "PlyLevelTbl.prs")
        server_param_bin = os.path.join(SERVER_DIR, "param", "PlyLevelTbl.bin")

        if not os.path.exists(default_bin):
            if os.path.exists(client_bin):
                shutil.copy2(client_bin, default_bin)
            else:
                raise FileNotFoundError("未找到 PlyLevelTbl.bin 基础文件，无法应用倍率")

        try:
            with open(default_bin, "rb") as f:
                orig_data = f.read()

            scaled_bin = ConfigManager.scale_ply_level_tbl(orig_data, mult_dmg, mult_def, mult_hp)
            compressed_prs = prs_compress(scaled_bin)

            # 1. 写入客户端与服务端根目录
            for path, data in [(client_bin, scaled_bin), (client_prs, compressed_prs),
                               (server_bin, scaled_bin), (server_prs, compressed_prs)]:
                tmp = path + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, path)

            # 2. 写入服务端 param (保留原文件尾部附加字节如果存在)
            trailing = b""
            server_default_param = os.path.join(SERVER_DIR, "param", "PlyLevelTbl.bin.default")
            if os.path.exists(server_default_param):
                with open(server_default_param, "rb") as f:
                    s_orig = f.read()
                if len(s_orig) > 29184:
                    trailing = s_orig[29184:]
            elif os.path.exists(server_param_bin):
                with open(server_param_bin, "rb") as f:
                    s_orig = f.read()
                if len(s_orig) > 29184:
                    trailing = s_orig[29184:]

            param_tmp = server_param_bin + ".tmp"
            with open(param_tmp, "wb") as f:
                f.write(scaled_bin + trailing)
            os.replace(param_tmp, server_param_bin)

            write_log("INFO", f"角色战斗倍率已成功应用: 伤害(ATP/MST)={mult_dmg}X, 防御(DFP)={mult_def}X, 血量(HP)={mult_hp}X")
        except Exception as e:
            write_log("ERROR", f"应用角色战斗倍率异常: {e}", exc=True)
            raise

    @staticmethod
    def get_redbox_rate():
        from launcher_data import get_redbox_level
        return get_redbox_level(SERVER_DIR)

    @staticmethod
    def set_redbox_rate(rate):
        from launcher_data import apply_redbox_level
        apply_redbox_level(SERVER_DIR, rate)
        write_log("INFO", f"红盒概率已保存：{rate}（0 为原表，30 为约 30%）；重启服务生效")

    @staticmethod
    def set_drop_profile(rate, section_id):
        from launcher_data import apply_drop_profile, SECTION_IDS
        apply_drop_profile(SERVER_DIR, rate, section_id)
        label = SECTION_IDS[section_id] if section_id is not None else "角色原有徽章"
        write_log("INFO", f"掉落徽章已应用：{label}；红盒固定为原滑块 {rate} 档；重启服务生效")

    @staticmethod
    def get_meseta_mult():
        from launcher_data import get_meseta_multiplier
        return get_meseta_multiplier(SERVER_DIR)

    @staticmethod
    def set_meseta_mult(mult):
        from launcher_data import apply_meseta_multiplier
        apply_meseta_multiplier(SERVER_DIR, int(mult))
        write_log("INFO", f"美塞塔数量倍率已写入 160 张怪物/箱子掉落表: {mult}X；重启服务端生效")

    @staticmethod
    def get_tech_unlocked():
        """检查 tech.ini 是否处于全系 30 级全能解锁状态"""
        try:
            if os.path.exists(TECH_INI_PATH):
                with open(TECH_INI_PATH, "r", encoding="utf-8", errors="replace") as f:
                    c = f.read()
                    return "Foie,30,30" in c and "Resta,30,30" in c
        except Exception:
            pass
        return False

    @staticmethod
    def set_tech_unlocked(unlocked):
        """设置 tech.ini 开启/恢复全职业 30 级全能法术"""
        ConfigManager.ensure_default_backups()
        try:
            if unlocked:
                with open(TECH_INI_PATH, "w", encoding="utf-8") as f:
                    f.write(UNLOCKED_TECH)
                write_log("INFO", "已开启全职业 30 级全系魔法解锁")
            else:
                if os.path.exists(TECH_INI_DEFAULT):
                    shutil.copy2(TECH_INI_DEFAULT, TECH_INI_PATH)
                write_log("INFO", "已还原全职业技能等级为原版配置")
        except Exception as e:
            write_log("ERROR", f"写入技能配置错误: {e}", exc=True)

    @staticmethod
    def get_name_color():
        """读取 tethealla.ini 中的角色名称颜色预设名称"""
        try:
            if os.path.exists(TETHEALLA_INI_PATH):
                with open(TETHEALLA_INI_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.strip() for line in f]
                if len(lines) >= 48:
                    hex_val = lines[47].upper()
                    for name, code in COLOR_PRESETS.items():
                        if code == hex_val:
                            return name
        except Exception:
            pass
        return "经典原版白 (#FFFFFF)"

    @staticmethod
    def set_name_color(color_name):
        """将选定颜色代号原子写入 tethealla.ini 第 44/46/48 行"""
        hex_val = COLOR_PRESETS.get(color_name, "FFFFFF")
        try:
            if os.path.exists(TETHEALLA_INI_PATH):
                with open(TETHEALLA_INI_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.rstrip("\r\n") for line in f]
                if len(lines) >= 48:
                    lines[43] = hex_val
                    lines[45] = hex_val
                    lines[47] = hex_val
                    tmp = TETHEALLA_INI_PATH + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.write("\n".join(lines) + "\n")
                    os.replace(tmp, TETHEALLA_INI_PATH)
                    write_log("INFO", f"保存角色名称颜色成功: {color_name} -> #{hex_val}")
        except Exception as e:
            write_log("ERROR", f"保存角色名称颜色错误: {e}", exc=True)

    @staticmethod
    def load_widescreen_cfg():
        """读取 widescreen.cfg 着色器与 HUD 比例配置"""
        cfg = {"ssao": True, "hdr": True, "cel": True, "hud_scale": "1.0"}
        if os.path.exists(WIDESCREEN_CFG_PATH):
            try:
                with open(WIDESCREEN_CFG_PATH, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        s = line.strip()
                        if "=" in s:
                            k, v = s.split("=", 1)
                            k, v = k.strip().lower(), v.strip()
                            if k == "ssao": cfg["ssao"] = (v == "1")
                            elif k == "hdr": cfg["hdr"] = (v == "1")
                            elif k == "celshader": cfg["cel"] = (v == "1")
                            elif k == "hudscale": cfg["hud_scale"] = v
            except Exception: pass
        return cfg

    @staticmethod
    def save_widescreen_cfg(cfg):
        """原子写入 widescreen.cfg (SMAA=0 保证2D文字极致锐利，MSAA=1 保证3D边缘平滑，默认1.0X原生点阵清晰)"""
        try:
            raw_hud = str(cfg.get("hud_scale", "1.0"))
            hud_val = "1.0"
            if "1.5" in raw_hud: hud_val = "1.5"
            elif "1.25" in raw_hud: hud_val = "1.25"

            lines = [
                f"MSAA=1\n",
                f"SMAA=0\n",
                f"SSAO={1 if cfg.get('ssao', False) else 0}\n",
                f"CelShader={1 if cfg.get('cel', False) else 0}\n",
                f"DOF=0\n",
                f"HDR={1 if cfg.get('hdr', False) else 0}\n",
                f"HUDScale={hud_val}\n",
            ]
            tmp = WIDESCREEN_CFG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(lines)
            os.replace(tmp, WIDESCREEN_CFG_PATH)
            write_log("INFO", f"保存 widescreen.cfg 成功 (HUDScale={hud_val}, CelShader={lines[3].strip()})")
        except Exception as e:
            write_log("ERROR", f"保存 widescreen.cfg 错误: {e}", exc=True)
            raise

    @staticmethod
    def load_server_config():
        """从固定行号读取 ship.ini 与 tethealla.ini"""
        ConfigManager.ensure_default_backups()
        config = {
            "exp_boost": 1,
            "drop_weapon": 30,
            "drop_armor": 20,
            "drop_tool": 50,
            "drop_meseta": 40,
            "meseta_mult": ConfigManager.get_meseta_mult(),
            "drop_mag": 1,
            "event_id": 0,
            "rare_mob_mult": 1,
            "drop_redbox": ConfigManager.get_redbox_rate(),
            "unlock_tech_30": ConfigManager.get_tech_unlocked(),
            "name_color": ConfigManager.get_name_color(),
            "dmg_mult": "4X (畅爽推荐)",
            "def_mult": "4X (畅爽推荐)",
            "hp_mult": "4X (畅爽推荐)",
        }

        # 读取 ship.ini
        if os.path.exists(SHIP_INI_PATH):
            try:
                with open(SHIP_INI_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.strip() for line in f]
                if len(lines) >= 37:
                    try: config["event_id"] = int(lines[20])
                    except (ValueError, IndexError): pass
                    try: config["drop_weapon"] = max(0, min(100, int(lines[26]) // 1000))
                    except (ValueError, IndexError): pass
                    try: config["drop_armor"] = max(0, min(100, int(lines[28]) // 1000))
                    except (ValueError, IndexError): pass
                    try: config["drop_mag"] = max(0, min(100, int(lines[30]) // 1000))
                    except (ValueError, IndexError): pass
                    try: config["drop_tool"] = max(0, min(100, int(lines[32]) // 1000))
                    except (ValueError, IndexError): pass
                    try: config["drop_meseta"] = max(0, min(100, int(lines[34]) // 1000))
                    except (ValueError, IndexError): pass
                    try: config["exp_boost"] = max(1, min(99, int(lines[36])))
                    except (ValueError, IndexError): pass
            except Exception as e:
                write_log("ERROR", f"读取 ship.ini 错误: {e}", exc=True)

        # 读取 tethealla.ini 中的 Rappies 行 (第 30 行)
        if os.path.exists(TETHEALLA_INI_PATH):
            try:
                with open(TETHEALLA_INI_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.strip() for line in f]
                if len(lines) >= 30:
                    try:
                        rate = int(lines[29])
                        config["rare_mob_mult"] = max(1, min(25, rate // 8))
                    except (ValueError, IndexError): pass
            except Exception as e:
                write_log("ERROR", f"读取 tethealla.ini 错误: {e}", exc=True)

        return config

    @staticmethod
    def save_server_config(config):
        """严格按行号就地替换数值，带哨兵校验与原子写回"""
        ConfigManager.ensure_default_backups()

        from launcher_data import get_drop_section_id
        ConfigManager.set_drop_profile(20, get_drop_section_id(SERVER_DIR))
        ConfigManager.set_meseta_mult(config.get("meseta_mult", 1))
        ConfigManager.set_tech_unlocked(config.get("unlock_tech_30", False))

        mult_dmg = parse_mult(config.get("dmg_mult", "4X (畅爽推荐)"))
        mult_def = parse_mult(config.get("def_mult", "4X (畅爽推荐)"))
        mult_hp = parse_mult(config.get("hp_mult", "4X (畅爽推荐)"))
        ConfigManager.apply_stats_multipliers(mult_dmg, mult_def, mult_hp)

        # 1. 保存 ship.ini (总行数固定为 39 行，CRLF，无 BOM)
        if os.path.exists(SHIP_INI_PATH):
            try:
                with open(SHIP_INI_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.rstrip("\r\n") for line in f]

                if len(lines) != 39 and len(lines) != 40:
                    raise ValueError(f"ship.ini 行数异常 ({len(lines)} 行)，拒绝写入以防服务端错位")
                if "100000" not in lines[22] or "Experience" not in lines[35]:
                    raise ValueError("ship.ini 哨兵注释未匹配，可能行结构已被破坏")

                w_drop = max(0, min(100000, config['drop_weapon'] * 1000))
                a_drop = max(0, min(100000, config['drop_armor'] * 1000))
                m_drop = max(0, min(100000, config['drop_mag'] * 1000))
                t_drop = max(0, min(100000, config['drop_tool'] * 1000))
                ms_drop = max(0, min(100000, config['drop_meseta'] * 1000))
                exp_b = max(1, min(99, config['exp_boost']))
                ev_id = max(0, min(15, config['event_id']))

                lines[4] = "127.0.0.1"
                lines[16] = "127.0.0.1"
                lines[20] = str(ev_id)
                lines[26] = str(w_drop)
                lines[28] = str(a_drop)
                lines[30] = str(m_drop)
                lines[32] = str(t_drop)
                lines[34] = str(ms_drop)
                lines[36] = str(exp_b)

                tmp_path = SHIP_INI_PATH + ".tmp"
                with open(tmp_path, "wb") as f:
                    content = "\r\n".join(lines).encode("utf-8")
                    if not content.endswith(b"\r\n"):
                        content += b"\r\n"
                    f.write(content)
                os.replace(tmp_path, SHIP_INI_PATH)
                write_log("INFO", "ship.ini 保存成功")
            except Exception as e:
                write_log("ERROR", f"写入 ship.ini 错误: {e}", exc=True)
                raise

        # 2. 保存 tethealla.ini (总行数固定为 48 行，CRLF，无 BOM)
        if os.path.exists(TETHEALLA_INI_PATH):
            try:
                with open(TETHEALLA_INI_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.rstrip("\r\n") for line in f]

                if len(lines) != 48 and len(lines) != 49:
                    raise ValueError(f"tethealla.ini 行数异常 ({len(lines)} 行)，拒绝写入以防服务端错位")
                if "divided by 1000" not in lines[24] or "Kondrieu" not in lines[40]:
                    raise ValueError("tethealla.ini 哨兵注释未匹配，可能行结构已被破坏")

                mult = max(1, min(25, config["rare_mob_mult"]))
                lines[13] = "127.0.0.1"
                lines[15] = "Welcome to PSOBB Offline Server"
                lines[27] = str(min(100000, 7 * mult))
                lines[29] = str(min(100000, 8 * mult))
                lines[31] = str(min(100000, 8 * mult))
                lines[33] = str(min(100000, 7 * mult))
                lines[35] = str(min(100000, 7 * mult))
                lines[37] = str(min(100000, 7 * mult))
                lines[39] = str(min(100000, 7 * mult))
                lines[41] = str(min(100000, 10000 * mult))

                hex_col = COLOR_PRESETS.get(config.get("name_color"), "FFFFFF")
                if len(lines) >= 48:
                    lines[43] = hex_col
                    lines[45] = hex_col
                    lines[47] = hex_col

                tmp_path = TETHEALLA_INI_PATH + ".tmp"
                with open(tmp_path, "wb") as f:
                    content = "\r\n".join(lines).encode("utf-8")
                    if not content.endswith(b"\r\n"):
                        content += b"\r\n"
                    f.write(content)
                os.replace(tmp_path, TETHEALLA_INI_PATH)
                write_log("INFO", "tethealla.ini 保存成功")
            except Exception as e:
                write_log("ERROR", f"写入 tethealla.ini 错误: {e}", exc=True)
                raise

    @staticmethod
    def get_ship_port():
        """从 ship.ini 第 8 行读取主舰服务主端口 (默认 15278)"""
        try:
            if os.path.exists(SHIP_INI_PATH):
                with open(SHIP_INI_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.strip() for line in f]
                if len(lines) >= 8 and lines[7].isdigit():
                    p = int(lines[7])
                    if 1024 <= p <= 65530:
                        return p
        except Exception as e:
            write_log("WARN", f"读取 ship.ini 主舰端口异常: {e}")
        return 15278

    @staticmethod
    def is_port_bindable(port):
        """测试端口是否可在 0.0.0.0 上成功 bind 监听 (检测外部系统进程占用)"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('0.0.0.0', port))
                return True
            except Exception:
                return False

    @staticmethod
    def ensure_clean_ship_port():
        """智能检测主舰端口及分线 (Block) 端口冲突，如遇外部占用则自动迁移至纯净端口"""
        cur_port = ConfigManager.get_ship_port()
        conflict = False
        for p in [cur_port, cur_port + 1, cur_port + 2]:
            if not ConfigManager.is_port_bindable(p):
                conflict = True
                write_log("WARN", f"检测到主舰/分线端口 {p} 被外部系统进程占用")
                break

        if not conflict:
            return cur_port

        candidate = 15278
        for offset in range(0, 1000, 10):
            test_base = candidate + offset
            if (ConfigManager.is_port_bindable(test_base) and
                ConfigManager.is_port_bindable(test_base + 1) and
                ConfigManager.is_port_bindable(test_base + 2)):
                candidate = test_base
                break

        write_log("INFO", f"自动避让端口冲突，切换主舰端口: {cur_port} -> {candidate}")
        if os.path.exists(SHIP_INI_PATH):
            try:
                with open(SHIP_INI_PATH, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.rstrip("\r\n") for line in f]
                if len(lines) >= 8:
                    lines[7] = str(candidate)
                    tmp_path = SHIP_INI_PATH + ".tmp"
                    with open(tmp_path, "wb") as f:
                        f.write(("\r\n".join(lines) + "\r\n").encode("utf-8"))
                    os.replace(tmp_path, SHIP_INI_PATH)
                    write_log("INFO", f"已成功将安全可用端口 {candidate} 写入 ship.ini 第 8 行")
            except Exception as e:
                write_log("ERROR", f"更新 ship.ini 端口失败: {e}", exc=True)
        return candidate

    @staticmethod
    def load_client_settings():
        """读取客户端画面与着色器设置"""
        settings = {
            "screen_mode": DEFAULT_MODE,
            "window_scale": "2X 高清窗口 (1280×960 推荐)",
            "display_mode": "2X 高清窗口 (1280×960 推荐)",
            "font_choice": "宋体 (像素点阵 超清晰推荐)",
            "antialiasing": "off",
            "auto_login": True,
            "auto_backup": True,
            "auto_kill": True,
            "hud_scale": "1.0 (原生锐利清晰，推荐)",
            "ssao": False,
            "hdr": False,
            "cel": False,
        }
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\SonicTeam\PSOBB", 0, winreg.KEY_READ)
            cur_res, _ = winreg.QueryValueEx(k, "Resolution")
            cur_win = 1
            try: cur_win, _ = winreg.QueryValueEx(k, "WINDOW_MODE")
            except Exception: pass
            try:
                cur_font, _ = winreg.QueryValueEx(k, "FONT_JPN")
                for k_name, f_code in FONT_PRESETS.items():
                    if f_code.lower() == str(cur_font).lower():
                        settings["font_choice"] = k_name
                        break
            except Exception: pass
            winreg.CloseKey(k)
            if cur_win != 0:
                for k_name, p in WINDOW_SCALE_PRESETS.items():
                    if p["mode"] == "window" and p["res_id"] == cur_res:
                        settings["window_scale"] = k_name
                        settings["display_mode"] = k_name
                        break
        except Exception:
            pass

        if os.path.exists(DGVOODOO_CONF_PATH):
            try:
                with open(DGVOODOO_CONF_PATH, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        s = line.strip()
                        if s.startswith("OutputAPI"):
                            parts = s.split("=")
                            if len(parts) > 1:
                                raw_api = parts[1].strip()
                                for k_api, code in RENDER_API_PRESETS.items():
                                    if code == raw_api:
                                        settings["output_api"] = k_api
                                        break
                        elif s.startswith("Antialiasing"):
                            parts = s.split("=")
                            if len(parts) > 1:
                                settings["antialiasing"] = parts[1].strip()
            except Exception:
                pass

        ws = ConfigManager.load_widescreen_cfg()
        settings.update(ws)
        raw_h = str(ws.get("hud_scale", "1.0"))
        if "1.5" in raw_h: settings["hud_scale"] = "1.5 (大界面缩放)"
        elif "1.25" in raw_h: settings["hud_scale"] = "1.25 (适度微调放大)"
        else: settings["hud_scale"] = "1.0 (原生锐利清晰，推荐)"
        return settings

    @staticmethod
    def save_client_settings(settings):
        """写入注册表、dgVoodoo.conf 与 widescreen.cfg (4:3 原生窗口与自适应缩放)"""
        win_scale = settings.get("window_scale") or settings.get("display_mode") or "2X 高清窗口 (1280×960 推荐)"
        p_info = WINDOW_SCALE_PRESETS.get(win_scale, WINDOW_SCALE_PRESETS["2X 高清窗口 (1280×960 推荐)"])
        profile = display_profile(settings.get("screen_mode", DEFAULT_MODE),
                                  (p_info["w"], p_info["h"]), desktop_size())
        res_id = p_info["res_id"]

        api_name = settings.get("output_api", "DirectX 11 (流畅推荐)")
        api_code = RENDER_API_PRESETS.get(api_name, "d3d11_fl11_0")

        try:
            k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\SonicTeam\PSOBB")
            # Native fullscreen exits on WM_ACTIVATE/WA_INACTIVE (0x82C57C).
            # Keep the client windowed; dgVoodoo controls presentation independently.
            win_val = 1
            winreg.SetValueEx(k, "WINDOW_MODE", 0, winreg.REG_DWORD, win_val)
            winreg.SetValueEx(k, "windowmode", 0, winreg.REG_DWORD, win_val)
            winreg.SetValueEx(k, "Resolution", 0, winreg.REG_DWORD, res_id)
            # GRAPHICCTRL's first DWORD is the original graphics preset:
            # 0=High End, 1=Normal, 2=Low End, 3=custom.  Keep custom/Low End
            # choices and all detailed graphics fields intact.
            try:
                graphic_ctrl, graphic_type = winreg.QueryValueEx(k, "GRAPHICCTRL")
                if graphic_type != winreg.REG_BINARY or len(graphic_ctrl) != 36:
                    raise ValueError("invalid GRAPHICCTRL")
            except (OSError, ValueError, TypeError):
                graphic_ctrl = (1).to_bytes(4, "little") + bytes.fromhex(
                    "0000000000000000000000000100000001000000010000000000000000000000")
            if int.from_bytes(graphic_ctrl[:4], "little") == 1:
                winreg.SetValueEx(k, "GRAPHICCTRL", 0, winreg.REG_BINARY,
                                  b"\x00\x00\x00\x00" + graphic_ctrl[4:])
            try:
                old_ctrl, value_type = winreg.QueryValueEx(k, "CTRLBUF")
                if value_type != winreg.REG_BINARY or len(old_ctrl) < 12:
                    raise ValueError("invalid CTRLBUF")
            except (OSError, ValueError, TypeError):
                old_ctrl = b"\x00" * 4 + b"\x01\x00\x00\x00" * 2
            ctrlbuf = res_id.to_bytes(4, "little") + old_ctrl[4:]
            winreg.SetValueEx(k, "CTRLBUF", 0, winreg.REG_BINARY, ctrlbuf)

            # 写入字体设置
            font_choice = settings.get("font_choice", "宋体 (像素点阵 超清晰推荐)")
            font_code = FONT_PRESETS.get(font_choice, "SimSun")
            winreg.SetValueEx(k, "FONT_JPN", 0, winreg.REG_SZ, font_code)

            # 离线单机自动填充 admin 账号与密码，并配置本地免外部补丁直连
            winreg.SetValueEx(k, "ACCOUNT", 0, winreg.REG_SZ, "admin")
            winreg.SetValueEx(k, "ACCOUNT_CHECK", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "PASSWORD_CHECK", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "PASSWORD", 0, winreg.REG_BINARY, b"admin\x00" + b"\x00" * 42)
            winreg.SetValueEx(k, "UpdateADDRESS", 0, winreg.REG_SZ, "http://127.0.0.1/")
            winreg.CloseKey(k)
        except Exception as e:
            write_log("WARN", f"注册表参数配置错误: {e}")
            raise

        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers") as key:
                stale_keys = []
                idx = 0
                while True:
                    try:
                        name, _, _ = winreg.EnumValue(key, idx)
                        idx += 1
                    except OSError:
                        break
                    if "psobb.exe" in name.lower() and name.lower() != PSOBB_EXE.lower():
                        stale_keys.append(name)
                for old_entry in stale_keys:
                    try: winreg.DeleteValue(key, old_entry)
                    except Exception: pass
                winreg.SetValueEx(key, PSOBB_EXE, 0, winreg.REG_SZ, "~ HIGHDPIAWARE DisableNXShowUI")
        except Exception as e:
            write_log("WARN", f"DEP 兼容层规则维护错误: {e}")

        try:
            old_text = Path(DGVOODOO_CONF_PATH).read_text(encoding='utf-8') if os.path.exists(DGVOODOO_CONF_PATH) else ''
            new_text = update_dgvoodoo(old_text, profile)
            new_text = update_ini(new_text, {
                'General': {'OutputAPI': api_code},
                'GeneralExt': {'FPSLimit': '0', 'Resampling': 'point'},
                'DirectX': {'Antialiasing': settings.get('antialiasing', 'off') if profile['mode'] == 'window' else 'off',
                            'Filtering': 'appdriven', 'KeepFilterIfPointSampled': 'true',
                            'Bilinear2DOperations': 'false', 'VRAM': '2048',
                            'FastVideoMemoryAccess': 'true', 'ForceVerticalSync': 'true',
                            'dgVoodooWatermark': 'false'},
            })
            Path(DGVOODOO_CONF_PATH + '.tmp').write_text(new_text, encoding='utf-8')
            os.replace(DGVOODOO_CONF_PATH + '.tmp', DGVOODOO_CONF_PATH)
            write_log('INFO', f"显示配置已保存: 后端={api_code}, 模式={profile['mode']}, 4:3 尺寸={profile['render']}")
        except Exception as error:
            write_log('ERROR', f'更新 dgVoodoo.conf 失败: {error}', exc=True)
            raise

        width, height = profile['render']
        display_path = os.path.join(CLIENT_DIR, 'launcher_display.ini')
        with open(display_path + '.tmp', 'w', encoding='ascii') as f:
            f.write(f'[Display]\nWidth={width}\nHeight={height}\nMode={profile["mode"]}\n')
        os.replace(display_path + '.tmp', display_path)
        ConfigManager.save_widescreen_cfg(settings)

    @staticmethod
    def get_account_hash():
        if not os.path.exists(ACCOUNT_DAT_PATH):
            return None
        h = hashlib.sha256()
        with open(ACCOUNT_DAT_PATH, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def backup_account(tag="auto"):
        if not os.path.exists(ACCOUNT_DAT_PATH):
            return False, "account.dat 尚未生成，跳过备份"

        size = os.path.getsize(ACCOUNT_DAT_PATH)
        if size < 64:
            return False, f"account.dat 体积异常 ({size} 字节 < 64)，中止备份以防污染历史归档"

        curr_hash = ConfigManager.get_account_hash()
        os.makedirs(SAVES_BACKUP_DIR, exist_ok=True)

        all_backups = [
            os.path.join(SAVES_BACKUP_DIR, f)
            for f in os.listdir(SAVES_BACKUP_DIR)
            if f.startswith("account_") and f.endswith(".dat")
        ]
        if all_backups:
            all_backups.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            latest = all_backups[0]
            if os.path.getsize(latest) == size:
                lh = hashlib.sha256()
                with open(latest, "rb") as lf:
                    while chunk := lf.read(65536): lh.update(chunk)
                companions_match = all(
                    not os.path.exists(os.path.join(SERVER_DIR, name + ".dat")) or (
                        os.path.exists(os.path.join(SAVES_BACKUP_DIR, name + "_" + os.path.basename(latest)[8:])) and
                        Path(SERVER_DIR, name + ".dat").read_bytes() ==
                        Path(SAVES_BACKUP_DIR, name + "_" + os.path.basename(latest)[8:]).read_bytes()
                    ) for name in ("character", "bank")
                )
                if lh.hexdigest() == curr_hash and companions_match:
                    return True, "账号、角色和仓库均无变动，跳过冗余快照"

        today_str = time.strftime("%Y%m%d")
        daily_dst = os.path.join(SAVES_BACKUP_DIR, f"account_daily_{today_str}.dat")
        if not os.path.exists(daily_dst):
            try: shutil.copy2(ACCOUNT_DAT_PATH, daily_dst)
            except Exception: pass

        timestamp = time.strftime("%Y%m%d_%H%M%S") + f"_{time.time_ns() % 1000000000:09d}"
        session_dst = os.path.join(SAVES_BACKUP_DIR, f"account_{tag}_{timestamp}.dat")
        shutil.copy2(ACCOUNT_DAT_PATH, session_dst)

        # 同步备份角色数据与仓库数据
        char_path = os.path.join(SERVER_DIR, "character.dat")
        bank_path = os.path.join(SERVER_DIR, "bank.dat")
        if os.path.exists(char_path) and os.path.getsize(char_path) > 0:
            try: shutil.copy2(char_path, os.path.join(SAVES_BACKUP_DIR, f"character_{tag}_{timestamp}.dat"))
            except Exception: pass
        if os.path.exists(bank_path) and os.path.getsize(bank_path) > 0:
            try: shutil.copy2(bank_path, os.path.join(SAVES_BACKUP_DIR, f"bank_{tag}_{timestamp}.dat"))
            except Exception: pass

        session_files = []
        daily_files = []
        try:
            for f in os.listdir(SAVES_BACKUP_DIR):
                p = os.path.join(SAVES_BACKUP_DIR, f)
                if not os.path.isfile(p):
                    continue
                if (f.startswith("account_prelaunch_") or f.startswith("account_exit_") or f.startswith("account_auto_") or f.startswith("account_session_")) and f.endswith(".dat"):
                    session_files.append((os.path.getmtime(p), p))
                elif f.startswith("account_daily_") and f.endswith(".dat"):
                    daily_files.append((os.path.getmtime(p), p))
        except Exception:
            pass

        session_files.sort(key=lambda x: x[0])
        if len(session_files) > 15:
            for _, old_f in session_files[:-15]:
                try: os.remove(old_f)
                except Exception: pass

        daily_files.sort(key=lambda x: x[0])
        if len(daily_files) > 30:
            for _, old_f in daily_files[:-30]:
                try: os.remove(old_f)
                except Exception: pass

        msg = f"已安全保存全量存档快照 (账号+角色+仓库): {os.path.basename(session_dst)}"
        write_log("INFO", msg)
        return True, msg


# ==============================================================================
# 服务端生命周期管理类
# ==============================================================================
class ServerProcessManager:
    server_processes = []

    @staticmethod
    def is_port_listening(port, timeout=0.3):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex(('127.0.0.1', port)) == 0

    @classmethod
    def is_server_running(cls):
        ship_port = ConfigManager.get_ship_port()
        return cls.is_port_listening(12000) and cls.is_port_listening(ship_port)

    @classmethod
    def kill_all_servers(cls):
        write_log("INFO", "开始停止本地单机服务端...")
        ship_port = ConfigManager.get_ship_port()
        for p in cls.server_processes:
            try: p.terminate()
            except Exception: pass

        deadline = time.time() + 2.0
        while time.time() < deadline:
            if not cls.is_port_listening(12000) and not cls.is_port_listening(ship_port):
                break
            time.sleep(0.2)

        cls.server_processes.clear()

        write_log("INFO", "服务端进程清理完成")

    @classmethod
    def start_all_servers(cls, status_callback=None, redbox_rate=None, meseta_mult=None, drop_section_id=None):
        write_log("INFO", "开始拉起本地单机服务流程...")

        # 智能检测主舰与分线端口冲突，必要时自动避让
        ship_port = ConfigManager.ensure_clean_ship_port()

        if cls.is_port_listening(12000) or cls.is_port_listening(ship_port):
            if not cls.server_processes:
                if status_callback: status_callback("服务端端口已被其他进程占用，请先关闭占用程序。")
                write_log("WARN", "端口被非本启动器管理的进程占用，拒绝结束其他进程")
                return False

        # 在 ship_server 尚未启动运行前，安全写入红箱爆率与美塞塔掉落数量倍率
        if redbox_rate is not None:
            ConfigManager.set_drop_profile(redbox_rate, drop_section_id)
        if meseta_mult is not None:
            ConfigManager.set_meseta_mult(meseta_mult)

        flags = 0x08000000  # CREATE_NO_WINDOW
        patch_exe = os.path.join(SERVER_DIR, "patch_server.exe")
        login_exe = os.path.join(SERVER_DIR, "login_server.exe")
        ship_exe = os.path.join(SERVER_DIR, "ship_server.exe")

        if not os.path.exists(login_exe) or not os.path.exists(ship_exe):
            err_msg = f"未找到服务端核心可执行文件！请确认路径：\n{login_exe}\n{ship_exe}"
            write_log("ERROR", err_msg)
            if status_callback: status_callback(err_msg)
            return False

        try:
            # 0. 启动本地补丁服务 (patch_server, 监听端口 11000/11001，为客户端提供无感快速握手)
            if os.path.exists(patch_exe):
                if status_callback: status_callback("正在启动本地补丁网关 (patch_server)...")
                write_log("INFO", f"启动本地补丁网关: {patch_exe}")
                p_patch = subprocess.Popen([patch_exe], cwd=SERVER_DIR, creationflags=flags)
                GLOBAL_JOB.assign_process(p_patch._handle)
                cls.server_processes.append(p_patch)

                patch_ready = False
                for _ in range(20):
                    time.sleep(0.25)
                    if p_patch.poll() is not None:
                        write_log("WARN", f"patch_server 退出 (返回码: {p_patch.returncode})")
                        break
                    if cls.is_port_listening(11000):
                        patch_ready = True
                        break
                if patch_ready:
                    write_log("INFO", "patch_server 端口 11000 已激活就绪")

            if status_callback: status_callback("正在启动认证网关 (login_server)...")
            write_log("INFO", f"启动认证网关: {login_exe}")
            p_login = subprocess.Popen([login_exe], cwd=SERVER_DIR, creationflags=flags)
            GLOBAL_JOB.assign_process(p_login._handle)
            cls.server_processes.append(p_login)

            login_ready = False
            for _ in range(20):
                time.sleep(0.25)
                if p_login.poll() is not None:
                    err = f"login_server 启动后异常退出 (返回码: {p_login.returncode})"
                    write_log("ERROR", err)
                    if status_callback: status_callback(err)
                    cls.kill_all_servers()
                    return False
                if cls.is_port_listening(12000):
                    login_ready = True
                    break

            if not login_ready:
                err = "login_server 启动超时 (端口 12000 未就绪)"
                write_log("ERROR", err)
                if status_callback: status_callback(err)
                cls.kill_all_servers()
                return False

            if status_callback: status_callback(f"正在启动主舰服务 (ship_server, 端口 {ship_port})...")
            write_log("INFO", f"启动主舰服务: {ship_exe} (端口 {ship_port})")
            p_ship = subprocess.Popen([ship_exe], cwd=SERVER_DIR, creationflags=flags)
            GLOBAL_JOB.assign_process(p_ship._handle)
            cls.server_processes.append(p_ship)

            ship_ready = False
            for _ in range(60):
                time.sleep(0.25)
                if p_ship.poll() is not None:
                    err = f"ship_server 启动后异常退出 (返回码: {p_ship.returncode})"
                    write_log("ERROR", err)
                    if status_callback: status_callback(err)
                    cls.kill_all_servers()
                    return False
                if cls.is_port_listening(ship_port):
                    ship_ready = True
                    break

            if not ship_ready:
                err = f"ship_server 启动超时 (端口 {ship_port} 未就绪)"
                write_log("ERROR", err)
                if status_callback: status_callback(err)
                cls.kill_all_servers()
                return False

            # 等待 1.5 秒让 ship_server 与 login_server 3455 端口完成主舰注册与握手
            time.sleep(1.5)

            msg = f"服务端就绪！127.0.0.1 本地回环网络链路已激活 (主舰端口: {ship_port})。"
            write_log("INFO", msg)
            if status_callback: status_callback(msg)
            return True
        except Exception as e:
            err = f"拉起服务端出错: {e}"
            write_log("ERROR", err, exc=True)
            if status_callback: status_callback(err)
            cls.kill_all_servers()
            return False


# ==============================================================================
# GUI 启动器主界面
# ==============================================================================
class PSOBBLauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("梦幻之星网络版 (PSOBB) · 哔哩哔哩：metalmouse")
        self.root.minsize(980, 660)
        self.root.resizable(True, True)

        # 设置窗口图标为 PsoBB.exe 官方图标
        ico_path = os.path.join(BASE_DIR, "psobb.ico")
        if not os.path.exists(ico_path):
            ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "psobb.ico")
        if os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception:
                pass

        self.c_bg = "#0c1421"
        self.c_card = "#131f30"
        self.c_cyan = "#70ded3"
        self.c_text = "#e6edf3"
        self.c_subtext = "#a3b4c9"
        self.c_green = "#00e676"
        self.c_red = "#ff5252"
        self.c_gold = "#ffca28"

        self.root.configure(bg=self.c_bg)

        # 启动自检与基础信息记录
        write_log("INFO", "=" * 60)
        write_log("INFO", "PSOBB 一键单机启动器启动")
        write_log("INFO", f"BASE_DIR: {BASE_DIR}")
        write_log("INFO", f"Frozen (PyInstaller): {getattr(sys, 'frozen', False)}")
        write_log("INFO", f"PSOBB_EXE 存在状态: {os.path.exists(PSOBB_EXE)} ({PSOBB_EXE})")
        write_log("INFO", f"ITEM_MAKER 存在状态: {os.path.exists(ITEM_MAKER_EXE)}")
        write_log("INFO", f"TETHMAN 存在状态: {os.path.exists(TETHMAN_EXE)}")

        self.server_cfg = ConfigManager.load_server_config()
        self.client_cfg = ConfigManager.load_client_settings()
        self.is_game_running = False

        self.init_window_state()
        self.init_ui()
        self.start_status_daemon()

    def init_window_state(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        def_w, def_h = min(1240, sw - 80), min(860, sh - 100)
        def_x = max(0, (sw - def_w) // 2)
        def_y = max(0, (sh - def_h) // 2)
        self.last_normal_geom = (def_w, def_h, def_x, def_y)

        self.ui_cfg = configparser.ConfigParser()
        loaded = False
        try:
            if os.path.exists(UI_INI_PATH):
                self.ui_cfg.read(UI_INI_PATH, encoding="utf-8")
                if self.ui_cfg.has_section("UI"):
                    w = self.ui_cfg.getint("UI", "window_width", fallback=def_w)
                    h = self.ui_cfg.getint("UI", "window_height", fallback=def_h)
                    x = self.ui_cfg.getint("UI", "window_x", fallback=def_x)
                    y = self.ui_cfg.getint("UI", "window_y", fallback=def_y)
                    is_zoomed = self.ui_cfg.getboolean("UI", "is_maximized", fallback=False)

                    # 校验尺寸合理性，防越界缩小
                    w = min(max(w, 980), max(980, sw - 40))
                    h = min(max(h, 660), max(660, sh - 80))
                    x = min(max(0, x), max(0, sw - w))
                    y = min(max(0, y), max(0, sh - h - 40))
                    self.last_normal_geom = (w, h, x, y)
                    self.root.geometry(f"{w}x{h}+{x}+{y}")
                    if is_zoomed:
                        self.root.after(80, lambda: self.root.state("zoomed"))
                    loaded = True
                    write_log("INFO", f"从 launcher_ui.ini 恢复窗口尺寸: {w}x{h}+{x}+{y}, zoomed={is_zoomed}")
        except Exception as e:
            write_log("WARN", f"读取 launcher_ui.ini 异常: {e}")

        if not loaded:
            self.root.geometry(f"{def_w}x{def_h}+{def_x}+{def_y}")

        self.root.bind("<Configure>", self.on_window_configure)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)

    def on_window_configure(self, event):
        if event.widget == self.root:
            if self.root.state() != "zoomed":
                w = self.root.winfo_width()
                h = self.root.winfo_height()
                x = self.root.winfo_x()
                y = self.root.winfo_y()
                if w >= 500 and h >= 400:
                    self.last_normal_geom = (w, h, x, y)

    def save_ui_state(self):
        """退出或保存时全量持久化窗口尺寸与所有参数到 launcher_ui.ini"""
        try:
            is_zoomed = (self.root.state() == "zoomed")
            w, h, x, y = self.last_normal_geom
            cfg = configparser.ConfigParser()
            if os.path.exists(UI_INI_PATH):
                cfg.read(UI_INI_PATH, encoding="utf-8")
            if not cfg.has_section("UI"):
                cfg.add_section("UI")

            cfg.set("UI", "window_width", str(w))
            cfg.set("UI", "window_height", str(h))
            cfg.set("UI", "window_x", str(x))
            cfg.set("UI", "window_y", str(y))
            cfg.set("UI", "is_maximized", str(is_zoomed))

            # 全量持久化当前界面选定值
            cfg.set("UI", "exp_boost", str(self.var_exp.get()))
            cfg.set("UI", "rare_mob_mult", str(self.var_rare.get()))
            cfg.remove_option("UI", "drop_redbox")
            cfg.set("UI", "drop_section_choice", str(self.var_drop_section.get()))
            cfg.set("UI", "meseta_mult", str(self.scale_meseta_mult.get()))
            cfg.set("UI", "event_id", str(EVENT_REVERSE_MAP.get(self.var_event.get(), 0)))
            cfg.set("UI", "name_color", str(self.var_name_color.get()))
            cfg.set("UI", "unlock_tech_30", str(self.var_unlock_tech.get()))
            cfg.set("UI", "dmg_mult", str(self.var_dmg_mult.get()))
            cfg.set("UI", "def_mult", str(self.var_def_mult.get()))
            cfg.set("UI", "hp_mult", str(self.var_hp_mult.get()))

            for k, s in self.sliders.items():
                cfg.set("UI", k, str(s.get()))

            cfg.set("UI", "output_api", str(self.var_render_api.get()))
            cfg.set("UI", "window_scale", str(self.var_win_mode.get()))
            cfg.set("UI", "display_mode", str(self.var_win_mode.get()))
            cfg.set("UI", "screen_mode", str(self.var_screen_mode.get()))
            cfg.set("UI", "font_choice", str(self.var_font.get()))
            cfg.set("UI", "antialiasing", str(self.var_aa.get()))
            cfg.set("UI", "hud_scale", str(self.var_hud_scale.get()))
            cfg.set("UI", "ssao", str(self.var_ssao.get()))
            cfg.set("UI", "hdr", str(self.var_hdr.get()))
            cfg.set("UI", "cel", str(self.var_cel.get()))
            cfg.set("UI", "auto_login", str(self.var_auto_login.get()))
            cfg.set("UI", "auto_backup", str(self.var_auto_backup.get()))
            cfg.set("UI", "auto_kill", str(self.var_auto_kill.get()))

            with open(UI_INI_PATH, "w", encoding="utf-8") as f:
                cfg.write(f)
            self.ui_cfg = cfg
            write_log("INFO", f"保存 UI 与配置全量持久化至: {UI_INI_PATH}")
        except Exception as e:
            write_log("ERROR", f"写入 launcher_ui.ini 错误: {e}", exc=True)

    def on_close_window(self):
        """窗口关闭时自动检测游戏与服务端状态，确认退出并保存配置"""
        server_alive = ServerProcessManager.is_server_running()
        game_alive = self.is_game_running or is_psobb_process_alive()

        if game_alive:
            messagebox.showwarning("请先退出游戏", "请在游戏内正常退出，等待存档完成后再关闭启动器。")
            return

        if game_alive or server_alive:
            detail = []
            if game_alive: detail.append("游戏客户端 (PsoBB.exe) 仍在运行")
            if server_alive: detail.append("单机服务端核心进程仍在运行")
            status_text = "、".join(detail)

            ans = messagebox.askyesno(
                "确认退出",
                f"检测到当前：{status_text}。\n\n若直接关闭启动器，后台服务端将被立即终止，导致游戏连接中断！\n\n确定要退出启动器并关闭服务吗？"
            )
            if not ans:
                write_log("INFO", "用户取消了关闭启动器主窗口操作")
                return

            if game_alive:
                write_log("INFO", "退出前执行安全存档快照备份...")
                ConfigManager.backup_account(tag="exit")
            ServerProcessManager.kill_all_servers()

        try:
            s_cfg, c_cfg = self.get_ui_config()
            ConfigManager.save_server_config(s_cfg)
            ConfigManager.save_client_settings(c_cfg)
        except Exception:
            pass
        self.save_ui_state()
        write_log("INFO", "启动器主窗口正常退出")
        self.root.destroy()

    def init_ui(self):
        from launcher_theme import build_ui
        build_ui(self, {
            "events": EVENT_MAP, "colors": COLOR_PRESETS,
            "drop_sections": DROP_SECTION_CHOICES,
            "stats": STATS_MULT_PRESETS, "render": RENDER_API_PRESETS,
            "window": WINDOW_SCALE_PRESETS, "fonts": FONT_PRESETS,
            "screen_modes": MODES,
            "hud": HUD_SCALE_PRESETS,
        })

    def log(self, msg, level="INFO"):
        write_log(level, msg)
        def _update():
            try: self.log_lbl.config(text=msg)
            except Exception: pass
        try: self.root.after(0, _update)
        except Exception: pass

    def open_log_file(self):
        """一键打开运行日志文件 launcher.log"""
        try:
            if not os.path.exists(LOG_FILE_PATH):
                with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
                    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] 日志文件初始化\n")
            os.startfile(LOG_FILE_PATH)
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开日志文件:\n{e}")

    def open_input_settings(self):
        from launcher_input import open_diagnostics
        open_diagnostics(self.root)

    def get_ui_config(self):
        try: exp_val = max(1, min(99, int(self.var_exp.get())))
        except Exception: exp_val = 1
        try: rare_val = int(self.var_rare.get())
        except Exception: rare_val = 1
        try: meseta_mult_val = int(self.scale_meseta_mult.get())
        except Exception: meseta_mult_val = 1

        cfg = {
            "exp_boost": exp_val,
            "rare_mob_mult": rare_val,
            "drop_section_choice": self.var_drop_section.get(),
            "meseta_mult": meseta_mult_val,
            "event_id": EVENT_REVERSE_MAP.get(self.var_event.get(), 0),
            "name_color": self.var_name_color.get(),
            "unlock_tech_30": bool(self.var_unlock_tech.get()),
            "drop_weapon": self.sliders["drop_weapon"].get(),
            "drop_armor": self.sliders["drop_armor"].get(),
            "drop_tool": self.sliders["drop_tool"].get(),
            "drop_meseta": self.sliders["drop_meseta"].get(),
            "drop_mag": self.sliders["drop_mag"].get(),
            "dmg_mult": self.var_dmg_mult.get(),
            "def_mult": self.var_def_mult.get(),
            "hp_mult": self.var_hp_mult.get(),
        }
        client_cfg = {
            "output_api": self.var_render_api.get(),
            "window_scale": self.var_win_mode.get(),
            "display_mode": self.var_win_mode.get(),
            "screen_mode": self.var_screen_mode.get(),
            "font_choice": self.var_font.get(),
            "antialiasing": self.var_aa.get(),
            "hud_scale": self.var_hud_scale.get(),
            "ssao": bool(self.var_ssao.get()),
            "hdr": bool(self.var_hdr.get()),
            "cel": bool(self.var_cel.get()),
            "auto_login": bool(self.var_auto_login.get()),
            "auto_backup": bool(self.var_auto_backup.get()),
            "auto_kill": bool(self.var_auto_kill.get()),
        }
        return cfg, client_cfg

    def on_click_save(self):
        try:
            s_cfg, c_cfg = self.get_ui_config()
            ConfigManager.save_server_config(s_cfg)
            ConfigManager.save_client_settings(c_cfg)
            self.save_ui_state()
            self.log("配置已保存。服务端设置将在下次启动游戏时重新加载。")
            messagebox.showinfo("成功", "配置已保存。请退出游戏后通过启动器重新启动，让大厅主题和掉落倍率生效。")
        except Exception as e:
            self.log(f"保存配置失败: {e}", level="ERROR")
            messagebox.showerror("保存失败", str(e))

    def on_restore_defaults(self):
        if messagebox.askyesno("恢复默认", "确定要恢复原始 1x 倍率与默认设置吗？红盒仍固定为原滑块 20 档。"):
            ConfigManager.restore_default_config()
            self.server_cfg = ConfigManager.load_server_config()
            self.client_cfg = ConfigManager.load_client_settings()

            self.var_exp.set(self.server_cfg["exp_boost"])
            self.var_rare.set(self.server_cfg["rare_mob_mult"])
            self.var_drop_section.set(next(iter(DROP_SECTION_CHOICES)))
            self.scale_meseta_mult.set(self.server_cfg.get("meseta_mult", 1))
            self.var_event.set(EVENT_MAP.get(self.server_cfg["event_id"], "无活动 (常规大厅)"))
            self.var_name_color.set(self.server_cfg.get("name_color", "经典原版白 (#FFFFFF)"))
            self.var_unlock_tech.set(self.server_cfg.get("unlock_tech_30", False))
            self.var_dmg_mult.set("1X (原版数值)")
            self.var_def_mult.set("1X (原版数值)")
            self.var_hp_mult.set("1X (原版数值)")

            for k, s in self.sliders.items():
                s.set(self.server_cfg.get(k, 10))

            self.var_render_api.set(self.client_cfg.get("output_api", "DirectX 11 (流畅推荐)"))
            self.var_win_mode.set(self.client_cfg.get("window_scale", "2X 高清窗口 (1280×960 推荐)"))
            self.var_screen_mode.set(DEFAULT_MODE)
            self.var_font.set(self.client_cfg.get("font_choice", "宋体 (像素点阵 超清晰推荐)"))
            self.var_aa.set(self.client_cfg.get("antialiasing", "off"))
            self.var_hud_scale.set(self.client_cfg.get("hud_scale", "1.0 (原生锐利清晰，推荐)"))
            self.var_ssao.set(self.client_cfg.get("ssao", False))
            self.var_hdr.set(self.client_cfg.get("hdr", False))
            self.var_cel.set(self.client_cfg.get("cel", False))

            self.log("已恢复原始默认配置。")

    def on_toggle_server(self):
        if getattr(self, "server_starting", False):
            return
        if ServerProcessManager.is_server_running():
            if self.is_game_running or is_psobb_process_alive():
                messagebox.showwarning("请先退出游戏", "游戏运行时不能关闭后台服务，请先正常退出游戏。")
                return
            ServerProcessManager.kill_all_servers()
            self.log("本地单机服务端已全部停止。")
        else:
            try:
                s_cfg, _ = self.get_ui_config()
            except Exception as e:
                self.log(f"读取界面配置参数异常: {e}", level="ERROR")
                messagebox.showerror("参数输入错误", str(e))
                return

            try:
                ConfigManager.save_server_config(s_cfg)
            except Exception as e:
                self.log(f"保存服务端配置异常: {e}", level="ERROR")
                ans = messagebox.askyesno("配置保存提示", f"保存服务端配置异常 ({e})。\n\n是否跳过配置保存，直接启动服务端？")
                if not ans:
                    return

            redbox_rate = 20
            drop_section_id = resolve_drop_section(s_cfg["drop_section_choice"])
            from launcher_data import SECTION_IDS
            self.log(f"本次掉落徽章：{SECTION_IDS[drop_section_id] if drop_section_id is not None else '角色原有徽章'}")
            meseta_mult = s_cfg.get("meseta_mult", 1)
            self.server_starting = True
            self.btn_srv_toggle.config(state="disabled")
            threading.Thread(target=self._worker_start_server, args=(redbox_rate, meseta_mult, drop_section_id), daemon=True).start()

    def _worker_start_server(self, redbox_rate=None, meseta_mult=None, drop_section_id=None):
        try:
            ServerProcessManager.start_all_servers(self.log, redbox_rate=redbox_rate, meseta_mult=meseta_mult, drop_section_id=drop_section_id)
        except Exception as e:
            self.log(f"启动服务端出错: {e}", level="ERROR")
        finally:
            self.server_starting = False
            self.root.after(0, lambda: self.btn_srv_toggle.config(state="normal"))

    def on_click_launch(self):
        if getattr(self, "server_starting", False):
            messagebox.showinfo("服务启动中", "请等待后台服务启动完成。")
            return
        if is_psobb_process_alive() or self.is_game_running:
            messagebox.showinfo("游戏正在运行", "请先正常退出游戏，再启动以应用新的服务端设置。")
            return
        write_log("INFO", "用户点击【一键启动单机游戏】")
        try:
            s_cfg, c_cfg = self.get_ui_config()
        except Exception as e:
            err_msg = f"读取界面配置参数异常: {e}"
            self.log(err_msg, level="ERROR")
            messagebox.showerror("参数输入错误", err_msg)
            return

        try:
            ConfigManager.save_server_config(s_cfg)
            ConfigManager.save_client_settings(c_cfg)
            self.save_ui_state()
        except Exception as e:
            write_log("ERROR", f"配置写入异常: {e}", exc=True)
            self.log("配置未完整保存，已停止启动，请解决写入问题后重试。", level="ERROR")
            messagebox.showerror("配置保存失败", f"配置未完整保存，已停止启动。\n{e}")
            return

        auto_backup = bool(self.var_auto_backup.get())
        preset = WINDOW_SCALE_PRESETS.get(c_cfg['window_scale'], next(iter(WINDOW_SCALE_PRESETS.values())))
        self._active_display_profile = display_profile(c_cfg['screen_mode'],
                                                       (preset['w'], preset['h']), desktop_size())
        auto_login = bool(self.var_auto_login.get())
        auto_kill = bool(self.var_auto_kill.get())
        redbox_rate = 20
        drop_section_id = resolve_drop_section(s_cfg["drop_section_choice"])
        from launcher_data import SECTION_IDS
        self.log(f"本次掉落徽章：{SECTION_IDS[drop_section_id] if drop_section_id is not None else '角色原有徽章'}")
        meseta_mult = s_cfg.get("meseta_mult", 1)

        if auto_backup:
            _, b_msg = ConfigManager.backup_account(tag="prelaunch")
            write_log("INFO", f"[Backup-Prelaunch] {b_msg}")

        self.btn_launch.config(state="disabled", text="正在拉起游戏中...")
        threading.Thread(target=self._worker_launch_all, args=(auto_login, auto_backup, auto_kill, redbox_rate, meseta_mult, drop_section_id), daemon=True).start()

    def _worker_launch_all(self, auto_login, auto_backup, auto_kill, redbox_rate=None, meseta_mult=None, drop_section_id=None):
        try:
            # INI/drop/level tables are loaded once at server boot, never hot-reloaded.
            if ServerProcessManager.is_server_running():
                self.log("重新启动本地服务，应用大厅主题与掉落设置...")
                ServerProcessManager.kill_all_servers()
                if ServerProcessManager.is_server_running():
                    raise RuntimeError("无法关闭非本启动器管理的服务，请手动关闭后重试。")
            if not ServerProcessManager.is_server_running():
                self.log("正在启动本地单机服务 (后台守护运行)...")
                if not ServerProcessManager.start_all_servers(self.log, redbox_rate=redbox_rate, meseta_mult=meseta_mult, drop_section_id=drop_section_id):
                    self.log("启动本地单机服务失败，请点击【运行日志】查看详情！", level="ERROR")
                    self.root.after(0, lambda: self.btn_launch.config(state="normal", text="启动游戏   →"))
                    return

            # 2. 检查游戏客户端文件
            if not os.path.exists(PSOBB_EXE):
                err = f"未找到游戏客户端可执行文件:\n{PSOBB_EXE}"
                self.log(err, level="ERROR")
                self.root.after(0, lambda: messagebox.showerror("游戏文件缺失", err))
                self.root.after(0, lambda: self.btn_launch.config(state="normal", text="启动游戏   →"))
                return

            # 3. 拉起客户端
            api_choice = self.var_render_api.get()
            self.log(f"正在唤起游戏客户端 (渲染后端: {api_choice})...")
            write_log("INFO", f"唤起游戏进程: {PSOBB_EXE}, 渲染模式: {api_choice}, 工作目录: {CLIENT_DIR}")
            os.environ["__COMPAT_LAYER"] = "RunAsInvoker"

            client_launched = False
            try:
                ret = ctypes.windll.shell32.ShellExecuteW(None, "open", PSOBB_EXE, "", CLIENT_DIR, 1)
                write_log("INFO", f"ShellExecuteW 返回代码: {ret}")
                if ret > 32:
                    client_launched = True
                else:
                    err_desc = {
                        2: "文件未找到 (ERROR_FILE_NOT_FOUND)",
                        3: "路径未找到 (ERROR_PATH_NOT_FOUND)",
                        5: "系统拒绝访问 (ERROR_ACCESS_DENIED)",
                        740: "需要管理员权限提升运行 (ERROR_ELEVATION_REQUIRED)",
                    }.get(ret, f"错误码 {ret}")
                    write_log("WARN", f"ShellExecuteW 启动返回异常: {err_desc}，尝试使用 Popen 后备拉起...")
                    try:
                        p_client = subprocess.Popen([PSOBB_EXE], cwd=CLIENT_DIR)
                        GLOBAL_JOB.assign_process(p_client._handle)
                        write_log("INFO", f"Popen 后备拉起客户端 PID: {p_client.pid}")
                        client_launched = True
                    except Exception as popen_e:
                        write_log("ERROR", f"Popen 后备拉起客户端亦失败: {popen_e}", exc=True)
                        raise RuntimeError(f"客户端启动失败 ({err_desc}; 后备错误: {popen_e})")
            except Exception as e:
                err = f"唤起客户端出错: {e}"
                self.log(err, level="ERROR")
                self.root.after(0, lambda: self.btn_launch.config(state="normal", text="启动游戏   →"))
                return

            # 4. 游戏窗口样式自适应与自动登录
            self.log("等待游戏窗口就绪并应用 4:3 显示模式...")
            threading.Thread(target=self._setup_window_and_login_daemon, args=(auto_login,), daemon=True).start()

            self.root.after(2000, lambda: self.btn_launch.config(state="normal", text="启动游戏   →"))
            self._start_game_watcher(auto_backup, auto_kill)
        except Exception as e:
            self.log(f"启动流程异常: {e}", level="ERROR")
            self.root.after(0, lambda: self.btn_launch.config(state="normal", text="启动游戏   →"))

    def _setup_window_and_login_daemon(self, auto_login):
        target_hwnd = 0
        write_log("INFO", "开始捕获游戏窗口 (PSO_BB)...")
        for i in range(30):
            time.sleep(0.5)
            hwnd = user32.FindWindowW("PSO_BB", None)
            if not hwnd:
                hwnd = user32.FindWindowW("PHANTASY STAR ONLINE Blue Burst", None)
            if not hwnd:
                hwnd = user32.FindWindowW(None, "Phantasy Star Online Blue Burst")
            if not hwnd:
                hwnd = user32.FindWindowW(None, "PHANTASY STAR ONLINE Blue Burst")
            if hwnd:
                target_hwnd = hwnd
                write_log("INFO", f"在第 {i*0.5:.1f} 秒成功捕获游戏窗口 hwnd: {hwnd}")
                break

        if not target_hwnd:
            self.log("未能在超时内捕获游戏窗口，请进入游戏后手动操作。", level="WARN")
            return

        from launcher_monitor import ExitProbe
        self._client_exit_probe = ExitProbe(target_hwnd)

        # Only ordinary windows receive a frame; presentation belongs to dgVoodoo.
        try:
            profile = getattr(self, '_active_display_profile', None)
            if profile:
                position_window(target_hwnd, profile)
                write_log('INFO', f"显示已就绪: {profile['mode']}, 4:3 {profile['render']}")
        except Exception as e:
            write_log("WARN", f"应用游戏窗口尺寸异常: {e}")

        # 2. 自动登录按键注入
        if not auto_login:
            self.log("游戏窗口已就绪，可直接回车登录。")
            return

        time.sleep(1.5)
        activated = False
        for _ in range(4):
            if force_activate_window(target_hwnd):
                activated = True
                break
            time.sleep(0.5)

        if user32.GetForegroundWindow() == target_hwnd or activated:
            time.sleep(1.0)
            for i in range(5):
                send_enter_keystroke(target_hwnd)
                time.sleep(1.2)
            self.log("已成功锁定前台并自动完成登录！")
            write_log("INFO", "自动回车登录按键注入成功完成")
        else:
            self.log("未能获取游戏前台焦点，请点击游戏窗口并手动按 Enter 登录。", level="WARN")

    def _start_game_watcher(self, auto_backup, auto_kill):
        def watch_loop():
            write_log("INFO", "游戏进程守护线程已激活，正在等待 PsoBB.exe 出现...")
            # 阶段 1：等待进程出现（最多等待 25 秒，每 0.5 秒检测一次）
            proc_appeared = False
            for _ in range(50):
                time.sleep(0.5)
                if is_psobb_process_alive():
                    proc_appeared = True
                    break

            if not proc_appeared:
                write_log("WARN", "超时 25 秒仍未检测到 PsoBB.exe 正在运行，守护线程安全退出 (绝不误杀服务端)")
                self.is_game_running = False
                return

            write_log("INFO", "已确认检测到 PsoBB.exe 处于运行状态，开始持续监控游戏生命周期")
            self.is_game_running = True
            try:
                self.root.after(0, self.root.iconify)
            except Exception:
                pass

            # 阶段 2：等待进程退出（双重判定，防止瞬时 tasklist 漏检）
            consecutive_misses = 0
            while True:
                time.sleep(2.0)
                if not is_psobb_process_alive():
                    consecutive_misses += 1
                    if consecutive_misses >= 2:
                        write_log("INFO", "已连续检测确认 PsoBB.exe 退出")
                        break
                else:
                    consecutive_misses = 0

            # 阶段 3：安全收尾
            probe = getattr(self, '_client_exit_probe', None)
            if probe:
                code = probe.finish()
                self._client_exit_probe = None
                write_log('INFO' if code == 0 else 'WARN',
                          f'客户端退出码: {"未知" if code is None else f"0x{code:08X}"}；0 可能是正常退出或客户端主动结束，非零需结合 Client/log 排查。')
            time.sleep(1.0)
            try:
                if auto_backup:
                    _, b_msg = ConfigManager.backup_account(tag="exit")
                    write_log("INFO", f"[Backup-Exit] {b_msg}")
            except Exception as b_e:
                write_log("WARN", f"退出存档备份异常: {b_e}")

            try:
                if auto_kill:
                    self.log("检测到游戏已退出，正在安全同步数据并关闭后台服务端...")
                    ServerProcessManager.kill_all_servers()
                    self.log("单机环境已彻底清理，存档已校验并安全分层备份。")
            except Exception as k_e:
                write_log("WARN", f"关闭后台服务异常: {k_e}")

            self.is_game_running = False
            try:
                self.root.after(0, lambda: (self.root.deiconify(), self.root.lift()))
            except Exception:
                pass

        threading.Thread(target=watch_loop, daemon=True).start()

    def start_status_daemon(self):
        def poll():
            running = ServerProcessManager.is_server_running()
            if running:
                self.status_pill.config(text="●  本地服务已就绪", fg="#8addb2", bg="#183336")
                self.btn_srv_toggle.config(text="停止后台服务", bg="#382a35")
            else:
                self.status_pill.config(text="○  本地服务未启动", fg=self.c_subtext, bg="#1a2a3e")
                self.btn_srv_toggle.config(text="启动后台服务", bg="#1a2a3e")
            self.root.after(2000, poll)
        poll()

    def show_gm_help(self):
        w = tk.Toplevel(self.root)
        w.title("单机 GM 常用指令速查手册")
        w.geometry("560x480")
        w.configure(bg="#101a2e")
        txt = tk.Text(w, font=("Consolas", 10), bg="#0b1322", fg="#00d2ff", wrap="word", padx=15, pady=15)
        txt.insert("1.0", GM_COMMANDS_HELP)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)

    def open_tethman(self):
        write_log("INFO", f"尝试打开帐号管理工具: {TETHMAN_EXE}")
        if os.path.exists(TETHMAN_EXE):
            try:
                subprocess.Popen([TETHMAN_EXE], cwd=os.path.dirname(TETHMAN_EXE))
            except Exception as e:
                err = f"启动帐号管理工具失败: {e}"
                write_log("ERROR", err, exc=True)
                messagebox.showerror("启动失败", err)
        else:
            err = f"未找到管理工具可执行文件:\n{TETHMAN_EXE}"
            write_log("ERROR", err)
            messagebox.showerror("未找到文件", err)

    def open_item_maker(self):
        write_log("INFO", f"尝试打开造物工具: {ITEM_MAKER_EXE}")
        if os.path.exists(ITEM_MAKER_EXE):
            try:
                subprocess.Popen([ITEM_MAKER_EXE], cwd=os.path.dirname(ITEM_MAKER_EXE))
            except Exception as e:
                err = f"启动造物工具失败: {e}"
                write_log("ERROR", err, exc=True)
                messagebox.showerror("启动失败", err)
        else:
            err = f"未找到造物工具可执行文件:\n{ITEM_MAKER_EXE}"
            write_log("ERROR", err)
            messagebox.showerror("未找到文件", err)


def main():
    # 保证全局单实例运行，防止多次启动产生多个启动器窗口
    MUTEX_NAME = "Global\\PSOBB_OneClick_Launcher_SingleInstance_Mutex"
    ERROR_ALREADY_EXISTS = 183
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    h_mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        # 已有实例在运行，尝试将已有实例的主窗口唤起至最前台
        hwnd = user32.FindWindowW(None, "梦幻之星网络版 (PSOBB) · 哔哩哔哩：metalmouse")
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
        sys.exit(0)

    def _install_exception_hooks(root):
        def _hook(exc_type, exc_val, exc_tb):
            err_text = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
            write_log("ERROR", f"全局未捕获异常:\n{err_text}")
        sys.excepthook = _hook
        threading.excepthook = lambda a: _hook(a.exc_type, a.exc_value, a.exc_traceback)
        root.report_callback_exception = _hook

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    root = tk.Tk()
    _install_exception_hooks(root)
    app = PSOBBLauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
