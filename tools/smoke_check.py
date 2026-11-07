"""Three small synthetic checks. No game, GUI, network or credentials required."""
from pathlib import Path
import random
import struct
import unittest

import psobb_quest_tool as quest
import psobb_unitxt_tool as unitxt


class SmokeChecks(unittest.TestCase):
    def test_prs_round_trip(self):
        rng = random.Random(417)
        samples = [b'', b'AB', b'abc' * 180, bytes(rng.randrange(256) for _ in range(2048))]
        for module in (quest, unitxt):
            self.assertEqual(module.prs_decompress(b'\x0bAB\x00\x00'), b'AB')
            for sample in samples:
                self.assertEqual(module.prs_decompress(module.prs_compress(sample)), sample)

    def test_qst_and_fixed_slot(self):
        header = bytearray(176)
        files = {'sample.bin': b'payload' * 400, 'sample.dat': b'data' * 350}
        for i, (name, value) in enumerate(files.items()):
            at = i * 88
            encoded = name.encode('ascii')
            header[at + 0x2c:at + 0x2c + len(encoded)] = encoded
            struct.pack_into('<I', header, at + 0x3c, len(value))
        rebuilt = quest.QSTArchive.pack_qst(bytes(header), files)
        actual_header, actual_files = quest.QSTArchive.unpack_qst(rebuilt)
        self.assertEqual(actual_header, bytes(header))
        self.assertEqual(actual_files, files)
        text = 'Hello, tester.'
        slot = text.encode('utf-16le') + b'\0\0'
        source = bytes(quest.QuestBytecodeTool.FULL_END) + slot + b'\xde\xad'
        fields = quest.QuestBytecodeTool.extract_texts(source)
        fields['dialogues'][0]['cn'] = '测试文本。'
        result = quest.QuestBytecodeTool.reinject_texts(source, fields)
        self.assertEqual(len(result), len(source))
        self.assertEqual(result[-2:], b'\xde\xad')
        self.assertEqual(result[:quest.QuestBytecodeTool.FULL_END], source[:quest.QuestBytecodeTool.FULL_END])
        fields['dialogues'][0]['cn'] = '超' * 100
        with self.assertRaises(ValueError):
            quest.QuestBytecodeTool.reinject_texts(source, fields)

    def test_unitxt_round_trip(self):
        tables = [['自造测试', 'line one\nline two', ''], [], ['标签 <name>']]
        payload = unitxt.build_unitxt_bin(tables)
        self.assertEqual(unitxt.parse_unitxt_prs(unitxt.prs_compress(payload)), tables)


if __name__ == '__main__':
    # Compile without writing caches or executing other modules.
    for path in Path(__file__).resolve().parent.glob('*.py'):
        compile(path.read_text(encoding='utf-8-sig'), str(path), 'exec')
    unittest.main(verbosity=2)
