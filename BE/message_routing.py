"""Resolve per-message source intent without making file scope sticky."""
import re

if __package__:
    from .search_text import TERMS, fold, normalize_query
else:
    from search_text import TERMS, fold, normalize_query


def route_message(question, scope='auto', attachment_ids=(), document_ids=(), history=()):
    if attachment_ids:
        return 'documents'
    if scope != 'auto':
        return scope
    query = fold(normalize_query(question)).strip(' .!?')
    if re.search(r'\b(kho (du lieu|ptit)|nguon (chinh thuc|ptit)|bo qua file|khong (hoi|dung) file|cau hoi moi)\b', query):
        return 'knowledge'
    explicit_file = re.search(
        r'\b((trong|theo|tu|cua|ve|doc|tom tat|tong hop) (file|tep|tai lieu|bang tinh)|'
        r'(file|tep|tai lieu|bang tinh) (nay|do|tren|vua|da (gui|tai))|pdf|docx|xlsx|excel|word)\b', query)
    has_file_history = any(message.get('attachments') or any(
        source.get('document_id') for source in message.get('sources', [])) for message in history)
    mentions_file = re.search(r'\b(file|tep)\b', query) and (document_ids or has_file_history)
    if explicit_file or mentions_file:
        return 'documents'
    latest = next((message for message in reversed(history) if message['role'] == 'assistant'), None)
    recent_file_answer = latest and any(source.get('document_id') for source in latest.get('sources', []))
    if recent_file_answer and re.search(
        r'\b((dieu kien|hoc bong|yeu cau|muc|so tien) (do|nay)|vua roi|'
        r'(noi dung|phan) (tren|nay|do)|do la gi)\b', query):
        return 'documents'
    # A new PTIT subject, including a bare "ktx", starts a knowledge query even
    # when the uploaded report happens to mention that same word.
    for full, aliases in TERMS:
        if any(re.search(r'(?<!\w)' + re.escape(fold(name)) + r'(?!\w)', query) for name in [full, *aliases]):
            return 'knowledge'
    if recent_file_answer and re.search(
        r'^(tom tat|tong hop|tong quan|noi dung chinh|so sanh|liet ke|con |vay |the |'
        r'what about|dieu kien|gpa|so tien|muc ho tro|han nop|yeu cau|giai thich|chi tiet|tiep )', query):
        return 'documents'
    return 'knowledge'


def file_history(history, document_ids):
    """Only related file turns can supply follow-up context, never PTIT turns."""
    selected = set(document_ids)
    result = []
    previous_user = None
    for message in history:
        if message['role'] == 'user':
            previous_user = message
        elif any(source.get('document_id') in selected for source in message.get('sources', [])):
            if previous_user:
                result.append(previous_user)
            result.append(message)
    return result[-4:]
