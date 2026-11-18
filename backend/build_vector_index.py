"""Build and query a local vector index for the PTIT knowledge base."""

import argparse
from pathlib import Path

from vector_search import VectorSearch

ROOT = Path(__file__).resolve().parent.parent


def build_index(directory):
    vs = VectorSearch(directory)
    print(f"Su dung model embedding: {vs.model_name}")
    count = vs.rebuild_index(ROOT / "knowledge_base")
    print(f"Da lap chi muc {count} chunks tu knowledge_base.")


def query_index(directory, questions):
    try:
        results = VectorSearch(directory).query(questions)
    except Exception as error:
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
        build_index(directory)
    else:
        query_index(directory, args.query)


if __name__ == "__main__":
    main()
