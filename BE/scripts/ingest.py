"""Build Chroma explicitly: python -m BE.scripts.ingest."""
from pathlib import Path
import os
import sys
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / 'BE/.env', override=True, encoding='utf-8-sig')


def main():
    from BE.knowledge import Knowledge
    from BE.rag_store import RagStore
    knowledge = Knowledge(Path(os.getenv('DATA_DIR', str(ROOT / 'data'))))
    chunks = knowledge.chunks()
    print(f'{len(knowledge.documents())} documents -> {len(chunks)} chunks', flush=True)
    store = RagStore()
    print('rebuilt' if store.ensure_index(chunks) else 'up-to-date', flush=True)


if __name__ == '__main__':
    main()
