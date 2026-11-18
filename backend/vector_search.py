"""Combine keyword and vector retrieval for chat."""

from pathlib import Path
from threading import Lock

import chromadb
from sentence_transformers import SentenceTransformer

from retrieval import Passage, load_document

COLLECTION_NAME = "ptit_vector_index"
CANDIDATE_MODELS = [
    "intfloat/multilingual-e5-small",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
]


def load_embedding_model():
    """Load the best available sentence transformer model locally or remotely."""
    for model_name in CANDIDATE_MODELS:
        try:
            return SentenceTransformer(model_name, device="cpu", local_files_only=True), model_name
        except Exception:
            pass
    for model_name in CANDIDATE_MODELS:
        try:
            return SentenceTransformer(model_name, device="cpu"), model_name
        except Exception:
            pass
    raise RuntimeError("Khong the tai mo hinh embedding.")


class VectorSearch:
    def __init__(self, directory, model=None, model_name=None):
        self.directory = Path(directory)
        self.client = chromadb.PersistentClient(path=str(self.directory))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
        )
        if model is None or model_name is None:
            self.model, self.model_name = load_embedding_model()
        else:
            self.model, self.model_name = model, model_name
        self.model_lock = Lock()

    def format_text(self, text, is_query=False):
        if "e5" in self.model_name.lower():
            return f"query: {text}" if is_query else f"passage: {text}"
        return text

    def query(self, questions, n_results=3):
        if self.collection.count() == 0:
            return {"documents": [[] for _ in questions], "metadatas": [[] for _ in questions], "distances": [[] for _ in questions]}
        with self.model_lock:
            embeddings = self.model.encode(
                [self.format_text(question, is_query=True) for question in questions],
                normalize_embeddings=True,
            )
        count = min(n_results, self.collection.count())
        return self.collection.query(
            query_embeddings=embeddings.tolist(),
            n_results=count,
            include=["documents", "metadatas", "distances"],
        )

    def upsert_passages(self, source_file, passages):
        """Index a list of Passage objects for a given source file."""
        if not passages:
            return 0
        inputs = [
            self.format_text(f"{passage.title}\n{passage.section}\n{passage.text}", is_query=False)
            for passage in passages
        ]
        with self.model_lock:
            embeddings = self.model.encode(inputs, normalize_embeddings=True)

        stem = Path(source_file).stem
        ids = [f"{stem}-chunk-{idx}" for idx in range(len(passages))]
        batch_size = max(1, self.client.get_max_batch_size())

        for start in range(0, len(passages), batch_size):
            end = start + batch_size
            self.collection.upsert(
                ids=ids[start:end],
                embeddings=embeddings[start:end].tolist(),
                documents=[p.text for p in passages[start:end]],
                metadatas=[
                    {
                        "title": p.title,
                        "section": p.section,
                        "url": p.url,
                        "source_file": source_file,
                    }
                    for p in passages[start:end]
                ],
            )
        return len(passages)

    def delete_document(self, source_file):
        """Remove all chunks associated with a source file."""
        try:
            self.collection.delete(where={"source_file": source_file})
            return True
        except Exception:
            # Fallback by id check if metadata delete is unsupported
            stem = Path(source_file).stem
            existing = self.collection.get()
            matching_ids = [doc_id for doc_id in existing["ids"] if doc_id.startswith(f"{stem}-chunk-")]
            if matching_ids:
                self.collection.delete(ids=matching_ids)
            return True

    def rebuild_index(self, knowledge_base_dir):
        """Re-index all markdown files in the knowledge base directory."""
        paths = sorted(Path(knowledge_base_dir).glob("*.md"))
        all_passages_with_file = []
        for path in paths:
            file_passages = list(load_document(path))
            all_passages_with_file.append((path.name, file_passages))

        # Reset or delete stale
        existing = self.collection.get()
        if existing and existing.get("ids"):
            self.collection.delete(ids=existing["ids"])

        total_indexed = 0
        for filename, passages in all_passages_with_file:
            total_indexed += self.upsert_passages(filename, passages)
        return total_indexed


class HybridSearch:
    def __init__(self, keyword, vector=None):
        self.keyword = keyword
        self.vector = vector
        self.document_count = keyword.document_count

    def search(self, question):
        keywords = self.keyword.search(question)
        semantic = []
        if self.vector and self.vector.collection.count() > 0:
            try:
                matches = self.vector.query([question])
                if matches and matches.get("documents") and matches["documents"][0]:
                    semantic = [
                        Passage(
                            text=text,
                            title=metadata.get("title", ""),
                            section=metadata.get("section", ""),
                            url=metadata.get("url", ""),
                        )
                        for text, metadata in zip(matches["documents"][0], matches["metadatas"][0])
                    ]
            except Exception as e:
                print(f"Loi tim kiem vector: {e}", flush=True)

        results = {}
        for passage in keywords[:2] + semantic[:1] + keywords[2:] + semantic[1:]:
            results.setdefault((passage.title, passage.section), passage)
            if len(results) == 3:
                break
        return list(results.values())
