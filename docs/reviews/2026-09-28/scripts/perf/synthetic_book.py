"""Deterministic synthetic EPUB-like book used by the performance probes.

Only synthetic text is generated; no user book, profile, or history is read.
"""

from __future__ import annotations

import random
from pathlib import Path
import sys

ROOT = Path(__file__).resolve()
for parent in ROOT.parents:
    if (parent / "plugin" / "OpenCCForSigil").is_dir():
        ROOT = parent
        break
else:  # script copied outside the repository: run it from the repository root
    ROOT = Path.cwd()
PLUGIN = ROOT / "plugin" / "OpenCCForSigil"
if str(PLUGIN) not in sys.path:
    sys.path.insert(0, str(PLUGIN))

# Simplified characters that s2t converts, and neutral characters that it keeps.
CONVERTING = "这个们时国会学发经对实现说话语书长门见车东马鸟鱼开关问间听讲读写电脑软件鼠标网络后来里面还没为从样头点动体过边认识"
NEUTRAL = "的一是不了人我在有他上大中到和地出也子要以可天小心多方生去而好事自用年同如家下着起成日所其然前把"
PUNCT = "，。、；：？！"


def paragraph(rng: random.Random, length: int) -> str:
    chars = []
    for index in range(length):
        roll = rng.random()
        if index and index % rng.randint(12, 30) == 0:
            chars.append(rng.choice(PUNCT))
        elif roll < 0.35:
            chars.append(rng.choice(CONVERTING))
        else:
            chars.append(rng.choice(NEUTRAL))
    return "".join(chars)


def chapter(rng: random.Random, index: int, paragraphs: int, para_chars: int,
            inline_every: int = 4) -> str:
    body = [f'<h2 id="c{index}">第{index}章 {paragraph(rng, 8)}</h2>']
    for p_index in range(paragraphs):
        text = paragraph(rng, para_chars)
        if inline_every and p_index % inline_every == 0:
            cut = len(text) // 2
            text = f'{text[:cut]}<em>{paragraph(rng, 4)}</em>{text[cut:]}'
        if p_index % 25 == 0:
            text += '&amp;“引号”<img src="../Images/a.png" alt="图片说明"/>'
        body.append(f'<p class="p">{text}</p>')
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">\n'
        f'<head><title>第{index}章</title><style>p{{margin:0}}</style></head>\n'
        '<body>\n' + "\n".join(body) + '\n</body>\n</html>\n'
    )


def build_sources(files: int, paragraphs: int, para_chars: int, seed: int = 20260928):
    rng = random.Random(seed)
    return {
        f"chapter{index:04d}": chapter(rng, index, paragraphs, para_chars)
        for index in range(files)
    }


class SyntheticBook:
    """Minimal BookContainer fake used by SigilBookAdapter."""

    def __init__(self, sources: dict[str, str]) -> None:
        self.sources = dict(sources)
        self.reads = 0
        self.writes = []

    def text_iter(self):
        return ((file_id, f"Text/{file_id}.xhtml") for file_id in self.sources)

    def readfile(self, file_id: str) -> str:
        self.reads += 1
        return self.sources[file_id]

    def writefile(self, file_id: str, data: str) -> None:
        self.writes.append((file_id, len(data)))


class CountingBackend:
    """Wrap the real vendored backend and count official conversion calls."""

    def __init__(self, backend) -> None:
        self._backend = backend
        self.convert_calls = 0
        self.convert_chars = 0
        self.compare_calls: dict[str, int] = {}
        self.compare_chars: dict[str, int] = {}

    @property
    def config(self):
        return self._backend.config

    def convert(self, text):
        self.convert_calls += 1
        self.convert_chars += len(text)
        return self._backend.convert(text)

    def convert_for_config(self, config, text):
        self.compare_calls[config] = self.compare_calls.get(config, 0) + 1
        self.compare_chars[config] = self.compare_chars.get(config, 0) + len(text)
        return self._backend.convert_for_config(config, text)

    def provenance(self):
        return self._backend.provenance()

    def close(self):
        self._backend.close()
