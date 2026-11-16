"""Detect follow-up questions and validate the history sent with a chat turn."""

import re

from retrieval import fold

MAX_QUESTION_CHARS = 500
MAX_HISTORY_TURNS = 3
MAX_HISTORY_ANSWER_CHARS = 700
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
        turns.append(clean)
    return turns


def is_follow_up(question):
    text = " ".join(re.findall(r"\w+", fold(question)))
    return bool(
        PERSON_REFERENCE.search(question)
        or re.match(r"^(?:the|vay|con|neu vay|sau do|tiep theo)\b", text)
        or re.search(r"\b(?:thi sao|nhu vay|o tren|noi tren|"
                     r"(?:mon|nganh|khoa|truong|co so|hoc ky|nam|dot|muc|qui dinh|quy dinh|"
                     r"thu tuc|tai lieu|tep|file|truong hop) (?:do|ay|kia))\b", text)
        or re.search(r"\b(?:mon|nganh|co so|muc|thu tuc|truong hop) nay\b", text)
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
    previous = history[-1]
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
