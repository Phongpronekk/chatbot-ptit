"""Index Markdown sections and table rows for the local demo."""

from collections import Counter
from dataclasses import dataclass
from math import log
from pathlib import Path
import re
import unicodedata

STOP_WORDS = set("""
a an ai anh bao ban bang ban biet bi bon cho co cua cung day de den du duoc
gi gioi hai hay ho hoi hocvien hom khac khi khoi khong la lai lam lan len loai
minh mot nao nay neu nhieu nhom nhu nhung noi nua o phai qua ra rang roi sau
se so tai theo thi tren trong tu tung va ve voi vua xem xin
""".split()) - {"bao", "khong", "nhieu", "so", "ai", "lai"}

ALIASES = (
    ("bao nhieu tin chi", "so tin chi khoi luong"),
    ("mat the", "cap lai the sinh vien"),
    ("lam lai the", "cap lai the sinh vien"),
    ("ky tuc xa", "ktx noi tru"),
    ("ktx", "ky tuc xa noi tru"),
    ("clc", "chat luong cao"),
    ("udu", "dinh huong ung dung"),
    ("do an", "tot nghiep"),
)


def fold(text):
    decomposed = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def tokens(text):
    return [word for word in re.findall(r"[a-z0-9]+", fold(text))
            if len(word) > 1 and word not in STOP_WORDS]


@dataclass(frozen=True)
class Passage:
    title: str
    section: str
    text: str
    url: str


def load_document(path):
    raw = path.read_text(encoding="utf-8-sig")
    frontmatter = re.match(r"\A---\s*\n(.*?)\n---\s*\n", raw, flags=re.S)
    metadata = frontmatter[1] if frontmatter else ""
    source = re.search(r'^source_url: "(https://[^"\s]+)"$', metadata, re.M)
    url = source[1] if source else ""
    body = raw[frontmatter.end():] if frontmatter else raw
    title_match = re.search(r"^# (.+)$", body, re.M)
    title = title_match[1] if title_match else path.stem
    sections = re.split(r"^#{2,6} (.+)$", body, flags=re.M)
    content = [(title, re.sub(r"^# .+\n?", "", sections[0], flags=re.M))]
    content.extend(zip(sections[1::2], sections[2::2]))

    for section, text in content:
        clean = re.sub(r"^\[(?:PDF gốc của PTIT|Nguồn PTIT)\].*$", "", text, flags=re.M).strip()
        if not clean:
            continue
        rows = clean.splitlines()
        if len(rows) < 13 or not all(row.startswith("|") for row in rows):
            yield Passage(title, section, clean, url)
            continue
        header = "\n".join(rows[:2])
        for start in range(2, len(rows), 4):
            table = header + "\n" + "\n".join(rows[start:start + 4])
            yield Passage(title, section, table, url)


class KnowledgeBase:
    def __init__(self, directory: Path):
        paths = sorted(directory.glob("*.md"))
        self.document_count = len(paths)
        self.passages = [passage for path in paths for passage in load_document(path)]
        self.vectors = []
        self.frequency = Counter()
        for passage in self.passages:
            vector = Counter(tokens(passage.text))
            vector.update(tokens(passage.title))
            vector.update(tokens(passage.section) * 2)
            self.vectors.append(vector)
            self.frequency.update(vector.keys())
        self.lengths = [sum(vector.values()) for vector in self.vectors]
        self.mean_length = sum(self.lengths) / max(len(self.vectors), 1) or 1

    def search(self, question):
        query = set(tokens(question))
        words = " ".join(re.findall(r"[a-z0-9]+", fold(question)))
        expanded = {
            word for phrase, alternative in ALIASES
            if f" {phrase} " in f" {words} "
            for word in tokens(alternative)
        }
        weights = {word: 0.45 for word in expanded - query}
        weights.update(dict.fromkeys(query, 1.0))
        count = len(self.passages)
        idf = {word: log(1 + (count - self.frequency[word] + 0.5)
                                / (self.frequency[word] + 0.5))
               for word in weights if self.frequency[word]}
        ranked = []
        for passage, vector, length in zip(self.passages, self.vectors, self.lengths):
            hits = query.intersection(vector)
            if len(hits) < min(2, len(query)) or not hits:
                continue
            normalizer = 1.4 * (0.35 + 0.65 * length / self.mean_length)
            score = sum(weights[word] * idf[word] * (2.4 * vector[word])
                        / (vector[word] + normalizer)
                        for word in idf.keys() & vector.keys())
            # Prefer literal document headings and exact course codes.
            scope = fold(f"{passage.title} {passage.section}")
            section = fold(passage.section)
            if any(phrase in words for phrase in ("khi nao", "thoi han", "han nop",
                                                  "han dang ky", "lich dang ky")):
                if any(phrase in section for phrase in ("lich", "thoi gian", "han nop")):
                    score += 4.0
            for phrase in ("so tin chi", "cap lai the", "lop rieng", "lop ghep",
                           "chat luong cao", "dinh huong ung dung", "hoc vuot", "ky phu"):
                if phrase in words and phrase in scope:
                    score += 1.8
            if "bao nhieu tin chi" in words and "so tin chi" in scope:
                score += 9.0
            if "mat the" in words and "cap lai the" in scope:
                score += 1.8
            if any(any(c.isdigit() for c in word) and any(c.isalpha() for c in word)
                   and word in vector for word in query):
                score += 4.0
            ranked.append((score, passage))
        ranked.sort(key=lambda candidate: candidate[0], reverse=True)
        if not ranked or ranked[0][0] < 2.4:
            return []

        results = []
        origins = set()
        for score, passage in ranked:
            origin = (passage.title, passage.section)
            if origin in origins or score < ranked[0][0] * 0.62:
                continue
            origins.add(origin)
            results.append(passage)
            if len(results) == 3:
                break
        return results
