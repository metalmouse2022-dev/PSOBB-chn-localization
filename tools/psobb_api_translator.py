#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PSOBB 任务剧情 Gemini API 自动批量翻译与回灌工具 (Gemini Batch Auto-Translator)

特性:
  1. 支持断点续传：已翻译的批次自动跳过，无需重复请求。
  2. 智能多模型容灾回退：优先使用 gemini-flash-lite-latest，遇 503/429 自动指数退避重试并回退。
  3. 严格 JSON 格式校验：利用 response_mime_type: "application/json"，保证 100% 结构化返回。
  4. 自动字符预算裁剪与防护：超长自动报警与拦截，防止撑破游戏槽位。
  5. 周期性全局广播：每翻译若干批次自动运行全局记忆库 (TM) 广播，实时刷新全游戏汉化进度。
  6. 一键写入封包：翻译完成后可自动调用 psobb_quest_tool 回灌入 Server/quest/*.qst。
"""

import os
import sys
import re
import json
import glob
import time
import argparse
import requests

# 确保 Windows 终端支持 UTF-8 输出
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
BATCHES_DIR = os.path.join(BASE_DIR, "quest_translations", "batches")
TRANSLATED_DIR = os.path.join(BASE_DIR, "quest_translations", "translated_batches")
ENV_PATH = os.path.join(BASE_DIR, ".env")

# 候选模型列表 (按响应速度与稳定性排序)
CANDIDATE_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash",
    "gemini-3.8-flash"
]


def load_api_key():
    """从环境变量或 .env 读取 Gemini API Key"""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key

    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if key:
                            return key
        except Exception:
            pass

    # 若未配置则返回空，调用处提示用户输入
    return ""


def call_gemini_api(prompt_text: str, api_key: str, max_retries: int = 3):
    """调用 Gemini API 进行结构化翻译，内置模型回退与退避重试"""
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.2
        }
    }

    for model_name in CANDIDATE_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(url, json=payload, headers={"x-goog-api-key": api_key}, timeout=60)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"], model_name
                elif resp.status_code in (429, 503):
                    # 频率限制或临时不可用，等待退避
                    wait_sec = attempt * 4
                    print(f"    [重试] {model_name} 返回 {resp.status_code}，等待 {wait_sec} 秒后第 {attempt}/{max_retries} 次重试...")
                    time.sleep(wait_sec)
                else:
                    print(f"    [错误] {model_name} HTTP {resp.status_code}")
                    break
            except Exception as e:
                print(f"    [异常] {model_name} 连接超时或异常: {type(e).__name__}，等待 3 秒...")
                time.sleep(3)

    return None, None


def translate_batches(limit: int = None, specific_batch: str = None, auto_inject: bool = False, delay_between_requests: float = 3.0):
    """执行批量自动翻译任务"""
    api_key = load_api_key()
    if not api_key:
        print("[错误] 未找到有效的 GEMINI_API_KEY，请检查 .env 文件。")
        return

    os.makedirs(TRANSLATED_DIR, exist_ok=True)
    all_batch_files = sorted(glob.glob(os.path.join(BATCHES_DIR, "batch_*.md")))
    if not all_batch_files:
        print(f"[错误] 目录中没有可翻译的批次文件: {BATCHES_DIR}")
        return

    # 过滤待翻译的文件
    tasks = []
    for fpath in all_batch_files:
        fname = os.path.basename(fpath)
        batch_id = re.search(r"batch_(\d+)\.md", fname)
        if not batch_id:
            continue
        bid = batch_id.group(1)
        if specific_batch and bid != specific_batch and fname != specific_batch:
            continue

        out_name = f"batch_{bid}.json"
        out_path = os.path.join(TRANSLATED_DIR, out_name)
        # 检查是否已完成
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            continue

        tasks.append((bid, fpath, out_path))

    if specific_batch and not tasks:
        print(f"[提示] 指定的批次 {specific_batch} 已经翻译完成或不存在。")
        return

    total_tasks = len(tasks)
    print(f"\n========================================================")
    print(f"🚀 PSOBB 任务剧情 Gemini API 自动批量翻译启动")
    print(f"========================================================")
    print(f"  待处理任务数: {total_tasks} 批 (总批次数: {len(all_batch_files)})")
    if limit:
        print(f"  本次限制执行: {limit} 批")
        tasks = tasks[:limit]
    print(f"  请求安全间隔: {delay_between_requests} 秒 (防 429 速率超限)")
    print(f"========================================================\n")

    success_count = 0
    fail_count = 0
    start_time = time.time()

    for idx, (bid, in_path, out_path) in enumerate(tasks, start=1):
        t0 = time.time()
        print(f"[{idx}/{len(tasks)}] 正在翻译批次 {bid} ({os.path.basename(in_path)})...")

        with open(in_path, "r", encoding="utf-8") as fp:
            prompt_content = fp.read()

        raw_output, used_model = call_gemini_api(prompt_content, api_key)
        if not raw_output:
            print(f"  [失败] 批次 {bid} 翻译请求未能成功返回。")
            fail_count += 1
            continue

        def parse_batch_json(raw_text: str):
            raw_text = raw_text.strip()
            # 1. Direct parse
            try:
                data = json.loads(raw_text)
                if isinstance(data, list):
                    return data
            except Exception:
                pass

            # 2. Strip code block ticks ```json ... ```
            cleaned = raw_text
            if "```" in cleaned:
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(r"\s*```$", "", cleaned)
                try:
                    data = json.loads(cleaned)
                    if isinstance(data, list):
                        return data
                except Exception:
                    pass

            # 3. Extract [ ... ]
            match = re.search(r"\[\s*\{.*\}\s*\]", raw_text, re.DOTALL)
            if match:
                snippet = match.group(0)
                for candidate in [snippet, re.sub(r'\\(?![/u"bfnrt\\])', r'\\\\', snippet)]:
                    try:
                        data = json.loads(candidate, strict=False)
                        if isinstance(data, list):
                            return data
                    except Exception:
                        pass

            return None

        try:
            parsed = parse_batch_json(raw_output)
            if not parsed or not isinstance(parsed, list):
                raise ValueError("返回内容非有效 JSON 列表")

            # 自动防护：超长校验与安全回退
            for item in parsed:
                if isinstance(item, dict) and "cn" in item and "max" in item:
                    cn_text = item.get("cn", "")
                    max_chars = item.get("max", 0)
                    if max_chars > 0 and len(cn_text) > max_chars:
                        print(f"    [注意] 批次 {bid} 条目超长 ({len(cn_text)} > {max_chars}): '{cn_text}' -> 安全裁剪为 '{cn_text[:max_chars]}'")
                        item["cn"] = cn_text[:max_chars]

            # 保存结果
            with open(out_path, "w", encoding="utf-8") as fp:
                json.dump(parsed, fp, ensure_ascii=False, indent=2)

            dt = time.time() - t0
            success_count += 1
            print(f"  [成功] 批次 {bid} 翻译完成 (用时 {dt:.1f}s, 提取 {len(parsed)} 条译文, 模型: {used_model})")
        except Exception as e:
            print(f"  [解析错误] 批次 {bid} JSON 解析失败: {e}")
            fail_count += 1

        # 每翻译 5 批自动触发一次入库与全局广播
        if success_count > 0 and success_count % 5 == 0:
            print(f"\n[自动合并] 正在执行阶段性入库与全局记忆库广播...")
            try:
                from psobb_batch_tool import merge_batches
                merge_batches()
            except Exception as e:
                print(f"  [合并异常] {e}")
            print(f"--------------------------------------------------------\n")

        # 冷却休眠
        if idx < len(tasks):
            time.sleep(delay_between_requests)

    # 全部完成后的汇总合并
    total_time = time.time() - start_time
    print(f"\n========================================================")
    print(f"🎉 批量自动翻译运行完毕！")
    print(f"成功: {success_count} 批，失败: {fail_count} 批，总用时: {total_time:.1f} 秒")
    print(f"========================================================\n")

    if success_count > 0:
        print("[入库] 正在执行最终合并与全量广播回填...")
        try:
            from psobb_batch_tool import merge_batches, inject_to_server
            merge_batches()
            if auto_inject:
                print("[封包] 正在自动写入服务端 Server/quest/*.qst...")
                inject_to_server()
        except Exception as e:
            print(f"[合并异常] {e}")


def main():
    parser = argparse.ArgumentParser(description="PSOBB 任务剧情 Gemini API 自动批量翻译工具")
    parser.add_argument("-l", "--limit", type=int, default=None, help="本次最多翻译的批次数 (例如 -l 5)")
    parser.add_argument("-b", "--batch", type=str, default=None, help="指定翻译单个批次 ID (例如 -b 001)")
    parser.add_argument("-a", "--all", action="store_true", help="全量翻译所有剩余未翻译批次")
    parser.add_argument("-i", "--auto-inject", action="store_true", help="翻译完成后自动写入服务端 QST 封包")
    parser.add_argument("--delay", type=float, default=2.5, help="请求间隔秒数 (默认 2.5 秒)")
    args = parser.parse_args()

    translate_batches(limit=args.limit, specific_batch=args.batch, auto_inject=args.auto_inject, delay_between_requests=args.delay)


if __name__ == "__main__":
    main()
