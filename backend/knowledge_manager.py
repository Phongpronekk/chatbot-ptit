"""Knowledge base and document indexing manager for admin operations."""

from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
import unicodedata

from retrieval import KnowledgeBase, Passage, load_document, markdown_passages
from uploads import docx_sections, pdf_sections, sheet_sections

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "knowledge_base"


def sanitize_filename(name: str) -> str:
    name = Path(name).name.strip()
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name)
    if not name.endswith(".md"):
        name = Path(name).stem + ".md"
    return name


def document_to_markdown(filename: str, data: bytes) -> str:
    """Convert raw file data (.md, .txt, .pdf, .docx, .xlsx) to standardized Markdown."""
    ext = Path(filename).suffix.lower()
    title = Path(filename).stem.replace("_", " ").title()

    if ext in (".md", ".markdown"):
        text = data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        # Ensure has a # Title if missing
        if not re.search(r"^#\s+.+", text, re.M):
            text = f"# {title}\n\n{text}"
        return text

    if ext == ".txt":
        content = data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        return f"# {title}\n\n## Nội dung\n\n{content}\n"

    if ext == ".pdf":
        sections = list(pdf_sections(data))
        lines = [f"# {title}\n"]
        for section, text in sections:
            clean_text = text.strip()
            if clean_text:
                lines.append(f"## {section}\n\n{clean_text}\n")
        return "\n".join(lines)

    if ext == ".docx":
        sections = list(docx_sections(data))
        lines = [f"# {title}\n"]
        for section, text in sections:
            clean_text = text.strip()
            if clean_text:
                lines.append(f"## {section}\n\n{clean_text}\n")
        return "\n".join(lines)

    raise ValueError(f"Định dạng tệp {ext} không được hỗ trợ. Hãy tải .md, .txt, .pdf hoặc .docx.")


class KnowledgeManager:
    def __init__(self, server, kb_dir=KB_DIR):
        self.server = server
        self.kb_dir = Path(kb_dir)
        self.kb_dir.mkdir(parents=True, exist_ok=True)

    def list_documents(self):
        docs = []
        for path in sorted(self.kb_dir.glob("*.md")):
            stat = path.stat()
            passages = list(load_document(path))
            title = passages[0].title if passages else path.stem
            docs.append({
                "filename": path.name,
                "title": title,
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M"),
                "passages_count": len(passages),
            })
        return docs

    def add_document(self, filename: str, data: bytes):
        """Save a new document to knowledge_base, index into vector DB, and reload server index."""
        md_filename = sanitize_filename(filename)
        md_content = document_to_markdown(filename, data)

        file_path = self.kb_dir / md_filename
        file_path.write_text(md_content, encoding="utf-8")

        # Load newly created passages
        passages = list(load_document(file_path))
        if not passages:
            file_path.unlink(missing_ok=True)
            raise ValueError("Tệp không chứa văn bản trích xuất được.")

        # Update Vector Search index if available
        chunks_indexed = 0
        vector_search = getattr(self.server.index, "vector", None)
        if vector_search:
            chunks_indexed = vector_search.upsert_passages(md_filename, passages)

        # Reload KnowledgeBase keyword index
        new_kb = KnowledgeBase(self.kb_dir)
        if hasattr(self.server.index, "keyword"):
            self.server.index.keyword = new_kb
            self.server.index.document_count = new_kb.document_count
        else:
            self.server.index = new_kb

        return {
            "filename": md_filename,
            "passages_count": len(passages),
            "chunks_indexed": chunks_indexed,
            "total_documents": self.server.index.document_count,
        }

    def delete_document(self, filename: str):
        safe_name = Path(filename).name
        file_path = self.kb_dir / safe_name
        if not file_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy tài liệu '{safe_name}'.")

        file_path.unlink()

        # Delete from vector search
        vector_search = getattr(self.server.index, "vector", None)
        if vector_search:
            vector_search.delete_document(safe_name)

        # Reload KnowledgeBase keyword index
        new_kb = KnowledgeBase(self.kb_dir)
        if hasattr(self.server.index, "keyword"):
            self.server.index.keyword = new_kb
            self.server.index.document_count = new_kb.document_count
        else:
            self.server.index = new_kb

        return {"deleted": safe_name, "total_documents": self.server.index.document_count}

    def reindex_all(self):
        """Re-index all documents in knowledge_base."""
        vector_search = getattr(self.server.index, "vector", None)
        total_chunks = 0
        if vector_search:
            total_chunks = vector_search.rebuild_index(self.kb_dir)

        new_kb = KnowledgeBase(self.kb_dir)
        if hasattr(self.server.index, "keyword"):
            self.server.index.keyword = new_kb
            self.server.index.document_count = new_kb.document_count
        else:
            self.server.index = new_kb

        return {"total_chunks": total_chunks, "total_documents": self.server.index.document_count}
