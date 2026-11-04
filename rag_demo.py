"""CLI demo using the same RAG pipeline/configuration as the backend."""
from dotenv import load_dotenv
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / 'BE/.env', override=True, encoding='utf-8-sig')

def main():
    from BE.knowledge import Knowledge
    knowledge = Knowledge(Path(os.getenv('DATA_DIR', str(ROOT / 'data'))))
    knowledge.prepare()
    print('RAG backend:', knowledge.mode)
    try:
        while True:
            question = input('Cau hoi (exit de thoat): ').strip()
            if not question or question.lower() in ('exit', 'quit', 'q'):
                break
            answer, mode, sources = knowledge.answer(question)
            print(answer)
            for i, source in enumerate(sources, 1):
                print(f"[{i}] {source['source_url']} | score={source['score']}")
    finally:
        knowledge.close()

if __name__ == '__main__':
    main()
