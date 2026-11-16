"""Build and query a local vector index for the PTIT knowledge base."""

import argparse
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from retrieval import load_document
from vector_search import COLLECTION_NAME, MODEL_NAME, VectorSearch

ROOT = Path(__file__).resolve().parent.parent


def build_index(client):
    paths = sorted((ROOT / "knowledge_base").glob("*.md"))
    passages = [passage for path in paths for passage in load_document(path)]
    if not passages:
        raise SystemExit("Khong tim thay doan van trong knowledge_base.")

    model = SentenceTransformer(MODEL_NAME, device="cpu")
    inputs = [
        f"passage: {passage.title}\n{passage.section}\n{passage.text}"
        for passage in passages
    ]
    embeddings = model.encode(inputs, normalize_embeddings=True, show_progress_bar=True)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=None,
        configuration={"hnsw": {"space": "cosine"}},
    )
    ids = [f"chunk-{index}" for index in range(len(passages))]
    batch_size = client.get_max_batch_size()
    for start in range(0, len(passages), batch_size):
        end = start + batch_size
        batch = passages[start:end]
        collection.upsert(
            ids=ids[start:end],
            embeddings=embeddings[start:end].tolist(),
            documents=[passage.text for passage in batch],
            metadatas=[
                {"title": passage.title, "section": passage.section, "url": passage.url}
                for passage in batch
            ],
        )

    stale_ids = sorted(set(collection.get(include=[])["ids"]) - set(ids))
    for start in range(0, len(stale_ids), batch_size):
        collection.delete(ids=stale_ids[start:start + batch_size])

    print(f"Indexed {collection.count()} chunks from {len(paths)} documents.")


def query_index(directory, questions):
    try:
        results = VectorSearch(directory).query(questions)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    for question, metadata, distances in zip(
        questions, results["metadatas"], results["distances"]
    ):
        print(f"\n{question}")
        for rank, (source, distance) in enumerate(zip(metadata, distances), start=1):
            print(f"{rank}. {source['title']} | {source['section']}")
            print(f"   Cosine distance: {distance:.3f} | {source['url']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--build", action="store_true", help="Index the Markdown files")
    action.add_argument("--query", nargs="+", metavar="QUESTION", help="Search the index")
    args = parser.parse_args()

    directory = ROOT / ".chroma"
    if args.build:
        build_index(chromadb.PersistentClient(path=str(directory)))
    else:
        query_index(directory, args.query)


if __name__ == "__main__":
    main()
