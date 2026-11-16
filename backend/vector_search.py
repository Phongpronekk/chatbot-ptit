"""Combine keyword and vector retrieval for chat."""

from threading import Lock

import chromadb
from sentence_transformers import SentenceTransformer

from retrieval import Passage

MODEL_NAME = "intfloat/multilingual-e5-small"
COLLECTION_NAME = "ptit_e5_small"


class VectorSearch:
    def __init__(self, directory):
        client = chromadb.PersistentClient(path=str(directory))
        try:
            self.collection = client.get_collection(COLLECTION_NAME, embedding_function=None)
        except chromadb.errors.NotFoundError:
            raise ValueError("Run build_vector_index.py --build to create the vector index.") from None
        if not self.collection.count():
            raise ValueError("The Chroma index is empty. Run build_vector_index.py --build.")
        self.model = SentenceTransformer(MODEL_NAME, device="cpu", local_files_only=True)
        self.model_lock = Lock()

    def query(self, questions):
        with self.model_lock:
            embeddings = self.model.encode(
                [f"query: {question}" for question in questions], normalize_embeddings=True
            )
        return self.collection.query(
            query_embeddings=embeddings.tolist(),
            n_results=min(3, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )


class HybridSearch:
    def __init__(self, keyword, vector):
        self.keyword = keyword
        self.vector = vector
        self.document_count = keyword.document_count

    def search(self, question):
        keywords = self.keyword.search(question)
        matches = self.vector.query([question])
        semantic = [
            Passage(text=text, **metadata)
            for text, metadata in zip(matches["documents"][0], matches["metadatas"][0])
        ]
        # Keep the strongest exact matches and give semantic retrieval one slot
        # when it finds a different section.
        results = {}
        for passage in keywords[:2] + semantic[:1] + keywords[2:] + semantic[1:]:
            results.setdefault((passage.title, passage.section), passage)
            if len(results) == 3:
                break
        return list(results.values())
