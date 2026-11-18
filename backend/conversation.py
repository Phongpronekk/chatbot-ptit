"""Detect greetings and follow-ups, and validate chat history."""

from dataclasses import asdict
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
    """Conservative fallback when Gemini is unavailable; never gate online context."""
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
