#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PSOBB (Phantasy Star Online Blue Burst) 任务剧情与对白文本提取/回填工具 (v2.0 工业级防崩与校验版)

核心设计准则:
  1. 【原地定长 NOP 填充法 (In-Place Exact NOP Padding)】:
     在中文末尾写入 0x00 0x00 终止符，剩余多余字节以 0x00 (PASM 虚拟机 NOP 空指令) 填充至与原英文字节数 100% 相同。
     确保整段字节码总长与所有函数指针、Label 跳转偏移 1 字节不差，杜绝任何错位闪退！
  2. 【字符预算显式化 (Explicit max_chars Budget)】:
     导出 JSON 时为任务名、简报、详述及每句对话均显式提供 max_chars 字段，让 AI / 译者在翻译时明确字数预算。
  3. 【超长硬拦截与格式校验】:
     回填时严禁静默截断，若译文超出预算直接报错拦截；
     内置控制码 (\\tC颜色码、<hero name>等) 完整度校验与单行字数 (>18汉字) 溢出预警。
  4. 【纯 Python 自包含 PRS 引擎】:
     内置 SEGA PRS LZ77 算法编解码，零第三方外部库依赖。
"""

import os
import sys
import struct
import json
import re
import argparse

# ==============================================================================
# 自包含 SEGA PRS 压缩与解压缩引擎 (LZ77 变种)
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
        # 写入停止标志
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


# ==============================================================================
# QST 封包解析与分块打包
# ==============================================================================
class QSTArchive:
    @staticmethod
    def unpack_qst(data: bytes):
        """
        解包 Sega PSOBB QST 容器文件
        返回: (header_bytes, files_dict)
        """
        match = re.search(b'[\x1c\x20]\x04\x13\x00', data)
        chunk_start = match.start() if match else -1
        if chunk_start == -1:
            raise ValueError("未在 QST 文件中找到有效的分块标志 0x1300")

        header_bytes = data[:chunk_start]
        files_data = {}
        offset = chunk_start
        while offset + 1056 <= len(data):
            fname = data[offset+8:offset+24].split(b"\x00")[0].decode("ascii", errors="ignore")
            payload_size = struct.unpack_from("<I", data, offset + 0x418)[0]
            payload = data[offset+0x18 : offset+0x18+payload_size]
            if fname not in files_data:
                files_data[fname] = []
            files_data[fname].append(payload)
            offset += 1056

        combined_files = {fname: b"".join(chunks) for fname, chunks in files_data.items()}
        return header_bytes, combined_files

    @staticmethod
    def pack_qst(header_bytes: bytes, files_dict: dict) -> bytes:
        """
        将多个文件重新打包为标准 1056 字节的 QST 封包
        """
        file_chunks = {}
        max_chunks = 0
        for fname, file_bytes in files_dict.items():
            chunks = []
            for i in range(0, len(file_bytes), 1024):
                chunks.append(file_bytes[i:i+1024])
            file_chunks[fname] = chunks
            if len(chunks) > max_chunks:
                max_chunks = len(chunks)

        new_header = bytearray(header_bytes)
        desc_offset = 0
        while desc_offset + 88 <= len(new_header):
            fname = new_header[desc_offset+0x2c:desc_offset+0x3c].split(b"\x00")[0].decode("ascii", errors="ignore")
            if fname in files_dict:
                struct.pack_into("<I", new_header, desc_offset + 0x3C, len(files_dict[fname]))
            desc_offset += 88

        out_qst = bytearray(new_header)
        for chunk_idx in range(max_chunks):
            for fname in sorted(files_dict.keys()):
                chunks = file_chunks[fname]
                if chunk_idx < len(chunks):
                    chunk_payload = chunks[chunk_idx]
                    payload_len = len(chunk_payload)

                    block = bytearray(1056)
                    block[0:4] = b"\x1c\x04\x13\x00"
                    struct.pack_into("<I", block, 4, chunk_idx)
                    fname_bytes = fname.encode("ascii")[:15]
                    block[8:8+len(fname_bytes)] = fname_bytes
                    block[0x18:0x18+payload_len] = chunk_payload
                    struct.pack_into("<I", block, 0x418, payload_len)
                    out_qst.extend(block)

        return bytes(out_qst)


# ==============================================================================
# 任务剧情字节码文本提取、回填与校验
# ==============================================================================
class QuestBytecodeTool:
    # 头部固定缓冲区界限（严格核对真实 .bin 头）
    TITLE_START = 0x18
    TITLE_END = 0x58      # 64 字节缓冲区 (最多 31 字符 + 0x00 0x00)
    SHORT_START = 0x58
    SHORT_END = 0x158     # 256 字节缓冲区 (最多 127 字符 + 0x00 0x00)
    FULL_START = 0x158
    FULL_END = 0x39C      # 580 字节缓冲区 (最多 289 字符 + 0x00 0x00)

    @classmethod
    def extract_texts(cls, bin_decompressed: bytes):
        """
        从解压后的 .bin 字节码中全量提取剧情与对白文本 (UTF-16LE)
        """
        title = bin_decompressed[cls.TITLE_START:cls.TITLE_END].decode("utf-16le", errors="ignore").split("\x00")[0].strip()
        short_desc = bin_decompressed[cls.SHORT_START:cls.SHORT_END].decode("utf-16le", errors="ignore").split("\x00")[0].strip()
        full_desc = bin_decompressed[cls.FULL_START:cls.FULL_END].decode("utf-16le", errors="ignore").split("\x00")[0].strip()

        dialogues = []
        # 扫描 0x39C 以后的所有内联 UTF-16LE 字符串 (以 0x00 0x00 截断)
        pattern = re.compile(b'(?:[\x20-\x7e\x0a\x0d\x09]\x00){2,}\x00\x00')

        for m in pattern.finditer(bin_decompressed):
            start = m.start()
            if start < cls.FULL_END:
                continue

            raw = m.group(0)
            text = raw.decode("utf-16le", errors="ignore").split("\x00")[0].strip()
            if not text:
                continue

            # 过滤无效纯符号代码
            if not any(c.isalnum() for c in text):
                continue

            raw_len = len(raw)
            max_chars = (raw_len - 2) // 2

            dialogues.append({
                "id": len(dialogues),
                "offset": f"0x{start:04X}",
                "raw_offset": start,
                "raw_len": raw_len,
                "max_chars": max_chars,
                "en": text,
                "cn": ""
            })

        return {
            "title": title,
            "title_max_chars": (cls.TITLE_END - cls.TITLE_START - 2) // 2,
            "title_cn": "",
            "short_desc": short_desc,
            "short_desc_max_chars": (cls.SHORT_END - cls.SHORT_START - 2) // 2,
            "short_desc_cn": "",
            "full_desc": full_desc,
            "full_desc_max_chars": (cls.FULL_END - cls.FULL_START - 2) // 2,
            "full_desc_cn": "",
            "dialogues": dialogues
        }

    @classmethod
    def validate_translation(cls, qst_name: str, item_id: str, en_text: str, cn_text: str, max_chars: int):
        """校验译文长度、控制标记与行宽"""
        if not cn_text:
            return True, []

        warnings = []
        # 1. 严格长度硬拦截 (必须留 2 字节给 0x00 0x00 终止符)
        cn_encoded = cn_text.encode("utf-16le")
        max_bytes = max_chars * 2
        if len(cn_encoded) > max_bytes:
            raise ValueError(
                f"[{qst_name} - {item_id}] 译文长度超出硬上限！\n"
                f"  当前字节数: {len(cn_encoded)} 字节 ({len(cn_text)} 字符)\n"
                f"  最大允许值: {max_bytes} 字节 ({max_chars} 字符)\n"
                f"  英文原句: {en_text}\n"
                f"  超长中文: {cn_text}"
            )

        # 2. 控制代码与占位符匹配校验 (\\tC颜色控制符, <hero name>, <name>, %s)
        control_patterns = [r'\\tC[0-9]', r'<[^>]+>', r'%[0-9]*[sdxf]']
        for pat in control_patterns:
            en_tags = re.findall(pat, en_text, re.IGNORECASE)
            cn_tags = re.findall(pat, cn_text, re.IGNORECASE)
            if set(en_tags) != set(cn_tags):
                warnings.append(f"[{qst_name} - {item_id}] 控制标签不匹配: 英文包含 {en_tags}，中文包含 {cn_tags}")

        # 3. 单行字符宽度校验 (PSOBB 对话框单行若超 18 个全角汉字无 \\n 则会冲出右边界)
        lines = cn_text.split("\n")
        for idx, line in enumerate(lines):
            # 计算全角/半角等效宽度
            w = sum(2 if ord(c) > 127 else 1 for c in line)
            if w > 36:  # 超过 18 个汉字宽
                warnings.append(f"[{qst_name} - {item_id}] 第 {idx+1} 行文本过宽 ({w//2} 汉字)，可能冲出游戏边框，建议加 \\n 换行: {line}")

        return True, warnings

    @classmethod
    def reinject_texts(cls, bin_decompressed: bytes, quest_translation: dict, qst_name: str = "") -> bytes:
        """
        使用【原地定长 NOP 填充法】回填译文：
        中文 UTF-16LE + 0x00 0x00 终止符 + 0x00 (nop) 填充补齐至 raw_len。
        """
        buf = bytearray(bin_decompressed)
        all_warnings = []

        # 1. 替换任务标题 (0x18 ~ 0x58, 64 字节)
        title_cn = quest_translation.get("title_cn", "").strip()
        if title_cn:
            max_c = (cls.TITLE_END - cls.TITLE_START - 2) // 2
            _, warns = cls.validate_translation(qst_name, "Title", quest_translation.get("title", ""), title_cn, max_c)
            all_warnings.extend(warns)
            buf[cls.TITLE_START:cls.TITLE_END] = b"\x00" * (cls.TITLE_END - cls.TITLE_START)
            t_bytes = title_cn.encode("utf-16le") + b"\x00\x00"
            buf[cls.TITLE_START:cls.TITLE_START+len(t_bytes)] = t_bytes

        # 2. 替换简要描述 (0x58 ~ 0x158, 256 字节)
        short_cn = quest_translation.get("short_desc_cn", "").strip()
        if short_cn:
            max_c = (cls.SHORT_END - cls.SHORT_START - 2) // 2
            _, warns = cls.validate_translation(qst_name, "ShortDesc", quest_translation.get("short_desc", ""), short_cn, max_c)
            all_warnings.extend(warns)
            buf[cls.SHORT_START:cls.SHORT_END] = b"\x00" * (cls.SHORT_END - cls.SHORT_START)
            s_bytes = short_cn.encode("utf-16le") + b"\x00\x00"
            buf[cls.SHORT_START:cls.SHORT_START+len(s_bytes)] = s_bytes

        # 3. 替换详述 (0x158 ~ 0x39C, 580 字节)
        full_cn = quest_translation.get("full_desc_cn", "").strip()
        if full_cn:
            max_c = (cls.FULL_END - cls.FULL_START - 2) // 2
            _, warns = cls.validate_translation(qst_name, "FullDesc", quest_translation.get("full_desc", ""), full_cn, max_c)
            all_warnings.extend(warns)
            buf[cls.FULL_START:cls.FULL_END] = b"\x00" * (cls.FULL_END - cls.FULL_START)
            f_bytes = full_cn.encode("utf-16le") + b"\x00\x00"
            buf[cls.FULL_START:cls.FULL_START+len(f_bytes)] = f_bytes

        # 4. 原地定长回填内联剧情文本 (中文 + 0x00 0x00 终止符 + 0x00 nop 填充)
        for item in quest_translation.get("dialogues", []):
            cn_text = item.get("cn", "").strip()
            if not cn_text:
                continue

            raw_off = item["raw_offset"]
            raw_len = item["raw_len"]
            max_chars = item.get("max_chars", (raw_len - 2) // 2)

            _, warns = cls.validate_translation(qst_name, f"Dlg_{item['id']}", item.get("en", ""), cn_text, max_chars)
            all_warnings.extend(warns)

            cn_encoded = cn_text.encode("utf-16le")
            # 终止符紧随其中，剩余空间全填 0x00 nop
            pad_len = raw_len - len(cn_encoded) - 2
            final_bytes = cn_encoded + b"\x00\x00" + (b"\x00" * pad_len)

            if len(final_bytes) != raw_len:
                raise RuntimeError(f"内部定长对齐计算错误: 生成 {len(final_bytes)} 字节 != 原始 {raw_len} 字节")

            buf[raw_off:raw_off+raw_len] = final_bytes

        for w in all_warnings:
            print(f"  [格式预警] {w}")

        return bytes(buf)


# ==============================================================================
# 批量导出与回灌流程
# ==============================================================================
def export_all_quests(quest_dir: str, out_json_path: str):
    """批量导出所有任务文本，并显式计算 max_chars 预算"""
    results = {}
    all_qst_files = []
    for root, dirs, files in os.walk(quest_dir):
        for f in files:
            if f.lower().endswith(".qst"):
                all_qst_files.append(os.path.join(root, f))

    all_qst_files.sort()
    print(f"正在扫描并解包 {len(all_qst_files)} 个任务封包...")

    total_dialogues = 0
    for qst_path in all_qst_files:
        rel_path = os.path.relpath(qst_path, os.path.dirname(quest_dir)).replace("\\", "/")
        try:
            with open(qst_path, "rb") as f:
                data = f.read()

            header, files = QSTArchive.unpack_qst(data)
            bin_name = next((k for k in files if k.endswith(".bin")), None)
            if not bin_name:
                continue

            dec_bin = prs_decompress(files[bin_name])
            quest_data = QuestBytecodeTool.extract_texts(dec_bin)
            quest_data["dat_name"] = next((k for k in files if k.endswith(".dat")), "")
            quest_data["bin_name"] = bin_name

            results[rel_path] = quest_data
            total_dialogues += len(quest_data["dialogues"])
        except Exception as e:
            print(f"警告: 解析 {rel_path} 失败: {e}")

    os.makedirs(os.path.dirname(os.path.abspath(out_json_path)), exist_ok=True)
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n========================================================")
    print(f"全量导出完成！")
    print(f"成功导出任务数: {len(results)} / {len(all_qst_files)}")
    print(f"提取剧情、翻页、选项与对白总句数: {total_dialogues} 句 (每句均已包含 max_chars)")
    print(f"导出文件路径: {out_json_path}")
    print(f"========================================================\n")


def import_all_quests(translation_json_path: str, base_dir: str):
    """批量回填翻译好的文本到任务封包 (带超长拦截与警告)"""
    if not os.path.exists(translation_json_path):
        print(f"错误: 翻译文件不存在: {translation_json_path}")
        return

    with open(translation_json_path, "r", encoding="utf-8") as f:
        translations = json.load(f)

    print(f"正在读取翻译文件，准备回填 {len(translations)} 个任务...")

    success_count = 0
    failed_count = 0
    for rel_path, quest_trans in translations.items():
        candidates = [
            os.path.join(base_dir, "Server", rel_path),
            os.path.join(base_dir, rel_path),
        ]
        if rel_path.startswith("quest/"):
            candidates.append(os.path.join(base_dir, "Server", rel_path[6:]))

        qst_path = None
        for cand in candidates:
            if os.path.isfile(cand):
                qst_path = cand
                break

        if not qst_path:
            continue

        try:
            with open(qst_path, "rb") as f:
                raw_data = f.read()

            header, files = QSTArchive.unpack_qst(raw_data)
            bin_name = quest_trans.get("bin_name") or next((k for k in files if k.endswith(".bin")), None)
            if not bin_name or bin_name not in files:
                continue

            dec_bin = prs_decompress(files[bin_name])
            modified_bin = QuestBytecodeTool.reinject_texts(dec_bin, quest_trans, qst_name=rel_path)

            # 重新进行 PRS 压缩
            compressed_bin = prs_compress(modified_bin)
            files[bin_name] = compressed_bin

            # 重新封包写回 QST
            repacked_qst = QSTArchive.pack_qst(header, files)
            with open(qst_path, "wb") as f:
                f.write(repacked_qst)

            success_count += 1
        except Exception as e:
            print(f"❌ 回填 {rel_path} 失败: {e}")
            failed_count += 1

    print(f"\n========================================================")
    print(f"回填完成！成功更新: {success_count} 个任务，失败: {failed_count} 个。")
    print(f"========================================================\n")


def check_translation_json(translation_json_path: str):
    """预先校验翻译文件中的字符数与标签完整度，不修改实际 QST"""
    if not os.path.exists(translation_json_path):
        print(f"错误: 文件不存在: {translation_json_path}")
        return

    with open(translation_json_path, "r", encoding="utf-8") as f:
        translations = json.load(f)

    errors = 0
    warnings = 0
    for rel_path, q in translations.items():
        for field, max_c, en_f in [
            ("title_cn", q.get("title_max_chars", 31), q.get("title", "")),
            ("short_desc_cn", q.get("short_desc_max_chars", 127), q.get("short_desc", "")),
            ("full_desc_cn", q.get("full_desc_max_chars", 289), q.get("full_desc", ""))
        ]:
            val = q.get(field, "").strip()
            if val:
                try:
                    _, warns = QuestBytecodeTool.validate_translation(rel_path, field, en_f, val, max_c)
                    warnings += len(warns)
                    for w in warns: print(f"  [预警] {w}")
                except ValueError as err:
                    print(f"  [错误] {err}")
                    errors += 1

        for d in q.get("dialogues", []):
            cn = d.get("cn", "").strip()
            if cn:
                try:
                    _, warns = QuestBytecodeTool.validate_translation(rel_path, f"Dlg_{d['id']}", d.get("en", ""), cn, d["max_chars"])
                    warnings += len(warns)
                    for w in warns: print(f"  [预警] {w}")
                except ValueError as err:
                    print(f"  [错误] {err}")
                    errors += 1

    print(f"\n校验报告: 发现错误 {errors} 项 (超出硬字符上限)，格式预警 {warnings} 项。")


def main():
    parser = argparse.ArgumentParser(description="PSOBB 任务剧情与对白提取/回填工具 (v2.0 工业级防崩与校验版)")
    parser.add_argument("-e", "--export", action="store_true", help="批量导出所有任务文本为 JSON 格式")
    parser.add_argument("-i", "--import-json", type=str, help="将翻译好的 JSON 文本回填回 QST 文件")
    parser.add_argument("-c", "--check", type=str, help="预检翻译 JSON 文件的合法性（不修改 QST）")
    parser.add_argument("-o", "--output", type=str, default="quest_translations/all_quests_text.json", help="导出 JSON 目标路径")
    parser.add_argument("-q", "--quest-dir", type=str, default="Server/quest", help="服务端任务目录")
    from project_paths import game_root
    parser.add_argument("--game-root", default=str(game_root()), help="自备 Client/Server 的工作目录")
    args = parser.parse_args()

    if args.export:
        export_all_quests(os.path.join(args.game_root, args.quest_dir), args.output)
    elif args.import_json:
        import_all_quests(args.import_json, args.game_root)
    elif args.check:
        check_translation_json(args.check)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
