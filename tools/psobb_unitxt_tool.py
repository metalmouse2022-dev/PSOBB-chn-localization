#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PSOBB (Phantasy Star Online Blue Burst) 客户端汉化文本提取与打包工具
支持:
  1. 解压 SEGA PRS 并解析 unitxt 数据表，导出为 UTF-8 编码的 TXT 文件
  2. 读取编辑后的 TXT 文件，重构 unitxt 二进制数据并重新压缩为 PRS 格式
"""

import os
import sys
import struct
import re

# ==============================================================================
# SEGA PRS 压缩与解压缩算法实现 (基于 SEGA LZ77 变种规范)
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
                # 长距离回溯 (Long backreference)
                low = cr.get_u8()
                high = cr.get_u8()
                a = low | (high << 8)
                raw_offset = a >> 3
                if raw_offset == 0:
                    # 停止操作码 (Stop opcode)
                    break
                offset = raw_offset - 0x2000
                size_bits = a & 7
                count = (size_bits + 2) if size_bits != 0 else (cr.get_u8() + 1)
            else:
                # 短距离回溯 (Short backreference)
                bit1 = cr.read_bit()
                bit2 = cr.read_bit()
                count = ((bit1 << 1) | bit2) + 2
                offset = cr.get_u8() - 0x100

            read_pos = len(out) + offset
            if read_pos < 0 or read_pos >= len(out):
                raise ValueError(f"无效的回溯偏移量 {offset}，当前缓冲区长度 {len(out)}")
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
        # 写入停止标志: 控制位 0, 1，数据位 0x00, 0x00
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

        if pos + 2 < length:
            triplet = (data[pos], data[pos+1], data[pos+2])
            match_pos = head.get(triplet, -1)
            chain_len = 0
            while match_pos != -1 and chain_len < 32:
                off = match_pos - pos
                if off <= -0x1FFF:  # 有效偏移范围为 -1 到 -8191 (0x1FFF)
                    break
                m_len = 0
                max_check = min(256, length - pos)
                while m_len < max_check and data[pos + m_len] == data[match_pos + m_len]:
                    m_len += 1
                if m_len > best_len:
                    best_len = m_len
                    best_off = off
                    if best_len >= 256:
                        break
                match_pos = prev[match_pos]
                chain_len += 1

        if best_len < 2 or (best_len == 2 and best_off < -256):
            c.put_literal(data[pos])
            if pos + 2 < length:
                triplet = (data[pos], data[pos+1], data[pos+2])
                prev[pos] = head.get(triplet, -1)
                head[triplet] = pos
            pos += 1
        else:
            if best_len <= 5 and best_off >= -256:
                c.put_short_copy(best_off, best_len)
            else:
                c.put_long_copy(best_off, best_len)

            for k in range(best_len):
                if pos + k + 2 < length:
                    triplet = (data[pos+k], data[pos+k+1], data[pos+k+2])
                    prev[pos+k] = head.get(triplet, -1)
                    head[triplet] = pos + k
            pos += best_len

    return c.finish()


# ==============================================================================
# PSOBB unitxt 二进制结构解析与重构
# ==============================================================================

def parse_unitxt_prs(prs_data: bytes):
    """解压 PRS 并解析 unitxt 表结构"""
    bin_data = prs_decompress(prs_data)
    num_tables = struct.unpack_from("<I", bin_data, 0)[0]
    counts = struct.unpack_from(f"<{num_tables}I", bin_data, 4)
    total_strings = sum(counts)
    header_size = 4 + num_tables * 4
    ptrs = struct.unpack_from(f"<{total_strings}I", bin_data, header_size)

    idx = 0
    tables = []
    for count in counts:
        table = []
        for _ in range(count):
            p = ptrs[idx]
            end = p
            while end + 1 < len(bin_data) and not (bin_data[end] == 0 and bin_data[end+1] == 0):
                end += 2
            s = bin_data[p:end].decode("utf-16le", errors="replace")
            table.append(s)
            idx += 1
        tables.append(table)
    return tables


def build_unitxt_bin(tables) -> bytes:
    """由字符串表列表重构 unitxt 二进制数据块"""
    num_tables = len(tables)
    counts = [len(t) for t in tables]
    total_strings = sum(counts)

    header_size = 4 + num_tables * 4
    pointer_table_size = total_strings * 4
    strings_start_offset = header_size + pointer_table_size

    string_offsets = []
    string_pool = bytearray()

    for table in tables:
        for s in table:
            offset = strings_start_offset + len(string_pool)
            string_offsets.append(offset)
            encoded = s.encode("utf-16le") + b"\x00\x00"
            string_pool.extend(encoded)

    bin_data = bytearray()
    bin_data.extend(struct.pack("<I", num_tables))
    bin_data.extend(struct.pack(f"<{num_tables}I", *counts))
    bin_data.extend(struct.pack(f"<{total_strings}I", *string_offsets))
    bin_data.extend(string_pool)
    return bytes(bin_data)


# 表分类注释说明
UNITXT_J_DESCRIPTIONS = {
    0: "键盘与控制器按键设置 (Keyboard & Gamepad Controls)",
    1: "道具与武器装备名称 (Item & Weapon Names - 1081 条)",
    2: "未鉴定武器名与道具类别 (Unappraised Weapons & Item Categories)",
    3: "道具与武器详细说明 (Item & Weapon Descriptions - 993 条)",
    4: "敌人与Boss名称 (Enemy & Boss Names)",
    5: "魔法技能名称 (Technique Names)",
    6: "魔法简要说明 (Technique Short Descriptions)",
    7: "魔法详细说明 (Technique Long Descriptions)",
    8: "职业名称 (Classes / Character Types)",
    9: "玛古光子爆发 (Photon Blasts)",
    10: "区域与地图名称 (Areas & Map Locations)",
    11: "菜单与动作帮助说明 (Menu & Action Help Text)",
    12: "道具/状态/金钱相关界面 (Inventory, Bank, Status)",
    13: "网络连接与登录提示 (Network & Login Status)",
    14: "游戏难度选择 (Difficulty Levels)",
    15: "母舰/冒险大厅/队伍选择 (Ship & Lobby Selection)",
    16: "语言与系统设置 (Language & Audio Settings)",
    17: "对战战绩统计 (Battle Mode Statistics)",
    18: "职业特点简述1 (Class Details Part 1)",
    19: "职业特点简述2 (Class Details Part 2)",
    20: "角色与章节选择 (Character & Chapter Select)",
    21: "游戏篇章 (Episode 1 / Episode 2)",
    24: "PSO账号与密码输入提示 (Account & Password Prompt)",
    25: "难度与章节选择 (Difficulty & Episode Select)",
    28: "协议同意选项 (Agreement: Agree / Disagree)",
    31: "角色更衣室/选择 (Dressing Room / Character Select)",
    34: "游戏返回/退出菜单 (Return to Menu / Quit)",
    39: "角色创建选项 (Character Creation)",
    40: "账号信息确认 (Account Info Confirmation)",
    41: "常用确定/取消菜单 (Common Confirmation Menu)",
    44: "挑战模式通关与奖励评价 (Challenge Mode Rewards)",
    45: "名片/声音设置 (Guild Cards & Sound FX)",
    47: "在线/离线游戏模式 (Online / Offline Mode)",
    57: "创建角色 (New Character)",
    58: "角色变更与保存提示 (Character Change & Save Prompts)",
    66: "聊天快捷短语 (Quick Chat Phrases: Greetings, Dialogue, Emotion)",
    70: "服务器大厅与满员提示 (Lobby & Server Notifications)",
    71: "PSOBB网络连接同步状态 (PSOBB Server Connection Status)",
    72: "Section ID 玛古进化属性颜色 (Viridia, Greenill, Skyly...)",
}

UNITXT_SHOP_J_DESCRIPTIONS = {
    0: "商店基础菜单与交易交互 (Shop Basic Menu & Prompts)",
    1: "猎人公会柜台接待台词 (Hunter's Guild Counter)",
    2: "挑战模式专用柜台接待台词 (Challenge Mode Counter)",
    3: "对战模式专用柜台接待台词 (Battle Mode Counter)",
    4: "鉴定行鉴定师台词 (Tekker Appraisal Dialog 1)",
    5: "鉴定行鉴定师台词 (Tekker Appraisal Dialog 2)",
    6: "鉴定行鉴定师台词 (Tekker Appraisal Dialog 3)",
    7: "鉴定行鉴定师台词 (Tekker Appraisal Dialog 4)",
    8: "鉴定行鉴定师台词 (Tekker Appraisal Dialog 5)",
    9: "鉴定行鉴定师台词 (Tekker Appraisal Dialog 6)",
    10: "鉴定行鉴定师台词 (Tekker Appraisal Dialog 7)",
    11: "鉴定行鉴定师台词 (Tekker Appraisal Dialog 8)",
    12: "鉴定行鉴定师台词 (Tekker Appraisal Dialog 9)",
    13: "鉴定行鉴定师台词 (Tekker Appraisal Dialog 10)",
    14: "任务标题、委托人及任务简报 (Episode 1 & 2 Quests)",
    15: "挑战模式关卡及目标 (Challenge Mode Stages)",
    16: "对战模式规则说明 (Battle Mode Rules)",
    17: "总督府受理处柜台台词 (Principal's Office Counter - Ep1)",
    18: "实验室受理处柜台台词 (Lab Counter - Ep2)",
}


def export_prs_to_txt(prs_path: str, txt_path: str):
    """将 .prs 文件导出为规范标注的 .txt 文件"""
    with open(prs_path, "rb") as f:
        prs_data = f.read()

    tables = parse_unitxt_prs(prs_data)
    is_shop = "shop" in os.path.basename(prs_path).lower()
    desc_map = UNITXT_SHOP_J_DESCRIPTIONS if is_shop else UNITXT_J_DESCRIPTIONS

    with open(txt_path, "w", encoding="utf-8-sig") as out:
        out.write("# ================================================================\n")
        out.write("# PSOBB 客户端汉化文本导出文件\n")
        out.write(f"# 源文件: {os.path.basename(prs_path)}\n")
        out.write(f"# 分类表总数: {len(tables)}\n")
        out.write(f"# 文本总条数: {sum(len(t) for t in tables)}\n")
        out.write("# 编码格式: UTF-8 with BOM\n")
        out.write("# 格式说明:\n")
        out.write("#   每个词条由 [表编号:条目序号] 开始，以 [/entry] 结束。\n")
        out.write("#   词条内部支持多行文本与换行。\n")
        out.write("#   以 # 开头的行为注释，修改后可使用本工具直接打包回 .prs 格式。\n")
        out.write("# ================================================================\n\n")

        for t_idx, table in enumerate(tables):
            table_desc = desc_map.get(t_idx, "未分类/系统保留")
            out.write("# ----------------------------------------------------------------\n")
            out.write(f"# 表 {t_idx:02d} [{table_desc}] (共 {len(table)} 条)\n")
            out.write("# ----------------------------------------------------------------\n\n")
            for s_idx, s in enumerate(table):
                out.write(f"[{t_idx:02d}:{s_idx:04d}]\n{s}\n[/entry]\n\n")

    print(f"成功导出: {prs_path} -> {txt_path} (共 {len(tables)} 表，{sum(len(t) for t in tables)} 条文本)")


def import_txt_to_prs(txt_path: str, prs_path: str):
    """读取规范标注的 .txt 文件并重新打包为 .prs 压缩文件"""
    with open(txt_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    # 匹配 [TT:SSSS]\n ... \n[/entry]
    pattern = re.compile(r"^\[(\d+):(\d+)\]\r?\n(.*?)\r?\n\[/entry\]", re.MULTILINE | re.DOTALL)
    matches = list(pattern.finditer(content))

    if not matches:
        raise ValueError(f"在 {txt_path} 中未找到任何形如 [00:0000]...[/entry] 的条目标记！")

    table_dict = {}
    for m in matches:
        t_idx = int(m.group(1))
        s_idx = int(m.group(2))
        s_text = m.group(3)

        if t_idx not in table_dict:
            table_dict[t_idx] = {}
        table_dict[t_idx][s_idx] = s_text

    num_tables = max(table_dict.keys()) + 1
    tables = []
    for t_idx in range(num_tables):
        t_entries = table_dict.get(t_idx, {})
        if t_entries:
            max_s_idx = max(t_entries.keys())
            table = [t_entries.get(s_idx, "") for s_idx in range(max_s_idx + 1)]
        else:
            table = []
        tables.append(table)

    bin_data = build_unitxt_bin(tables)
    prs_data = prs_compress(bin_data)

    with open(prs_path, "wb") as f:
        f.write(prs_data)

    print(f"成功打包: {txt_path} -> {prs_path} (解压大小: {len(bin_data)} 字节, 压缩后大小: {len(prs_data)} 字节)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # 默认模式：自动查找并导出当前目录下的 SCmedium 汉化文件
        base_dir = os.path.dirname(os.path.abspath(__file__))
        sc_dir = os.path.join(base_dir, "SCmedium")
        if os.path.isdir(sc_dir):
            for filename in ["unitxt_j.prs", "unitxt_shop_j.prs"]:
                src = os.path.join(sc_dir, filename)
                dst = os.path.join(base_dir, filename.replace(".prs", ".txt"))
                if os.path.isfile(src):
                    export_prs_to_txt(src, dst)
        else:
            print("用法:")
            print("  导出: python psobb_unitxt_tool.py export <输入.prs> [输出.txt]")
            print("  导入: python psobb_unitxt_tool.py import <输入.txt> [输出.prs]")
    else:
        cmd = sys.argv[1].lower()
        if cmd == "export":
            src = sys.argv[2]
            dst = sys.argv[3] if len(sys.argv) > 3 else src.replace(".prs", ".txt")
            export_prs_to_txt(src, dst)
        elif cmd == "import":
            src = sys.argv[2]
            dst = sys.argv[3] if len(sys.argv) > 3 else src.replace(".txt", ".prs")
            import_txt_to_prs(src, dst)
        else:
            print(f"未知命令: {cmd}")
