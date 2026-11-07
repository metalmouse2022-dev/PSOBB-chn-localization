#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PSOBB Episode 2 总督府任务 (quest451.raw - quest468.raw) 批处理汉化灌注系统
"""

import os
import sys
import json
import time
import shutil
import glob

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
EP2_DIR = os.path.join(PROJECT_ROOT, "Server", "quest", "princ", "ep2")
TM_PATH = os.path.join(BASE_DIR, "quest_translations", "translation_memory.json")
CACHE_PATH = os.path.join(BASE_DIR, "map_dialogues_cache.json")

sys.path.insert(0, BASE_DIR)
from psobb_quest_tool import QSTArchive, prs_decompress, prs_compress, QuestBytecodeTool
import psobb_api_translator

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
    print("     PSOBB Episode 2 总督府任务 (5-1 ~ 8-3) 汉化系统")
    print("========================================================")

    raw_files = sorted(glob.glob(os.path.join(EP2_DIR, "quest*.raw")))
    print(f"找到 {len(raw_files)} 个 Ep2 原始任务文件。")

    # 1. 备份
    print("[1/5] 备份原始 .raw 文件...")
    for rf in raw_files:
        dst = rf + ".orig"
        if not os.path.exists(dst):
            shutil.copy2(rf, dst)
            print(f"  已备份: {os.path.basename(rf)} -> .orig")

    # 2. 提取文本
    print("\n[2/5] 提取任务与对白文本...")
    tm = load_translation_memory()
    cache = load_cache()

    parsed_quests = {}
    all_unique_texts = {} # text -> min_max_chars

    for rf in raw_files:
        fname = os.path.basename(rf)
        with open(rf, "rb") as f:
            raw_bytes = f.read()

        hdr, files = QSTArchive.unpack_qst(raw_bytes)
        bin_name = [k for k in files if k.endswith('.bin')][0]
        dat_name = [k for k in files if k.endswith('.dat')][0]
        bin_raw = prs_decompress(files[bin_name])
        extracted = QuestBytecodeTool.extract_texts(bin_raw)

        parsed_quests[rf] = {
            "hdr": hdr,
            "bin_name": bin_name,
            "dat_name": dat_name,
            "bin_raw": bin_raw,
            "dat_bytes": files[dat_name],
            "extracted": extracted,
            "orig_size": len(raw_bytes)
        }

        # 收集标题、简报、详述
        for key in ["title", "short_desc", "full_desc"]:
            t = extracted[key].strip()
            if t and t != "NO_TEXT":
                all_unique_texts[t] = min(all_unique_texts.get(t, 9999), extracted[f"{key}_max_chars"])

        # 收集对白
        for d in extracted["dialogues"]:
            en = d["en"].strip()
            if en and en != "NO_TEXT":
                all_unique_texts[en] = min(all_unique_texts.get(en, 9999), d["max_chars"])

    print(f"  收集到不重复文本条目: {len(all_unique_texts)} 条")

    # 3. 匹配已有记忆库
    to_translate = []
    translated_map = {}
    for text, max_c in all_unique_texts.items():
        if text in cache and cache[text].strip():
            translated_map[text] = cache[text]
        elif text in tm and tm[text].strip():
            translated_map[text] = tm[text]
            cache[text] = tm[text]
        else:
            to_translate.append((text, max_c))

    print(f"  TM/缓存已有翻译: {len(translated_map)} 条")
    print(f"  待翻译条目: {len(to_translate)} 条")

    # 4. 调用 Gemini API 翻译
    if to_translate:
        api_key = psobb_api_translator.load_api_key()
        if not api_key:
            print("[错误] 未找到 GEMINI_API_KEY，无法翻译！")
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

            prompt = f"""You are a professional video game localization expert translating SEGA's Phantasy Star Online Blue Burst (PSOBB) Episode 2 Principal / Lab Quests into immersive Simplified Chinese.

Context:
- Setting: Colony Ship Pioneer 2 Lab, Chief Natasha Milarose, Scientist Montague, Elenor, VR Temple, VR Spaceship, Central Control Area, Seabed Facility, Flowen.
- Quest titles: e.g. "5-1:Test/VR Temple 1" -> "5-1:测试/VR神殿 1", "6-1:Test/Spaceship 1" -> "6-1:测试/VR宇宙船 1", "7-1:From the Past" -> "7-1:来自过去", "8-1:Below the Waves" -> "8-1:波涛之下".

Requirements:
1. Translate faithfully, naturally and fluently into Simplified Chinese.
2. PRESERVE all placeholder tags EXACTLY: <color X>, <hero name>, <name hero>, <name job>, <bk>, \\tC etc.
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

    # 5. 回填并打包回 .raw
    print("\n[4/5] 无损回灌并打包写入 Server/quest/princ/ep2/*.raw...")
    injected_count = 0
    for rf, qdata in parsed_quests.items():
        fname = os.path.basename(rf)
        extracted = qdata["extracted"]

        q_trans = {
            "title": extracted["title"],
            "title_cn": translated_map.get(extracted["title"].strip(), extracted["title"]),
            "short_desc": extracted["short_desc"],
            "short_desc_cn": translated_map.get(extracted["short_desc"].strip(), extracted["short_desc"]),
            "full_desc": extracted["full_desc"],
            "full_desc_cn": translated_map.get(extracted["full_desc"].strip(), extracted["full_desc"]),
            "dialogues": []
        }

        # 截断超标保护
        for fld, m_fld in [("title_cn", "title_max_chars"), ("short_desc_cn", "short_desc_max_chars"), ("full_desc_cn", "full_desc_max_chars")]:
            if len(q_trans[fld]) > extracted[m_fld]:
                q_trans[fld] = q_trans[fld][:extracted[m_fld]]

        dlg_injected = 0
        for d in extracted["dialogues"]:
            item = dict(d)
            en_clean = d["en"].strip()
            if en_clean in translated_map:
                cn_text = translated_map[en_clean]
                max_c = d["max_chars"]
                if len(cn_text) > max_c:
                    cn_text = cn_text[:max_c]
                item["cn"] = cn_text
                dlg_injected += 1
            else:
                item["cn"] = ""
            q_trans["dialogues"].append(item)

        try:
            new_bin = QuestBytecodeTool.reinject_texts(qdata["bin_raw"], q_trans, qdata["bin_name"])
            if len(new_bin) != len(qdata["bin_raw"]):
                print(f"  [错误] {fname} bin 尺寸不一致，跳过")
                continue

            comp_bin = prs_compress(new_bin)
            new_raw = QSTArchive.pack_qst(qdata["hdr"], {qdata["bin_name"]: comp_bin, qdata["dat_name"]: qdata["dat_bytes"]})

            tmp_path = rf + ".tmp"
            with open(tmp_path, "wb") as f:
                f.write(new_raw)
            os.replace(tmp_path, rf)
            injected_count += 1
            print(f"  [OK] {fname:<16} 汉化完成 (对白: {dlg_injected}/{len(extracted['dialogues'])}, 大小: {len(new_raw)} 字节)")
        except Exception as e:
            print(f"  [错误] {fname} 写入异常: {e}")

    print("\n[5/5] 完成！")
    print(f"成功汉化回填 {injected_count}/{len(parsed_quests)} 个 Ep2 总督任务！")

if __name__ == "__main__":
    main()
