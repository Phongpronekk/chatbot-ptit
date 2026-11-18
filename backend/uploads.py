"""Extract and index uploaded documents without modifying the PTIT corpus."""

from collections import Counter, OrderedDict
from contextlib import closing
from io import BytesIO
from pathlib import PurePath
import re
from secrets import token_urlsafe
from threading import Lock
from time import monotonic
from zipfile import ZipFile

from retrieval import KeywordIndex, Passage, fold, markdown_passages
from math_formatting import extract_docx_cell, extract_docx_paragraph, format_math_text

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 500_000
MAX_ARCHIVE_BYTES = 40 * 1024 * 1024
MAX_SHEET_ROWS = 100_000
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 140
UPLOAD_TTL = 2 * 60 * 60
MAX_STORED_UPLOADS = 32


class UploadError(ValueError):
    """A file could not be indexed and the reason can be shown to the user."""


def markdown_sections(data):
    text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text):
        raise UploadError("Tệp Markdown phải là văn bản UTF-8.")
    if len(text) > MAX_EXTRACTED_CHARS:
        raise UploadError("Tệp có quá nhiều nội dung để lập chỉ mục.")
    text = format_math_text(text)
    sections = list(markdown_passages(text, "Nội dung"))
    if not sections:
        yield "Nội dung", text
    for passage in sections:
        yield passage.section, passage.text


def pdf_sections(data):
    from pypdf import PdfReader

    with PdfReader(BytesIO(data)) as reader:
        if reader.is_encrypted:
            raise UploadError("Hãy bỏ mật khẩu của tệp PDF rồi tải lại.")
        for number, page in enumerate(reader.pages, start=1):
            raw_text = page.extract_text() or ""
            yield f"Trang {number}", format_math_text(raw_text)


def docx_sections(data):
    from docx import Document
    from docx.table import Table

    def blocks(container):
        for block in container.iter_inner_content():
            if isinstance(block, Table):
                for row in block.rows:
                    row_text = " | ".join(format_math_text(extract_docx_cell(cell)) for cell in row.cells)
                    yield None, row_text
            else:
                style = block.style.style_id if block.style is not None else ""
                p_text = format_math_text(extract_docx_paragraph(block))
                yield p_text if style.startswith("Heading") else None, p_text

    section = "Nội dung"
    lines = []
    size = 0
    for heading, text in blocks(Document(BytesIO(data))):
        size += len(text)
        if size > MAX_EXTRACTED_CHARS:
            raise UploadError("Tệp có quá nhiều nội dung để lập chỉ mục.")
        if heading:
            if lines:
                yield section, "\n".join(lines)
            section, lines = heading, []
        if text.strip():
            lines.append(text)
    if lines:
        yield section, "\n".join(lines)


def sheet_sections(name, values):
    heading = ""
    lines = []
    size = 0
    first = None
    for number, row in enumerate(values, start=1):
        if number > MAX_SHEET_ROWS:
            raise UploadError("Mỗi trang tính được hỗ trợ tối đa 100.000 dòng.")
        cells = ["" if cell is None else format_math_text(" ".join(str(cell).split())) for cell in row]
        while cells and not cells[-1]:
            cells.pop()
        if not cells:
            continue
        line = f"Dòng {number}: " + " | ".join(cells)
        if not heading:
            heading = line
        if lines and (size + len(line) > CHUNK_SIZE or len(lines) == 8):
            yield f"Sheet {name} · dòng {first}–{last}", "\n".join(lines)
            lines = [heading]
            size = len(heading)
            first = None
        if first is None:
            first = number
        lines.append(line)
        last = number
        size += len(line)
    if lines:
        yield f"Sheet {name} · dòng {first}–{last}", "\n".join(lines)


def xlsx_sections(data):
    from openpyxl import load_workbook

    with closing(load_workbook(BytesIO(data), read_only=True, data_only=True,
                               keep_links=False)) as workbook:
        for sheet in workbook.worksheets:
            sheet.reset_dimensions()
            yield from sheet_sections(sheet.title, sheet.iter_rows(values_only=True))


def xls_sections(data):
    from xlrd import (XL_CELL_BOOLEAN, XL_CELL_DATE, open_workbook, xldate_as_datetime)

    def value(cell):
        if cell.ctype == XL_CELL_DATE:
            return xldate_as_datetime(cell.value, workbook.datemode)
        if cell.ctype == XL_CELL_BOOLEAN:
            return bool(cell.value)
        return cell.value

    with open_workbook(file_contents=data, on_demand=True, ragged_rows=True) as workbook:
        for number, name in enumerate(workbook.sheet_names()):
            sheet = workbook.sheet_by_index(number)
            yield from sheet_sections(name, ([value(cell) for cell in row] for row in sheet.get_rows()))
            workbook.unload_sheet(number)


READERS = {
    ".md": markdown_sections,
    ".markdown": markdown_sections,
    ".pdf": pdf_sections,
    ".docx": docx_sections,
    ".xlsx": xlsx_sections,
    ".xls": xls_sections,
}


def chunks(text):
    text = text.strip()
    while len(text) > CHUNK_SIZE:
        end = text.rfind("\n", CHUNK_SIZE // 2, CHUNK_SIZE)
        if end != -1:
            yield text[:end].strip()
            text = text[end + 1:].lstrip()
            continue
        end = text.rfind(" ", CHUNK_SIZE // 2, CHUNK_SIZE)
        if end == -1:
            end = CHUNK_SIZE
        yield text[:end].strip()
        text = text[end - CHUNK_OVERLAP:].lstrip()
    if text:
        yield text


class UploadedDocument:
    def __init__(self, name, passages):
        self.name = name
        self.index = KeywordIndex(passages)

    def search(self, question, *, required_phrase=None):
        if required_phrase:
            words = list(map(re.escape, fold(required_phrase).split()))
            if PurePath(self.name).suffix.lower() in {".xls", ".xlsx"}:
                # Excel may store the family and given names in separate cells.
                phrase = r"(?:[^\S\r\n]+|[^\S\r\n]*\|[^\S\r\n]*)".join(words)
                exact = re.compile(rf"(?:^dong \d+:|\|)[^\S\r\n]*{phrase}[^\S\r\n]*(?=\||$)", re.M)
            else:
                phrase = r"[^\S\r\n]+".join(words)
                exact = re.compile(rf"(?<!\w){phrase}(?!\w)")
            return self.index.search(question, required_match=lambda text: exact.search(fold(text)))
        # A general summary may have no keywords in common with the document.
        text = " ".join(fold(question).split()).rstrip(" ?!.")
        subject = r"(?:tai lieu|tep|file)(?: nay)?"
        if (
            re.fullmatch(rf"(?:hay |giup toi )?(?:tom tat|tong quan)(?: (?:noi dung )?"
                         rf"{subject})?(?: (?:giup toi|voi))?", text)
            or re.fullmatch(rf"(?:noi dung(?: chinh)? cua {subject} la gi|{subject} noi ve gi)", text)
        ):
            passages = self.index.passages
            positions = sorted({0, (len(passages) - 1) // 2, len(passages) - 1})
            return [passages[position] for position in positions]
        return self.index.search(question)


def index_upload(name, data):
    name = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or len(name) > 255 or not name.isprintable():
        raise UploadError("Tên tệp không hợp lệ.")
    extension = PurePath(name).suffix.lower()
    if extension not in READERS:
        raise UploadError("Chỉ hỗ trợ DOCX, PDF, Markdown và Excel (.xlsx, .xls).")
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise UploadError("Tệp phải có nội dung và dung lượng không quá 10 MB.")

    passages = []
    parts = Counter()
    size = 0
    try:
        if extension in {".docx", ".xlsx"}:
            with ZipFile(BytesIO(data)) as archive:
                if sum(item.file_size for item in archive.infolist()) > MAX_ARCHIVE_BYTES:
                    raise UploadError("Tệp quá lớn sau khi giải nén.")
        for section, text in READERS[extension](data):
            size += len(text)
            if size > MAX_EXTRACTED_CHARS:
                raise UploadError("Tệp có quá nhiều nội dung để lập chỉ mục.")
            for chunk in chunks(text):
                parts[section] += 1
                label = section if parts[section] == 1 else f"{section} · phần {parts[section]}"
                passages.append(Passage(name, label, chunk, ""))
    except UploadError:
        raise
    except ImportError:
        raise UploadError("Máy chủ thiếu thư viện đọc tệp. Hãy chạy python -m pip install -r requirements.txt.") from None
    except UnicodeError:
        raise UploadError("Tệp Markdown phải là văn bản UTF-8.") from None
    except Exception:
        # Parsers can raise format-specific errors for malformed documents.
        raise UploadError("Không đọc được tệp. Kiểm tra định dạng hoặc mật khẩu của tệp.") from None
    if not passages:
        note = " PDF dạng ảnh cần có lớp văn bản OCR." if extension == ".pdf" else ""
        raise UploadError("Không tìm thấy văn bản hoặc dữ liệu trong tệp." + note)
    return UploadedDocument(name, passages)


class UploadStore:
    def __init__(self):
        self.documents = OrderedDict()
        self.lock = Lock()

    def _expire(self, now):
        while self.documents and next(iter(self.documents.values()))[0] <= now:
            self.documents.popitem(last=False)

    def add(self, document):
        upload_id = token_urlsafe(24)
        with self.lock:
            now = monotonic()
            self._expire(now)
            self.documents[upload_id] = (now + UPLOAD_TTL, document)
            if len(self.documents) > MAX_STORED_UPLOADS:
                self.documents.popitem(last=False)
        return upload_id

    def get(self, upload_id):
        with self.lock:
            now = monotonic()
            self._expire(now)
            entry = self.documents.pop(upload_id, None)
            if entry is None:
                return None
            _, document = entry
            self.documents[upload_id] = (now + UPLOAD_TTL, document)
            return document
