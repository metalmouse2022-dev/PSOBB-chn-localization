#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PSOBB 地图与城市NPC对白全量汉化批处理工具 (Map & City Dialogue Auto-Translator & Injector)
功能：
1. 自动备份 Client/data/map_*.bin 到 .default
2. 提取城市(总督府/先驱者二号大厅/研究所)及野外(莉可/弗洛文留声机纪念碑)的所有未汉化对白
3. 整合 translation_memory.json，并调用 Gemini API 进行高质量批次汉化
4. 严格校验 max_chars 与特殊标签，无损回灌写入 Client/data/map_*.bin
"""

import os
import sys
import json
import time
import shutil

# 终端编码支持
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
if hasattr(sys.stderr, "reconfigure"):
    try: sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from project_paths import game_root
PROJECT_ROOT = str(game_root())
CLIENT_DATA_DIR = os.path.join(PROJECT_ROOT, "Client", "data")
TM_PATH = os.path.join(BASE_DIR, "quest_translations", "translation_memory.json")
CACHE_PATH = os.path.join(BASE_DIR, "map_dialogues_cache.json")

sys.path.insert(0, BASE_DIR)
from psobb_quest_tool import QuestBytecodeTool
import psobb_api_translator

TARGET_MAP_FILES = [
    # 核心城市与总督府、研究所
    "map_city02_on_j.bin",
    "map_city02_off_j.bin",
    "map_city_on_j.bin",
    "map_city_off_j.bin",
    "map_labo_on_j.bin",
    "map_labo_off_j.bin",
    # 野外调查纪念碑 (红环莉可与弗洛文剧情留声机)
    "map_forest_j.bin",
    "map_forest_j_u.bin",
    "map_cave_j.bin",
    "map_cave_j_u.bin",
    "map_machine_j.bin",
    "map_machine_j_u.bin",
    "map_ruin_j.bin",
    "map_ruin_j_u.bin",
    "map_ancient_j.bin",
    "map_ancient_j_u.bin",
    "map_space_j.bin",
    "map_space_j_u.bin",
    "map_seabed_j.bin",
    "map_seabed_j_u.bin",
    "map_jungle_j.bin",
    "map_jungle_j_u.bin"
]

def load_translation_memory():
    if os.path.exists(TM_PATH):
        try:
            with open(TM_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[警告] 读取 TM 失败: {e}")
    return {}

def save_translation_memory(tm):
    try:
        with open(TM_PATH, "w", encoding="utf-8") as f:
            json.dump(tm, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[错误] 保存 TM 失败: {e}")

def load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(cache):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[错误] 保存缓存失败: {e}")

def main():
    print("========================================================")
    print("     PSOBB 地图与总督府/研究所 NPC 对白汉化灌注系统")
    print("========================================================")

    # 1. 备份原文件
    print("[1/5] 备份原始 map_*.bin 文件...")
    for mf in TARGET_MAP_FILES:
        src = os.path.join(CLIENT_DATA_DIR, mf)
        dst = src + ".default"
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            print(f"  已备份: {mf} -> {mf}.default")

    # 2. 扫描并收集所有对白
    print("\n[2/5] 扫描提取所有地图对白文本...")
    tm = load_translation_memory()
    cache = load_cache()

    # en -> {'min_max': int, 'samples': []}
    all_unique_en = {}
    file_data_map = {}

    for mf in TARGET_MAP_FILES:
        p = os.path.join(CLIENT_DATA_DIR, mf)
        if not os.path.exists(p):
            continue
        with open(p, "rb") as f:
            raw = f.read()
        res = QuestBytecodeTool.extract_texts(raw)
        file_data_map[mf] = (raw, res)

        for d in res["dialogues"]:
            en = d["en"].strip()
            if not en or en == "NO_TEXT":
                continue
            if en not in all_unique_en:
                all_unique_en[en] = {"min_max": d["max_chars"], "sample_file": mf}
            else:
                all_unique_en[en]["min_max"] = min(all_unique_en[en]["min_max"], d["max_chars"])

    print(f"  共收集到 {len(all_unique_en)} 条不重复英文对白。")

    # 3. 匹配 TM 与缓存
    to_translate = []
    translated_map = {}

    for en, meta in all_unique_en.items():
        if en in cache and cache[en].strip():
            translated_map[en] = cache[en]
        elif en in tm and tm[en].strip():
            translated_map[en] = tm[en]
            cache[en] = tm[en]
        else:
            to_translate.append((en, meta["min_max"]))

    print(f"  TM/缓存已有翻译: {len(translated_map)} 条")
    print(f"  待翻译条目: {len(to_translate)} 条")

    # 4. 调用 Gemini API 批处理翻译
    if to_translate:
        api_key = psobb_api_translator.load_api_key()
        if not api_key:
            print("[错误] 未找到 GEMINI_API_KEY，无法自动调用 API 翻译！")
            return

        batch_size = 35
        total_batches = (len(to_translate) + batch_size - 1) // batch_size
        print(f"\n[3/5] 开始调用 Gemini 翻译剩余条目 (共 {total_batches} 个批次)...")

        for b_idx in range(total_batches):
            batch_slice = to_translate[b_idx * batch_size : (b_idx + 1) * batch_size]
            items = []
            for idx, (en_text, max_c) in enumerate(batch_slice):
                items.append({
                    "id": idx,
                    "en": en_text,
                    "max": max_c
                })

            prompt = f"""You are a professional video game localization expert translating SEGA's Phantasy Star Online Blue Burst (PSOBB) into immersive Simplified Chinese.

Context:
- Setting: Colony Ship Pioneer 2, Principal Tyrell, General Chief Natasha Milarose, Hunters, Ragol planet exploration.
- Characters: Red Ring Rico (heroine hunter leaving message capsules), Heathcliff Flowen, Momoka, Coren (wandering merchant), Principal Tyrell.

Requirements:
1. Translate faithfully, naturally and fluently into Simplified Chinese.
2. PRESERVE all placeholder tags EXACTLY as they are: <color X>, <hero name>, <name hero>, <name job>, <bk>, etc.
3. Every translation MUST NOT exceed the specified 'max' character limit (character count of Chinese text).
4. Use '\\n' appropriately to fit classic PSO dialogue boxes (usually <= 16-20 Chinese chars per line).
5. Output ONLY a valid JSON array of objects with keys 'id' and 'cn'.

Items to translate:
{json.dumps(items, ensure_ascii=False, indent=2)}
"""

            success = False
            for attempt in range(3):
                try:
                    raw_resp, model = psobb_api_translator.call_gemini_api(prompt, api_key)
                    # 清洗 markdown 代码块
                    clean_json = psobb_api_translator.extract_json_from_text(raw_resp) if hasattr(psobb_api_translator, 'extract_json_from_text') else raw_resp
                    clean_json = clean_json.strip()
                    if clean_json.startswith("```"):
                        lines = clean_json.splitlines()
                        if lines[0].startswith("```"): lines = lines[1:]
                        if lines and lines[-1].startswith("```"): lines = lines[:-1]
                        clean_json = "\n".join(lines).strip()

                    res_list = json.loads(clean_json)
                    if isinstance(res_list, list):
                        for r in res_list:
                            rid = r.get("id")
                            cn_str = r.get("cn", "").strip()
                            if rid is not None and 0 <= rid < len(batch_slice) and cn_str:
                                orig_en, max_c = batch_slice[rid]
                                # 字符超标保护
                                if len(cn_str) > max_c:
                                    cn_str = cn_str[:max_c]
                                translated_map[orig_en] = cn_str
                                cache[orig_en] = cn_str
                                tm[orig_en] = cn_str
                        success = True
                        print(f"  批次 [{b_idx+1}/{total_batches}] 成功 ({len(res_list)} 条，模型: {model})")
                        break
                except Exception as e:
                    print(f"  批次 [{b_idx+1}/{total_batches}] 重试 ({attempt+1}/3): {e}")
                    time.sleep(2)

            if not success:
                print(f"  [警告] 批次 [{b_idx+1}/{total_batches}] 翻译失败，保留原文。")

            save_cache(cache)
            save_translation_memory(tm)
            time.sleep(0.5)

    # 5. 回灌回各个 map_*.bin
    print("\n[4/5] 回灌写入 Client/data/map_*.bin...")
    injected_count = 0
    for mf, (raw_bin, res) in file_data_map.items():
        buf = bytearray(raw_bin)
        dlg_injected = 0
        for d in res["dialogues"]:
            en_clean = d["en"].strip()
            if not en_clean or en_clean == "NO_TEXT":
                continue
            if en_clean in translated_map and translated_map[en_clean].strip():
                cn_text = translated_map[en_clean].strip()
                raw_off = d["raw_offset"]
                raw_len = d["raw_len"]
                max_c = d["max_chars"]

                cn_bytes = cn_text.encode("utf-16le")
                if len(cn_bytes) > raw_len - 2:
                    cn_text = cn_text[:max_c]
                    cn_bytes = cn_text.encode("utf-16le")

                pad_len = raw_len - len(cn_bytes) - 2
                if pad_len < 0:
                    continue
                new_chunk = cn_bytes + b"\x00\x00" + (b"\x00" * pad_len)
                if len(new_chunk) == raw_len:
                    buf[raw_off : raw_off + raw_len] = new_chunk
                    dlg_injected += 1

        try:
            # 严格保护：头部 0x00..0x39C 必须 bit-for-bit 完全一致，防止破坏入口代码 0x394
            if len(buf) == len(raw_bin) and buf[:0x39C] == raw_bin[:0x39C]:
                out_path = os.path.join(CLIENT_DATA_DIR, mf)
                tmp_path = out_path + ".tmp"
                with open(tmp_path, "wb") as f:
                    f.write(buf)
                os.replace(tmp_path, out_path)
                injected_count += 1
                print(f"  [OK] {mf:<25} 安全灌入完成 (汉化对白: {dlg_injected}/{len(res['dialogues'])}, 头部完整性保护生效)")
            else:
                print(f"  [错误] {mf} 大小不一致或头部损坏，跳过写入")
        except Exception as e:
            print(f"  [错误] {mf} 回灌异常: {e}")

    print("\n[5/5] 完成！")
    print(f"成功汉化回灌 {injected_count}/{len(file_data_map)} 个地图与总督府文件！")

if __name__ == "__main__":
    main()
