"""Vietnamese query normalization and accent-insensitive BM25 candidate search."""
from collections import Counter
import math
import re
import unicodedata


def fold(text):
    text = unicodedata.normalize('NFD', text.casefold()).replace('đ', 'd')
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn')


# Explicit, unambiguous domain terminology. Avoid ambiguous short aliases such as TV.
TERMS = [
    ('bảo hiểm y tế', ['bhyt']), ('bảo hiểm thân thể', ['bhtt']),
    ('ký túc xá', ['ktx']), ('câu lạc bộ', ['clb']),
    ('thực tập tốt nghiệp', ['tttn']), ('đại học chính quy', ['đhcq', 'dhcq']),
    ('công nghệ thông tin', ['cntt']), ('an toàn thông tin', ['attt']),
    ('công tác sinh viên', ['ctsv']), ('giáo dục quốc phòng', ['gdqp']),
    ('học phí', []), ('học bổng', []), ('thư viện', []),
    ('đăng ký học phần', []), ('chuẩn đầu ra', []), ('tốt nghiệp', []),
]
STOP = set('toi minh em ban xin hoi cho biet ve cua la thi voi cac mot va nhung nay do duoc the nao'.split())


def normalize_query(text):
    return ' '.join(unicodedata.normalize('NFC', text).split())


def canonical(text):
    """Match aliases without accents; preserve all other words, negation and numbers."""
    text = normalize_query(text)
    replacements = []
    folded = fold(text)
    for full, aliases in TERMS:
        for name in [full, *aliases]:
            pattern = r'(?<!\w)' + re.escape(fold(name)).replace(r'\ ', r'\s+') + r'(?!\w)'
            for match in re.finditer(pattern, folded):
                replacements.append((match.start(), match.end(), full))
    # Long phrases win where matches overlap (e.g. thực tập tốt nghiệp / tốt nghiệp).
    chosen = []
    for start, end, full in sorted(replacements, key=lambda r: (-(r[1]-r[0]), r[0])):
        if not any(start < b and end > a for a, b, _ in chosen):
            chosen.append((start, end, full))
    for start, end, full in sorted(chosen, reverse=True):
        text = text[:start] + full + text[end:]
    return text


def terms(text):
    text = fold(canonical(text))
    text = re.sub(r'\b(?:bao nhieu|nhu the nao|lam the nao|co cach nao)\b', ' ', text)
    return [t for t in re.findall(r'[a-z0-9]+', text) if t not in STOP]


class KeywordIndex:
    """In-memory BM25 for the active Chroma generation; no second persistent DB."""
    def __init__(self, records):
        self.records = records
        sequences = [terms(r['text']) for r in records]
        self.tokens = [Counter(sequence) for sequence in sequences]
        self.sequences = [' ' + ' '.join(sequence) + ' ' for sequence in sequences]
        self.lengths = [sum(c.values()) for c in self.tokens]
        self.average = sum(self.lengths) / max(len(records), 1)
        self.df = Counter(t for counts in self.tokens for t in counts)

    def search(self, query, limit):
        ordered_terms = terms(query)
        query_terms = set(ordered_terms)
        if not query_terms:
            return [], query_terms
        rows = []
        for index, counts in enumerate(self.tokens):
            overlap = query_terms.intersection(counts)
            if not overlap:
                continue
            score = 0.
            for t in overlap:
                frequency = counts[t]
                idf = math.log(1 + (len(self.records)-self.df[t]+.5)/(self.df[t]+.5))
                score += idf * frequency * 2.5 / (frequency + 1.5 * (.25 + .75*self.lengths[index]/max(self.average,1)))
            # A short phrase needs contiguous support, not words scattered across
            # unrelated clauses (e.g. bảo hiểm thất nghiệp vs bảo hiểm y tế).
            coverage = len(overlap) / len(query_terms)
            phrase = ' ' + ' '.join(ordered_terms) + ' '
            text_terms = self.sequences[index]
            strong = (coverage == 1. and phrase in text_terms) if len(query_terms) <= 5 else coverage >= .8
            rows.append({'index': index, 'score': score, 'coverage': coverage, 'strong': strong})
        return sorted(rows, key=lambda r: (-r['score'], r['index']))[:limit], query_terms
