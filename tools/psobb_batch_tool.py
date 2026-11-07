#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PSOBB 任务剧情批量翻译切分与全局记忆库回填工具 (Batch Translation Splitter & TM Merger)

功能特性:
  1. 【全局翻译记忆库 (Translation Memory, --rebuild-tm / -r)】:
     融合所有已翻译的任务对白、标题、简报、详述与 37 条官方标准高频系统短语。
     支持 1:N 全局自动广播回填，翻译一次，全库 145 个任务所有相同英文句位自动填补！
  2. 【去重智能定额切分 (--split / -s)】:
     自动广播既有记忆库后，对全库剩余未翻译对白进行纯净去重合并，
     切分为 <= 24.5 KB 的独立文档，内置 AI 翻译提示词、四大铁律与官方词库。
     批次数量从 160 份骤降至 ~120 份，大幅减轻网页版 AI 的复制粘贴负担。
  3. 【鲁棒合并与全局广播回填 (--merge / -m)】:
     自动读取用户从网页版 AI (ChatGPT / Claude / Gemini) 复制回来的翻译文档，
     支持纯 JSON 或 Markdown 代码块提取，内置超长校验与防爆框检查，
     一键将译文存入记忆库并全局广播覆盖 145 个任务。
  4. 【一键注入服务端 (--inject / -i)】:
     调用 psobb_quest_tool.py 将最新翻译以 NOP 定长补齐无损写入 Server/quest/*.qst 封包。
  5. 【进度看板 (--status / -p)】:
     直观统计 145 个任务、标题、简报、详述、19,774 句对白与记忆库词条数。
"""

import os
import sys
import re
import json
import glob
import argparse
import subprocess

# 确保在 Windows 控制台环境下支持 UTF-8 编码，防止 GBK 字符编码异常
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALL_QUESTS_JSON = os.path.join(BASE_DIR, "quest_translations", "all_quests_text.json")
TM_PATH = os.path.join(BASE_DIR, "quest_translations", "translation_memory.json")
BATCHES_DIR = os.path.join(BASE_DIR, "quest_translations", "batches")
TRANSLATED_DIR = os.path.join(BASE_DIR, "quest_translations", "translated_batches")
GLOSSARY_PATH = os.path.join(BASE_DIR, "quest_translations", "GLOSSARY_术语对照表.md")

MAX_BATCH_BYTES = 24500  # 严格限制在 24.5 KB 以下 (符合 <= 25k 要求)

# 官方高频标准系统与剧情短语库 (严格适配 PSOBB 官方译名与字符预算)
BUILTIN_COMMON_PHRASES = {
    "Yes\nNo": "是\n否",
    "No\nYes": "否\n是",
    "Skip conversation?": "跳过对话吗？",
    "Good luck.": "祝你好运。",
    "Good luck!": "祝你好运！",
    "Mission complete!": "任务完成！",
    "Congratulations!": "恭喜！",
    "Congratulations. Pi!": "恭喜你，哔！",
    "Thank you.": "谢谢。",
    "Thank you!": "谢谢你！",
    "Are you ready?": "准备好了吗？",
    "+ 30 seconds": "+ 30 秒",
    "+ 60 seconds": "+ 60 秒",
    "Hmm...": "嗯……",
    "Huh?": "啊？",
    "What?": "什么？",
    "<hero name>!": "<hero name>！",
    "<hero name>": "<hero name>",
    "Ha ha ha.": "哈哈哈。",
    "...": "……",
    "Hmm.": "嗯。",
    "Too bad.": "真可惜。",
    "Error !": "错误！",
    "Error !!": "错误！！",
    "Failed Challenge!": "挑战失败！",
    "You received <award item>.": "你获得了 <award item>。",
    "You have already received a prize.": "你已经领取过奖励了。",
    "Your inventory is full--\nyou cannot have this item.": "背包已满，\n无法接收此道具。",
    "Waiting for other\nmembers to join.\nIs this OK?": "等待其他队员加入，\n确定吗？",
    "Damage done to opponent:+0.01\nDamage done to player:-0.01": "对敌伤害:+0.01\n自身伤害:-0.01",
    "OK\nCancel": "确定\n取消",
    "Cancel\nOK": "取消\n确定",
    "Please choose:": "请选择：",
    "Please select.": "请选择。",
    "Hey, I'm back.": "嘿，我回来了。",
    "Disturbing?\nNot at all!\nHa, ha, ha.": "觉得不安吗？\n根本不会！\n哈哈哈。",
    "Sorry to make you wait.\nBut take a look at this.": "让你久等了。\n快来看看这个吧。"
}

PROMPT_TEMPLATE = """# PSOBB 任务剧情汉化任务 - 批次 {batch_id} (第 {batch_num}/{total_batches} 批)

> **你是一位精通世嘉经典科幻 RPG《梦幻之星网络版：蓝色脉冲》(PSOBB) 的资深游戏本地化专家。**
> 请将下方 JSON 数据中每个条目的 `"cn": ""` 字段填入地道、精准、优雅的简体中文翻译。
> **请务必返回完整的 JSON 代码块（```json ... ```），保持所有条目结构与字段原样不变。**

---

### ⚠️ 翻译四大铁律（违背将导致游戏客户端崩溃或文字出框）：

1. **【严格字符预算】绝不能超过 `max` 上限**
   * 每个条目都有 `max` 属性，代表该句最多允许的 UTF-16LE 字符数（1个汉字=1个字符）。
   * 严禁超长！超长回填时会被工具直接报错拦截。
   * **短词单双字原则**：
     - `"Yes"` -> **`"是"`** 或 **`"好"`**（切勿翻译为 `"接受委托"` 这种长句，会撑破槽位）
     - `"No"` -> **`"否"`** 或 **`"不"`**
     - `"OK"` -> **`"好"`**
     - `"..."` -> **`"..."`**

2. **【防爆框硬换行】游戏对话框无自动折行，必须用 `\\n` 换行**
   * 全角汉字宽度为英文字符的两倍。
   * **单行汉字严格控制在 14 ~ 18 个汉字以内**！如果一句话超过 18 个汉字，必须手动插入 `\\n` 换行！
   * 严禁整段对白连成一行不写 `\\n`，否则文字会直接冲出游戏对话框右侧边框。

3. **【引擎变量与高亮码】100% 原样保留**
   * 绝对保留 `<hero name>`（玩家角色名）或 `<name>`，切勿修改或翻译！
   * 绝对保留 `\\tC1`、`\\tC2`、`\\tC3`、`%s`、`\\t` 等颜色与格式控制符，放在对应的中文词前。

4. **【官方词库统一】**
   * 地名/组织：Pioneer 2(先驱者二号)、Ragol(拉戈尔)、Principal's Office(总督府)、Hunter's Guild(猎人工会)、Lab(实验室)、Works(军方)
   * 场景：Forest(森林)、Caves(洞穴)、Mines(坑道)、Ruins(遗迹)、Temple(神殿)、Spaceship(宇宙船)、CCA(中央管理区)、Seabed(海底设施)、Crater(环形台地/陨石坑)、Subterranean Desert(地下沙漠)
   * 人物：Rico(丽子)、Flowen(弗洛文)、Tyrell(泰勒总督)、Elenor(艾莉诺)、Bernie(贝尔尼)、Zidd(席德)、Ash(艾修)
   * 道具/货币：Meseta(美塞塔)、Photon Drop(迪亚魔石)、Mag(玛古)、Monomate(单体回复药)

*说明：部分条目带有 `"count": N`，表示该对话在全游戏多处复用，翻译此句即可通过工具 1:N 自动填补全库多处对白；`"sample_q"` 为参考任务来源。*

---

### 待翻译数据 (请在下方的 "cn": "" 中填入中文):

```json
"""

PROMPT_FOOTER = """
```
"""


# ==============================================================================
# 1. 全局翻译记忆库 (TM) 重建与广播
# ==============================================================================
def rebuild_translation_memory(target_json=ALL_QUESTS_JSON, tm_path=TM_PATH):
    """
    从 all_quests_text.json 和内置高频短语库中提取所有已翻译的条目，
    重建全局翻译记忆库 translation_memory.json，并自动全库广播填补未翻译行。
    """
    if not os.path.exists(target_json):
        print(f"错误: 找不到任务文件: {target_json}")
        return {}

    with open(target_json, "r", encoding="utf-8") as f:
        master_data = json.load(f)

    # 1. 初始化记忆库 (优先加载既有 TM，融入内置高频短句)
    tm = dict(BUILTIN_COMMON_PHRASES)
    if os.path.exists(tm_path):
        try:
            with open(tm_path, "r", encoding="utf-8") as f:
                saved_tm = json.load(f)
                if isinstance(saved_tm, dict):
                    tm.update(saved_tm)
        except Exception:
            pass

    # 2. 从 master_data 中提取所有非空的译文，存入 TM (优先记录更紧凑/更短的译文以保证最大通用性)
    extracted_count = 0
    for qpath, q in master_data.items():
        # 任务标题
        t_en = q.get("title", "").strip()
        t_cn = q.get("title_cn", "").strip()
        if t_en and t_cn:
            if t_en not in tm or len(t_cn) < len(tm[t_en]):
                tm[t_en] = t_cn
                extracted_count += 1
        # 任务简报
        s_en = q.get("short_desc", "").strip()
        s_cn = q.get("short_desc_cn", "").strip()
        if s_en and s_cn:
            if s_en not in tm or len(s_cn) < len(tm[s_en]):
                tm[s_en] = s_cn
                extracted_count += 1
        # 任务详述
        f_en = q.get("full_desc", "").strip()
        f_cn = q.get("full_desc_cn", "").strip()
        if f_en and f_cn:
            if f_en not in tm or len(f_cn) < len(tm[f_en]):
                tm[f_en] = f_cn
                extracted_count += 1
        # 剧情对白
        for d in q.get("dialogues", []):
            en = d.get("en", "").strip()
            cn = d.get("cn", "").strip()
            if en and cn:
                if en not in tm or len(cn) < len(tm[en]):
                    tm[en] = cn
                    extracted_count += 1

    # 保存翻译记忆库
    os.makedirs(os.path.dirname(tm_path), exist_ok=True)
    with open(tm_path, "w", encoding="utf-8") as f:
        json.dump(tm, f, ensure_ascii=False, indent=2)

    print(f"\n========================================================")
    print(f"[OK] 全局翻译记忆库 (TM) 重建完成！")
    print(f"记忆库路径: {tm_path}")
    print(f"总记忆词条数: {len(tm)} 条 (融合了既有已翻条目与高频系统短语)")
    print(f"========================================================")

    # 3. 自动执行全局记忆库广播回填
    propagate_memory(master_data, tm, target_json)
    return tm


def propagate_memory(master_data, tm, target_json=ALL_QUESTS_JSON):
    """
    将翻译记忆库 (TM) 中的所有词条，自动广播回填到 master_data 中所有相同英文的位置，
    严格进行字符预算 (max_chars) 安全校验，确保防爆框与游戏稳定性。
    """
    propagated_dlgs = 0
    propagated_titles = 0
    propagated_shorts = 0
    propagated_fulls = 0

    for qpath, q in master_data.items():
        # 标题回填
        t_en = q.get("title", "").strip()
        if not q.get("title_cn") and t_en in tm:
            cand = tm[t_en]
            if len(cand) <= q.get("title_max_chars", 31):
                q["title_cn"] = cand
                propagated_titles += 1

        # 简报回填
        s_en = q.get("short_desc", "").strip()
        if not q.get("short_desc_cn") and s_en in tm:
            cand = tm[s_en]
            if len(cand) <= q.get("short_desc_max_chars", 127):
                q["short_desc_cn"] = cand
                propagated_shorts += 1

        # 详述回填
        f_en = q.get("full_desc", "").strip()
        if not q.get("full_desc_cn") and f_en in tm:
            cand = tm[f_en]
            if len(cand) <= q.get("full_desc_max_chars", 289):
                q["full_desc_cn"] = cand
                propagated_fulls += 1

        # 对白回填
        for d in q.get("dialogues", []):
            d_en = d.get("en", "").strip()
            if not d.get("cn") and d_en in tm:
                cand = tm[d_en]
                if len(cand) <= d.get("max_chars", 9999):
                    d["cn"] = cand
                    propagated_dlgs += 1

    total_propagated = propagated_dlgs + propagated_titles + propagated_shorts + propagated_fulls
    if total_propagated > 0:
        with open(target_json, "w", encoding="utf-8") as f:
            json.dump(master_data, f, ensure_ascii=False, indent=2)
        print(f"[广播完成] 自动填补了 {propagated_dlgs} 句对白、{propagated_titles} 个标题、{propagated_shorts} 篇简报、{propagated_fulls} 篇详述！")
        print(f"累计免除重复翻译: {total_propagated} 处！")
    else:
        print("[INFO] 暂无新增可广播内容。")

    return total_propagated


# ==============================================================================
# 2. 智能去重切分逻辑
# ==============================================================================
def split_all_quests(target_json=ALL_QUESTS_JSON, out_dir=BATCHES_DIR, max_bytes=MAX_BATCH_BYTES):
    """重建 TM、自动广播回填，并将剩余未翻译内容按纯净去重切分为 <= 24.5KB 的独立文档"""
    # 1. 先重建记忆库并执行全量广播回填
    tm = rebuild_translation_memory(target_json)

    with open(target_json, "r", encoding="utf-8") as f:
        master_data = json.load(f)

    # 2. 提取剩余未翻译的标题、简报、详述
    items_to_translate = []
    for qpath, q in master_data.items():
        if not q.get("title_cn"):
            items_to_translate.append({
                "q": qpath,
                "type": "title",
                "max": q.get("title_max_chars", 31),
                "en": q.get("title", ""),
                "cn": ""
            })
        if not q.get("short_desc_cn"):
            items_to_translate.append({
                "q": qpath,
                "type": "short_desc",
                "max": q.get("short_desc_max_chars", 127),
                "en": q.get("short_desc", ""),
                "cn": ""
            })
        if not q.get("full_desc_cn"):
            items_to_translate.append({
                "q": qpath,
                "type": "full_desc",
                "max": q.get("full_desc_max_chars", 289),
                "en": q.get("full_desc", ""),
                "cn": ""
            })

    # 3. 对剩余未翻译的对白进行纯净去重提取 (同句英文只保留一条，预算严格取 min_max)
    untrans_dialogues = {}
    total_raw_dlgs = 0
    for qpath, q in master_data.items():
        for d in q.get("dialogues", []):
            en = d.get("en", "")
            cn = d.get("cn", "")
            if not cn and en.strip():
                total_raw_dlgs += 1
                en_key = en.strip()
                max_c = d.get("max_chars", 9999)
                if en_key not in untrans_dialogues:
                    untrans_dialogues[en_key] = {
                        "type": "dialogue",
                        "en": en,
                        "max": max_c,
                        "count": 1,
                        "sample_q": qpath,
                        "cn": ""
                    }
                else:
                    untrans_dialogues[en_key]["count"] += 1
                    if max_c < untrans_dialogues[en_key]["max"]:
                        untrans_dialogues[en_key]["max"] = max_c

    items_to_translate.extend(untrans_dialogues.values())
    total_items = len(items_to_translate)
    multi_count = sum(1 for v in untrans_dialogues.values() if v["count"] > 1)

    print(f"\n========================================================")
    print(f"[统计] 待翻译文本提取统计:")
    print(f"  - 剩余未翻译唯一条目: {total_items} 条")
    print(f"  - 其中唯一对白条目:   {len(untrans_dialogues)} 条 (覆盖游戏实际 {total_raw_dlgs} 句对白)")
    print(f"  - 多任务复用对白条目: {multi_count} 种 (翻译一次将自动铺满全库！)")
    print(f"========================================================")

    if total_items == 0:
        print("[完成] 恭喜！所有任务剧情均已 100% 翻译完成，无需切分。")
        return

    # 4. 精确切分为 <= 24.5 KB 批次文件
    dummy_header = PROMPT_TEMPLATE.format(batch_id="000", batch_num=1, total_batches=999)
    base_bytes = len((dummy_header + "[\n" + PROMPT_FOOTER).replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))

    batches = []
    cur_batch = []
    cur_bytes = base_bytes

    for item in items_to_translate:
        s = json.dumps(item, ensure_ascii=False, indent=2)
        lines = s.split("\n")
        indented = "\r\n".join("  " + line for line in lines) + ",\r\n"
        item_bytes = len(indented.encode("utf-8"))

        if cur_bytes + item_bytes > max_bytes and cur_batch:
            batches.append(cur_batch)
            cur_batch = [item]
            cur_bytes = base_bytes + item_bytes
        else:
            cur_batch.append(item)
            cur_bytes += item_bytes

    if cur_batch:
        batches.append(cur_batch)

    total_batches = len(batches)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(TRANSLATED_DIR, exist_ok=True)

    # 清理旧的批次文档，防止残留与序号错位
    for old_file in glob.glob(os.path.join(out_dir, "batch_*.md")):
        try:
            os.remove(old_file)
        except Exception:
            pass

    print(f"正在生成 {total_batches} 个独立文档 (严格控制每份磁盘体积 <= 24.5 KB)...")

    for idx, batch_items in enumerate(batches, start=1):
        batch_id = f"{idx:03d}"
        header = PROMPT_TEMPLATE.format(batch_id=batch_id, batch_num=idx, total_batches=total_batches)
        items_json = json.dumps(batch_items, ensure_ascii=False, indent=2)
        full_content = header + items_json + PROMPT_FOOTER

        file_name = f"batch_{batch_id}.md"
        file_path = os.path.join(out_dir, file_name)
        with open(file_path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(full_content)

    print(f"\n========================================================")
    print(f"[完成] 切分完成！共生成 {total_batches} 个轻量化批次文档。")
    print(f"存放目录: {out_dir}")
    print(f"单文件体积: 严格 <= 24.5 KB (专为网页版 AI 4096 Token 限制优化)")
    print(f"使用建议:")
    print(f"  1. 打开任意批次文档 (如 batch_001.md)，直接全选复制贴入网页版 AI。")
    print(f"  2. 将 AI 返回的 JSON 代码块保存为同名文件放入 quest_translations/translated_batches/ 目录。")
    print(f"  3. 运行 `python psobb_batch_tool.py -m`，工具会自动入库并全局广播覆盖全库！")
    print(f"========================================================\n")


# ==============================================================================
# 3. 鲁棒合并回填与全局广播逻辑
# ==============================================================================
def extract_json_from_text(text: str):
    """从文本或 Markdown 中提取 JSON 数组/对象"""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\[\s*\{.*?\}\s*\])\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    start_bracket = text.find("[")
    end_bracket = text.rfind("]")
    if start_bracket != -1 and end_bracket != -1 and end_bracket > start_bracket:
        try:
            return json.loads(text[start_bracket:end_bracket+1])
        except Exception:
            pass

    try:
        return json.loads(text)
    except Exception as e:
        raise ValueError(f"无法解析 JSON 内容: {e}")


def merge_batches(source_path=None, target_json=ALL_QUESTS_JSON, tm_path=TM_PATH):
    """读取已翻译的批次，存入记忆库，并全局广播灌回 all_quests_text.json"""
    if not os.path.exists(target_json):
        print(f"错误: 找不到目标任务数据文件: {target_json}")
        return

    with open(target_json, "r", encoding="utf-8") as f:
        master_data = json.load(f)

    # 加载现有 TM
    tm = dict(BUILTIN_COMMON_PHRASES)
    if os.path.exists(tm_path):
        try:
            with open(tm_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    tm.update(saved)
        except Exception:
            pass

    # 收集待处理的文件列表
    files_to_process = []
    if source_path:
        if os.path.isfile(source_path):
            files_to_process.append(source_path)
        elif os.path.isdir(source_path):
            files_to_process.extend(glob.glob(os.path.join(source_path, "*.md")))
            files_to_process.extend(glob.glob(os.path.join(source_path, "*.json")))
            files_to_process.extend(glob.glob(os.path.join(source_path, "*.txt")))
    else:
        for d in [TRANSLATED_DIR, BATCHES_DIR]:
            if os.path.exists(d):
                files_to_process.extend(glob.glob(os.path.join(d, "*.md")))
                files_to_process.extend(glob.glob(os.path.join(d, "*.json")))
                files_to_process.extend(glob.glob(os.path.join(d, "*.txt")))

    files_to_process = sorted(list(set(files_to_process)))
    if not files_to_process:
        print("未找到任何已翻译的批次文件。请将 AI 翻译后的文件放入 quest_translations/translated_batches/ 目录。")
        return

    print(f"正在扫描并合并 {len(files_to_process)} 个批次文件...")

    total_merged = 0
    overlength_errors = 0
    files_updated = 0
    new_tm_entries = 0

    for fpath in files_to_process:
        fname = os.path.basename(fpath)
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                raw_text = fp.read()

            items = extract_json_from_text(raw_text)
            if not isinstance(items, list):
                continue

            file_has_cn = False
            for item in items:
                cn_text = item.get("cn", "").strip()
                if not cn_text:
                    continue

                item_type = item.get("type")
                en_text = item.get("en", "").strip()
                max_c = item.get("max", 9999)

                # 记录进翻译记忆库
                if en_text:
                    if en_text not in tm or len(cn_text) < len(tm[en_text]):
                        tm[en_text] = cn_text
                        new_tm_entries += 1

                # 长度校验
                if len(cn_text) > max_c:
                    print(f"  [超长拦截] [{fname}]: 长度 {len(cn_text)} > 上限 {max_c} 字: {repr(cn_text[:20])}")
                    overlength_errors += 1
                    continue

                # 1. 标题/简报/详述处理
                if item_type in ("title", "short_desc", "full_desc"):
                    qpath = item.get("q")
                    if qpath and qpath in master_data:
                        master_data[qpath][item_type + "_cn"] = cn_text
                        total_merged += 1
                        file_has_cn = True

                # 2. 对白处理
                elif item_type == "dialogue":
                    qpath = item.get("q")
                    dlg_id = item.get("id")
                    if qpath and dlg_id is not None and qpath in master_data:
                        # 指定了具体的 q 和 id
                        for d in master_data[qpath].get("dialogues", []):
                            if d["id"] == dlg_id:
                                d["cn"] = cn_text
                                total_merged += 1
                                file_has_cn = True
                                break
                    elif en_text:
                        # 去重条目：自动全库匹配该英文
                        matched = 0
                        for qp, q_entry in master_data.items():
                            for d in q_entry.get("dialogues", []):
                                if d.get("en", "").strip() == en_text:
                                    if len(cn_text) <= d.get("max_chars", 9999):
                                        if not d.get("cn"):
                                            d["cn"] = cn_text
                                            matched += 1
                        if matched > 0:
                            total_merged += matched
                            file_has_cn = True

            if file_has_cn:
                files_updated += 1
        except Exception:
            pass

    # 执行全局记忆库广播回填
    propagated = propagate_memory(master_data, tm, target_json)

    # 保存主 JSON 文件与记忆库
    with open(target_json, "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=2)

    with open(tm_path, "w", encoding="utf-8") as f:
        json.dump(tm, f, ensure_ascii=False, indent=2)

    print(f"\n========================================================")
    print(f"合并与全局广播回填完成！")
    print(f"成功扫描批次文件: {len(files_to_process)} 个，提取有翻译的文件: {files_updated} 个")
    print(f"直接合并写入条目: {total_merged} 条，记忆库全量广播回填: {propagated} 条")
    print(f"记忆库总词条容量: {len(tm)} 条")
    if overlength_errors > 0:
        print(f"[警告] 拦截超长错误: {overlength_errors} 处（已跳过写入，避免破坏游戏）")
    print(f"主数据文件已更新: {target_json}")
    print(f"========================================================\n")

    # 打印全局最新进度看板
    show_status(target_json)


# ==============================================================================
# 4. 进度看板
# ==============================================================================
def show_status(target_json=ALL_QUESTS_JSON, tm_path=TM_PATH):
    """显示任务剧情全局汉化进度看板"""
    if not os.path.exists(target_json):
        print(f"错误: 找不到任务文件: {target_json}")
        return

    with open(target_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    total_quests = len(data)
    completed_quests = 0
    t_count = sum(1 for q in data.values() if q.get("title_cn"))
    s_count = sum(1 for q in data.values() if q.get("short_desc_cn"))
    f_count = sum(1 for q in data.values() if q.get("full_desc_cn"))

    total_dlgs = 0
    trans_dlgs = 0

    for q in data.values():
        dlgs = q.get("dialogues", [])
        total_dlgs += len(dlgs)
        q_trans = sum(1 for d in dlgs if d.get("cn"))
        trans_dlgs += q_trans
        if bool(q.get("title_cn")) and bool(q.get("short_desc_cn")) and bool(q.get("full_desc_cn")) and (len(dlgs) == 0 or q_trans == len(dlgs)):
            completed_quests += 1

    dlg_pct = (trans_dlgs / total_dlgs * 100) if total_dlgs else 0
    tm_count = 0
    if os.path.exists(tm_path):
        try:
            with open(tm_path, "r", encoding="utf-8") as f:
                tm_data = json.load(f)
                tm_count = len(tm_data)
        except Exception:
            pass

    batch_files = glob.glob(os.path.join(BATCHES_DIR, "batch_*.md"))
    translated_batch_files = glob.glob(os.path.join(TRANSLATED_DIR, "*.*"))

    print(f"\n========================================================")
    print(f"          PSOBB 任务剧情全局汉化进度看板")
    print(f"========================================================")
    print(f"  完全汉化任务:  {completed_quests:3d} / {total_quests:3d}  ({completed_quests / total_quests * 100:5.1f}%)")
    print(f"  任务标题 (Title):   {t_count:3d} / {total_quests:3d}  ({t_count / total_quests * 100:5.1f}%)")
    print(f"  任务简报 (Short):   {s_count:3d} / {total_quests:3d}  ({s_count / total_quests * 100:5.1f}%)")
    print(f"  任务详述 (Full):    {f_count:3d} / {total_quests:3d}  ({f_count / total_quests * 100:5.1f}%)")
    print(f"  剧情对白 (Dialog): {trans_dlgs:5d} / {total_dlgs:5d}  ({dlg_pct:5.2f}%)")
    print(f"--------------------------------------------------------")
    print(f"  全局翻译记忆库 (TM): {tm_count} 条通用词条")
    print(f"  当前生成批次文档:   {len(batch_files)} 个 (存放于 batches/)")
    print(f"  已交付翻译批次:     {len(translated_batch_files)} 个 (存放于 translated_batches/)")
    print(f"========================================================\n")


# ==============================================================================
# 5. 一键灌回 QST 封包
# ==============================================================================
def inject_to_server(target_json=ALL_QUESTS_JSON):
    """直接调用 psobb_quest_tool.py 执行服务端回灌"""
    quest_tool = os.path.join(BASE_DIR, "psobb_quest_tool.py")
    if not os.path.exists(quest_tool):
        print(f"错误: 找不到工具脚本: {quest_tool}")
        return

    print("正在启动 psobb_quest_tool.py 执行服务端 QST 封包回灌...")
    cmd = [sys.executable, quest_tool, "-i", target_json]
    from project_paths import game_root
    cmd.extend(["--game-root", str(game_root())])
    ret = subprocess.run(cmd, cwd=str(game_root()))
    if ret.returncode == 0:
        print("[成功] 服务端回灌成功！已全部无损重构并写入 Server/quest/*.qst。")
    else:
        print(f"回灌异常退出，错误码: {ret.returncode}")


def main():
    parser = argparse.ArgumentParser(description="PSOBB 任务剧情批量翻译切分与全局记忆库回填工具 (Batch Tool)")
    parser.add_argument("-s", "--split", action="store_true", help="重建 TM、自动广播并切分未翻译批次 (<= 24.5K)")
    parser.add_argument("-m", "--merge", nargs="?", const="", help="从 translated_batches 或指定路径合并译文并全局广播")
    parser.add_argument("-r", "--rebuild-tm", action="store_true", help="从现有主数据与高频词库重建翻译记忆库并全库广播")
    parser.add_argument("-i", "--inject", action="store_true", help="一键将主 JSON 译文回灌进服务端 Server/quest/*.qst")
    parser.add_argument("-p", "--status", action="store_true", help="查看当前翻译全局完成进度看板")
    parser.add_argument("--max-size", type=int, default=MAX_BATCH_BYTES, help="单批次最大字节数 (默认 24500 字节)")
    args = parser.parse_args()

    if args.rebuild_tm:
        rebuild_translation_memory()
    elif args.split:
        split_all_quests(max_bytes=args.max_size)
    elif args.merge is not None:
        path = args.merge if args.merge else None
        merge_batches(path)
    elif args.inject:
        inject_to_server()
    elif args.status:
        show_status()
    else:
        show_status()
        print("提示: 使用 -s/--split 切分批次，-m/--merge 合并翻译，-r/--rebuild-tm 重建记忆库，-i/--inject 写入服务端。")


if __name__ == "__main__":
    main()
