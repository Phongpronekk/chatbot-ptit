"""Detect greetings and follow-ups, and validate chat history."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re

from retrieval import fold

MAX_QUESTION_CHARS = 500
MAX_HISTORY_TURNS = 6
MAX_HISTORY_ANSWER_CHARS = 10_000
MAX_HISTORY_CHARS = 24_000
MAX_SOURCE_IDS = 12
GREETING = re.compile(
    r"(?:(?:xin )?chao|hello|hi|hey)"
    r"(?: (?:ban|bot|chatbot|ptit(?: chat)?|ad|admin|anh|chi|thay|co))?"
    r"(?: (?:a|nhe|nha))?"
)
PERSON_REFERENCE = re.compile(
    r"\b(?:bạn|ban|người|sinh viên|anh|chị|cô|em)\s+(?:ấy|ay|ý|y|đó|kia|này)\b",
    re.IGNORECASE,
)
FULL_NAME = r"[^\W\d_]+(?:[ \t]+[^\W\d_]+){1,5}"
PERSON_QUESTION = re.compile(
    rf"(?:(?:sinh viên|bạn)\s+)?(?P<name>{FULL_NAME})\s+là ai[?.!]*"
    r"|(?:số thứ tự|stt|mã sinh viên|mssv|lớp|ngày sinh)\s+của\s+"
    rf"(?P<record_name>{FULL_NAME})\s+là\s+(?:bao nhiêu|gì|lớp nào)[?.!]*",
    re.IGNORECASE,
)


def is_greeting_only(question):
    """Match the whole message so a greeting cannot hide a real question."""
    text = " ".join(re.sub(r"[^\w\s]", " ", fold(question)).split())
    return GREETING.fullmatch(text) is not None


def is_immediate_summary(question):
    text = " ".join(re.findall(r"\w+", fold(question)))
    return text in {"tom tat lai", "rut gon lai", "viet ngan gon lai"}


def passage_id(passage):
    """Refer to an original source without sending its text back from the browser."""
    data = json.dumps(asdict(passage), ensure_ascii=False, sort_keys=True)
    return sha256(data.encode("utf-8")).hexdigest()


def read_history(history):
    if not isinstance(history, list) or len(history) > MAX_HISTORY_TURNS:
        raise ValueError
    turns = []
    for turn in history:
        if not isinstance(turn, dict):
            raise ValueError
        question = turn.get("question")
        answer = turn.get("answer", "")
        if (not isinstance(question, str) or not 0 < len(question.strip()) <= MAX_QUESTION_CHARS
                or not isinstance(answer, str) or len(answer) > MAX_HISTORY_ANSWER_CHARS):
            raise ValueError
        clean = {"question": question.strip(), "answer": answer.strip()}
        person = turn.get("person")
        if person is not None:
            if (not isinstance(person, str) or len(person) > MAX_QUESTION_CHARS
                    or not re.fullmatch(FULL_NAME, person)):
                raise ValueError
            clean["person"] = person
        source_ids = turn.get("source_ids")
        if source_ids is not None:
            if (not isinstance(source_ids, list) or len(source_ids) > MAX_SOURCE_IDS
                    or any(not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{64}", key)
                           for key in source_ids)):
                raise ValueError
            clean["source_ids"] = source_ids[:]
        if "intent" in turn:
            if turn["intent"] not in ("question", "transform", "clarification"):
                raise ValueError
            clean["intent"] = turn["intent"]
        if "answer_truncated" in turn:
            if not isinstance(turn["answer_truncated"], bool):
                raise ValueError
            clean["answer_truncated"] = turn["answer_truncated"]
        if not is_greeting_only(clean["question"]):
            turns.append(clean)
    size = sum(len(turn["question"]) + len(turn["answer"]) for turn in turns)
    while size > MAX_HISTORY_CHARS:
        oldest = turns.pop(0)
        size -= len(oldest["question"]) + len(oldest["answer"])
    return turns


def is_follow_up(question):
    """Recognize references that need a subject from the preceding conversation."""
    text = " ".join(re.findall(r"\w+", fold(question)))
    return bool(
        PERSON_REFERENCE.search(question)
        or re.match(r"^(?:the|vay|con|neu vay|sau do|tiep theo)\b", text)
        or re.search(r"\b(?:thi sao|nhu vay|o tren|noi tren|"
                     r"(?:mon|nganh|khoa|truong|co so|hoc ky|nam|dot|muc|qui dinh|quy dinh|"
                     r"thu tuc|tai lieu|tep|file|truong hop) (?:do|ay|kia))\b", text)
        or re.search(r"\b(?:mon|nganh|co so|muc|thu tuc|truong hop) nay\b", text)
        or re.fullmatch(r"(?:tom tat|rut gon|noi ro|chi tiet hon|giai thich|viet lai)"
                        r"(?: lai| ro hon| them)?(?: giup minh| giup toi| di| nhe| voi)?", text)
        or re.search(r"\b(?:cau tra loi|vua noi)\b", text)
        or re.fullmatch(r"(?:can )?(?:nhung )?(?:giay to|ho so) gi(?: vay| a)?", text)
        or re.fullmatch(r"(?:dung(?: roi)?|vang|co|khong|ok|oke|can nhung gi|"
                        r"can gi|lam sao|han dang ky la khi nao)", text)
        or re.fullmatch(r"(?:bao nhieu|khi nao|o dau|the nao|nhu the nao|vi sao|tai sao|"
                        r"(?:hoc phi|le phi|chi phi) (?:la )?bao nhieu|"
                        r"(?:han nop|han cuoi|thoi han) (?:la |den )?khi nao|"
                        r"(?:khoa|nam|hoc ky|ky|dot) (?:nay|sau|truoc|[\divx]+))"
                        r"(?: vay| a)?", text)
    )


def resolve_person_reference(question, history):
    """Use the name from the preceding question when the reference is explicit."""
    if not history or not PERSON_REFERENCE.search(question):
        return None
    previous = next((turn for turn in reversed(history)
                     if turn.get("intent") != "clarification"), None)
    if previous is None:
        return None
    name = previous.get("person")
    if name is None:
        match = PERSON_QUESTION.fullmatch(previous["question"])
        if match is None:
            return None
        name = match["name"] or match["record_name"]
    if PERSON_REFERENCE.search(name):
        return None
    resolved, references = PERSON_REFERENCE.subn(lambda _: name, question)
    if references == 1 and len(resolved) <= MAX_QUESTION_CHARS:
        return resolved, name
    return None


@dataclass(frozen=True)
class LocalContext:
    intent: str
    question: str = ""
    clarification: str = ""
    history_index: int | None = None
    uses_history: bool = False


TOPICS = (
    r"hoc phi|hoc lai",
    r"the sinh vien|cap lai the|mat the",
    r"ky tuc xa|\bktx\b",
    r"bao hiem|\bhyt\b",
    r"bang thpt|bang tot nghiep|ban sao bang",
    r"chuong trinh|tin chi|hoc phan|ma mon",
    r"lich thi|lich kiem tra",
    r"thuc tap|do an",
    r"hoc bong",
)
SLOT_PATTERNS = (
    r"\bkh(?:óa|oá|oa)\s+\d{2,4}\b",
    r"\b(?:năm học|nam hoc)\s+\d{4}\s*[-–/]\s*\d{4}\b",
    r"\b(?:học kỳ|hoc ky|học kì|hoc ki|kỳ|ky)\s+(?:iv|iii|ii|i|[1-4])\b",
    r"\b(?:cơ sở|co so)\s+(?:phía Bắc|phia Bac|phía Nam|phia Nam|Hà Đông|Ha Dong|Hà Nội|Ha Noi|Hồ Chí Minh|Ho Chi Minh|HCM)\b",
)


def _topic_ids(text):
    text = fold(text)
    return {i for i, pattern in enumerate(TOPICS) if re.search(pattern, text)}


def _context_query(previous, question):
    """Carry the subject forward while removing explicitly replaced conditions."""
    base = previous
    for pattern in SLOT_PATTERNS:
        if re.search(pattern, question, re.I):
            base = re.sub(pattern, "", base, flags=re.I)
    if re.fullmatch(r"(?:con )?(?:nam )?20\d{2}[?!. ]*", fold(question).strip()):
        base = re.sub(SLOT_PATTERNS[0], "", base, flags=re.I)
    base = " ".join(base.split()).rstrip(" ?!.")
    remaining = MAX_QUESTION_CHARS - len(question) - 2
    if remaining <= 0:
        return question
    return f"{base[:remaining].rstrip()}. {question}"


def resolve_local_context(question, history):
    """Plan retrieval without an LLM call; leave answer reasoning to generation."""
    text = " ".join(re.findall(r"\w+", fold(question)))
    transform_action = r"(?:tom tat|rut gon|viet ngan gon|dien dat|viet lai|giai thich|noi ro|chi tiet hon|phan tich|danh gia)"
    transform = bool(
        re.fullmatch(transform_action + r"(?: lai| ro hon| them| di| nhe| voi| giup minh| giup toi)*", text)
        or (re.match(transform_action + r"\b", text)
            and re.search(r"\b(?:cau tra loi|luot truoc|uu diem|nhuoc diem|nhuoc dien|uu nhuoc)\b", text))
    )
    if transform:
        if not history:
            return LocalContext("clarification", clarification="Bạn muốn tóm tắt hoặc giải thích nội dung nào?")
        index = len(history) - 1
        if re.search(r"\b(?:dau tien|thu nhat)\b", text):
            index = 0
        else:
            selected = re.search(r"\b(?:cau|luot|cau tra loi) (?:thu |so )?(\d+)\b", text)
            if selected:
                index = int(selected[1]) - 1
        if not 0 <= index < len(history):
            return LocalContext("clarification", clarification="Lượt đó không còn trong ngữ cảnh. Bạn gửi lại nội dung cần giải thích nhé.")
        return LocalContext("transform", question, history_index=index, uses_history=True)

    if PERSON_REFERENCE.search(question):
        person = resolve_person_reference(question, history)
        if person:
            return LocalContext("question", person[0], uses_history=True)
        return LocalContext("clarification", clarification="Bạn đang nhắc tới người nào? Hãy ghi rõ họ tên nhé.")
    if re.search(r"\b(?:cai do|cai nay|dieu do)\b", text):
        return LocalContext("clarification", clarification="Bạn muốn hỏi về nội dung hoặc thủ tục nào? Bạn ghi rõ chủ đề nhé.")

    generic = bool(re.match(
        r"^(?:co (?:phai|can)|can (?:nop|nhung|giay to|ho so)|han (?:dang ky|nop)|"
        r"le phi|chi phi|giay to|ho so|thoi han)\b", text))
    follow_up = is_follow_up(question) or generic
    if not history:
        if follow_up and not _topic_ids(question):
            return LocalContext("clarification", clarification="Bạn muốn tra cứu chủ đề hoặc thủ tục nào? Bạn bổ sung thông tin nhé.")
        return LocalContext("question", question)

    previous = history[-1]
    if previous.get("intent") == "clarification":
        if text in {"khong", "khong phai", "chua dung"}:
            return LocalContext("clarification", clarification="Bạn muốn hỏi chủ đề nào? Bạn ghi rõ yêu cầu nhé.")
        if text in {"dung", "dung roi", "co", "vang", "u", "ok", "oke"}:
            subject = previous.get("answer", "")
            if not _topic_ids(subject):
                return LocalContext("clarification", clarification="Bạn ghi rõ chủ đề hoặc đối tượng muốn tra cứu nhé.")
            return LocalContext("question", _context_query(subject, previous["question"]), uses_history=True)
        if not _topic_ids(question) or len(text.split()) <= 7:
            return LocalContext("question", _context_query(previous["question"], question), uses_history=True)

    current_topics, previous_topics = _topic_ids(question), _topic_ids(previous["question"])
    if current_topics and previous_topics and current_topics.isdisjoint(previous_topics):
        return LocalContext("question", question)
    if not follow_up:
        return LocalContext("question", question)
    return LocalContext("question", _context_query(previous["question"], question), uses_history=True)


def compact_answer_history(history):
    """Keep only recent context and mark clipped answers as incomplete hints."""
    result = []
    for turn in history[-2:]:
        entry = {key: turn[key] for key in ("question", "answer", "intent", "person", "answer_truncated")
                 if key in turn}
        answer = entry.get("answer", "")
        if len(answer) > 1200:
            entry["answer"] = answer[:1200]
            entry["answer_truncated"] = True
        result.append(entry)
    return result
