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
    ('sinh viên', ['sv']), ('giảng viên chủ nhiệm', ['gvcn']),
    ('đăng ký', ['dk', 'dki']), ('điểm trung bình tích lũy', ['gpa', 'cpa']),
    ('kỳ thi', ['ky thi', 'lich thi']),
    ('học phí', []), ('học bổng', []), ('thư viện', []),
    ('đăng ký học phần', []), ('chuẩn đầu ra', []), ('tốt nghiệp', []),
]
STOP = set(
    'toi minh em ban xin hoi cho biet ve cua la thi voi cac mot va nhung nay do duoc the nao '
    'co tai o sao ma theo khi can a nhe nha ha nhi vay da con '
    'neu ke liet tat ca toan gom moi gi dau ai khac ngoai quan trong '
    'ten dang hien lai bao noi vua b k ko dc toa'.split()
)


def normalize_query(text):
    return ' '.join(unicodedata.normalize('NFC', text).split())


_ABBR_TYPO_RE = re.compile(
    r'\b(clb|ktx|bhyt|bhtt|tttn|dhcq|cntt|attt|ctsv|gdqp|gvcn|sv|dk|dki|gpa|cpa)([a-zA-Z]+)\b',
    re.I,
)


def _fix_abbr_typo(match: re.Match) -> str:
    abbr, tail = match.group(1), match.group(2)
    if tail.lower() == abbr[-1].lower() * len(tail):
        return abbr
    return match.group(0)


def canonical(text):
    """Match aliases without accents; preserve all other words, negation and numbers."""
    text = normalize_query(text)
    # Normalize accidental repeated trailing letters on known short abbreviations (e.g. clbb -> clb, ktxx -> ktx)
    text = _ABBR_TYPO_RE.sub(_fix_abbr_typo, text)
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
    text = re.sub(
        r'\b(?:bao nhieu|nhu the nao|lam the nao|co cach nao|danh sach|thong tin(?: ve)?|quy dinh(?: ve)?|'
        r'the nao|ra sao|thi sao|luc nao|co nhung|neu ten|ke ten|liet ke|tat ca|toan bo|quan trong|dang co|hien co)\b',
        ' ',
        text,
    )
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
            phrase_in_text = phrase in text_terms
            if phrase_in_text:
                score *= 1.25
            if len(query_terms) <= 2:
                strong = coverage == 1.
            elif len(query_terms) <= 5:
                strong = coverage >= 0.75 or (coverage >= 0.6 and phrase_in_text)
            else:
                strong = coverage >= 0.6
            rows.append({'index': index, 'score': score, 'coverage': coverage, 'strong': strong})
        return sorted(rows, key=lambda r: (-r['score'], r['index']))[:limit], query_terms


GREETING_PATTERN = re.compile(
    r'^(?:(?:d[ao]|em|minh)\s+)*'
    r'(?:xin\s+)?'
    r'(?:'
        r'chao(?:\s+buoi\s+(?:sang|chieu|toi))?'
        r'|hello'
        r'|helo+'
        r'|he\s*lo'
        r'|hi+'
        r'|hey+'
        r'|alo+'
        r'|a\s+lo+'
        r'|good\s+(?:morning|afternoon|evening)'
    r')'
    r'(?:\s+(?:ban|bot|ad|admin|tro\s+ly|ai|ptit|cau|em|anh|chi|thay|co|moi\s+nguoi|ca\s+nha|there))?'
    r'(?:\s+(?:a|nhe|nha|oi|ne|co|nhi))*'
    r'$',
    re.IGNORECASE,
)


def is_greeting(text: str) -> bool:
    """Return True if the message is a greeting (chào, hello, hi, etc.) without an inquiry."""
    # Strip common emoticons and non-alphanumeric characters
    s = re.sub(r'[:;=8][\-o\*\']?[)\]\(\[dDpP/\:\}\{@\|\\]', ' ', text)
    s = re.sub(r'[\^xX\-_][\._\-]?[\^xX\-_]', ' ', s)
    s = re.sub(r'<3+', ' ', s)
    clean = re.sub(r'[^a-z0-9\s]', ' ', fold(normalize_query(s)))
    clean = ' '.join(clean.split())
    return bool(GREETING_PATTERN.match(clean))


def greeting_response() -> str:
    """Standard polite greeting and introduction of assistant capabilities."""
    return (
        "Chào bạn! Mình là trợ lý ảo hỗ trợ thông tin sinh viên Học viện Công nghệ Bưu chính Viễn thông (PTIT). 👋\n\n"
        "Mình có thể giúp gì cho bạn hôm nay? Bạn có thể hỏi mình về:\n"
        "- **Quy chế & đào tạo:** Đăng ký học phần, tín chỉ, chuẩn đầu ra, điểm rèn luyện...\n"
        "- **Học phí & học bổng:** Mức học phí, thời hạn nộp, chính sách học bổng, bảo hiểm y tế (BHYT)...\n"
        "- **Đời sống sinh viên:** Ký túc xá (KTX), câu lạc bộ (CLB), thư viện...\n"
        "- **Thực tập & việc làm:** Quy định thực tập tốt nghiệp, cơ hội việc làm, đồ án...\n"
        "- **Hỏi đáp theo file:** Tải lên file PDF, Word (.docx), Excel (.xlsx/.xls) để tra cứu nội dung trong file.\n\n"
        "Bạn cần tìm hiểu thông tin gì cứ nhắn cho mình nhé!"
    )

