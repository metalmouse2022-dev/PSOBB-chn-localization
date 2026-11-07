"""Validated, reversible edits to Tethealla common drop tables (no EXE patch)."""
import hashlib
import json
import os
from pathlib import Path
import struct
import math

SECTION_IDS = ('Viridia', 'Greennill', 'Skyly', 'Bluefull', 'Purplenum',
               'Pinkal', 'Redria', 'Oran', 'Yellowboze', 'Whitill')


def scale_meseta_tables(data, multiplier):
    if not isinstance(multiplier, int) or not 1 <= multiplier <= 20:
        raise ValueError('美塞塔数量倍率必须为 1—20 的整数')
    buf = bytearray(data)
    tables = []
    ranges = []
    for index in range(256):
        entry = index * 48
        if entry + 48 > len(data):
            raise ValueError('ItemPT.gsl 文件头被截断')
        name = data[entry:entry + 32].split(b'\0')[0]
        if not name:
            break
        sector, size = struct.unpack_from('>II', data, entry + 32)
        start = sector * 0x800
        if not name.startswith(b'ItemPT') or not name.endswith(b'.rel') or size != 0x9e0:
            raise ValueError('不支持的 ItemPT.gsl 表格式')
        if start < 0x3000 or start + size > len(data):
            raise ValueError('ItemPT.gsl 掉落表越界')
        if any(start < hi and start + size > lo for lo, hi in ranges):
            raise ValueError('ItemPT.gsl 包含重叠数据表')
        ranges.append((start, start + size))
        tables.append(start)
    if len(tables) != 160:
        raise ValueError(f'预期 160 张掉落表，实际 {len(tables)}')
    for start in tables:
        # Big endian uint16 min/max pairs, from packed Tethealla PTDATA.
        for offset, pairs in [(0x6ac, 100), (0x8a0, 10)]:
            for pair in range(pairs):
                pos = start + offset + pair * 4
                low, high = struct.unpack_from('>HH', data, pos)
                # Original tables include inverted ranges. Tethealla treats
                # those as a fixed low amount; retain that behavior.
                struct.pack_into('>HH', buf, pos, min(65535, low * multiplier), min(65535, high * multiplier))
    return bytes(buf)


def atomic_write(path, data):
    path = Path(path)
    if path.exists() and path.read_bytes() == data:
        return
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def get_meseta_multiplier(server_dir):
    state = Path(server_dir) / 'param' / 'ItemPT.meseta.json'
    if not state.exists():
        return 1
    record = json.loads(state.read_text(encoding='utf-8'))
    value = record['multiplier']
    if not isinstance(value, int) or not 1 <= value <= 20:
        raise ValueError('美塞塔倍率状态文件损坏')
    return value


def apply_meseta_multiplier(server_dir, multiplier):
    path = Path(server_dir) / 'param' / 'ItemPT.gsl'
    baseline = path.with_name('ItemPT.gsl.meseta-original')
    current = path.read_bytes()
    original = baseline.read_bytes() if baseline.exists() else current
    scaled = scale_meseta_tables(original, multiplier)
    if not baseline.exists():
        atomic_write(baseline, original)
    atomic_write(path, scaled)
    record = {'multiplier': multiplier, 'original_sha256': hashlib.sha256(original).hexdigest(),
              'applied_sha256': hashlib.sha256(scaled).hexdigest()}
    atomic_write(path.with_name('ItemPT.meseta.json'), json.dumps(record, indent=2).encode('utf-8'))


def rare_probability(code):
    # Same 32-bit threshold as ship_server.c ExpandDropRate. Zero disables entries.
    if not 0 <= code <= 255:
        raise ValueError('稀有掉落编码越界')
    return 0.0 if code == 0 else ((2 << max(0, (code >> 3) - 4)) * ((code & 7) + 7)) / 2**32


def adjust_rare_table(data, kind, level, target_probability=0.30):
    """0 restores bytes; 1..30 interpolates each enabled entry toward target.

    Round down to a representable probability. Already higher rates stay intact.
    Box tables may try several entries per floor; these are per-entry rates.
    """
    if type(level) is not int or not 0 <= level <= 30:
        raise ValueError('红盒设置必须为 0—30 的整数，0 表示原始概率')
    if not 0 < target_probability < 1:
        raise ValueError('红盒目标概率必须在 0—1 之间')
    stride, rate_index = {'mob': (2, 0), 'box': (3, 1)}[kind]
    lines = data.splitlines(keepends=True)
    rows = [i for i, line in enumerate(lines) if line.strip() and not line.lstrip().startswith(b'#')]
    if len(rows) % stride:
        raise ValueError('稀有掉落表行数异常')
    box_targets = {}
    if kind == 'box' and level:
        groups = {}
        for start in range(0, len(rows), stride):
            area = int(lines[rows[start]].strip())
            code = int(lines[rows[start + 1]].strip())
            if code and lines[rows[start + 2]].strip() != b'000000':
                groups.setdefault(area, []).append((rows[start + 1], rare_probability(code)))
        for entries in groups.values():
            survival = math.prod(1 - p for _, p in entries)
            total = 1 - survival
            if 0 < total < target_probability:
                target = total + (target_probability - total) * level / 30
                exponent = math.log1p(-target) / math.log(survival)
                for line_index, probability in entries:
                    box_targets[line_index] = 1 - (1 - probability) ** exponent
    for start in range(0, len(rows), stride):
        rate_line = rows[start + rate_index]
        code = int(lines[rate_line].strip())
        original = rare_probability(code)
        item = lines[rows[start + stride - 1]].strip()
        if len(item) != 6 or any(c not in b'0123456789abcdefABCDEF' for c in item):
            raise ValueError('稀有物品代码异常')
        if kind == 'box' and not 0 <= int(lines[rows[start]].strip()) <= 255:
            raise ValueError('箱子区域编码异常')
        if not level or not code or item == b'000000' or original >= target_probability:
            continue
        if kind == 'box' and rate_line not in box_targets:
            continue
        target = box_targets[rate_line] if kind == 'box' else original + (target_probability - original) * level / 30
        selected = max(range(1, 256), key=lambda c: rare_probability(c) if rare_probability(c) <= target else -1)
        line = lines[rate_line]
        # Replace just the numeric token, retaining whitespace and line endings.
        lines[rate_line] = line.replace(line.strip(), str(selected).encode('ascii'), 1)
    return b''.join(lines)


def get_redbox_level(server_dir):
    state = Path(server_dir) / 'drop' / 'redbox-state.json'
    if not state.exists():
        return 0
    level = json.loads(state.read_text(encoding='utf-8'))['level']
    if type(level) is not int or not 0 <= level <= 30:
        raise ValueError('红盒设置记录损坏')
    return level


def get_drop_section_id(server_dir):
    state = Path(server_dir) / 'drop' / 'redbox-state.json'
    if not state.exists():
        return None
    section_id = json.loads(state.read_text(encoding='utf-8')).get('section_id')
    if section_id is not None and (type(section_id) is not int or not 0 <= section_id < 10):
        raise ValueError('掉落徽章状态文件损坏')
    return section_id


def apply_drop_profile(server_dir, level, section_id=None, target_probability=0.30):
    """Apply one Section ID to all drop slots, then apply the redbox setting.

    Known old/new hashes allow safely retrying an interrupted application.
    Unrecognized edits are refused instead of overwriting another editor's work.
    """
    if type(level) is not int or not 0 <= level <= 30:
        raise ValueError('红盒设置必须为 0—30 的整数')
    if section_id is not None and (type(section_id) is not int or not 0 <= section_id < 10):
        raise ValueError('掉落徽章编号必须为 0—9')
    folder = Path(server_dir) / 'drop'
    backup = folder / 'redbox-original'
    state_path = folder / 'redbox-state.json'
    names = [f'ep{ep}_{kind}_{d}_{sid}.txt' for ep in (1, 2, 4)
             for kind in ('mob', 'box') for d in range(4) for sid in range(10)]
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else None
    digest = lambda data: hashlib.sha256(data).hexdigest()
    planned, originals, current_hashes = {}, {}, {}
    for name in names:
        current = (folder / name).read_bytes()
        saved = backup / name
        original = saved.read_bytes() if saved.exists() else current
        current_hashes[name] = digest(current)
        if state:
            if digest(original) != state['original'][name]:
                raise ValueError(f'红盒原表备份校验失败：{name}')
            allowed = [state['applied'][name]]
            if 'pending' in state:
                allowed.append(state['pending'][name])
            if digest(current) not in allowed:
                raise ValueError(f'掉落表已被其他工具修改，请先核对：{name}')
        elif saved.exists() and original != current:
            raise ValueError(f'存在不匹配的红盒备份，请先核对：{name}')
        originals[name] = original
    for name in names:
        ep, kind, difficulty, target = name[:-4].split('_')
        if section_id is None:
            source = originals[name]
        else:
            source_name = f'{ep}_{kind}_{difficulty}_{section_id}.txt'
            source = originals[source_name]
            # Keep the destination's header accurate; only the drop entries
            # come from the selected source ID.
            source_lines = source.splitlines(keepends=True)
            target_lines = originals[name].splitlines(keepends=True)
            if len(source_lines) < 2 or len(target_lines) < 2 or b'Section ID:' not in source_lines[1]:
                raise ValueError(f'掉落表头格式异常：{name}')
            source_lines[1] = target_lines[1]
            source = b''.join(source_lines)
        planned[name] = adjust_rare_table(source, kind, level, target_probability)
    backup.mkdir(exist_ok=True)
    for name, data in originals.items():
        if not (backup / name).exists():
            atomic_write(backup / name, data)
    record = {'level': level, 'section_id': section_id, 'target_probability': target_probability,
              'original': {n: digest(v) for n, v in originals.items()},
              'applied': current_hashes, 'pending': {n: digest(v) for n, v in planned.items()}}
    atomic_write(state_path, json.dumps(record, indent=2).encode('utf-8'))
    for name, data in planned.items():
        atomic_write(folder / name, data)
    record['applied'] = record.pop('pending')
    atomic_write(state_path, json.dumps(record, indent=2).encode('utf-8'))


def apply_redbox_level(server_dir, level):
    """Keep the active drop Section ID when only the redbox setting changes."""
    apply_drop_profile(server_dir, level, get_drop_section_id(server_dir))
