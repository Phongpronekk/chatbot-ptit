"""Small reproducible retrieval audit. Never calls an LLM or rebuilds the index.

Run from the project root: .venv/Scripts/python.exe docs/evaluate_source_requirements.py
This is a development smoke set, not a held-out accuracy benchmark.
"""
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv

load_dotenv(ROOT / 'BE/.env', override=True, encoding='utf-8-sig')
from BE.knowledge import Knowledge
from BE.rag_store import RagStore

CASES = [
    ('T01-B2', 'KTX B2 mức thu bao nhiêu một tháng?', 'ktx.md', '250.000'),
    ('T01-B1', 'KTX B1 có bao nhiêu chỗ ở?', 'ktx.md', '40 chỗ'),
    ('T02-B2', 'Ở ký túc xá B2 mỗi tháng phải đóng bao nhiêu tiền?', 'ktx.md', '250.000'),
    ('T01-NGOC', 'Sinh viên ở KTX Ngọc Trục được hỗ trợ đi lại bao nhiêu?', 'ktx.md', '150.000'),
    ('T01-CLB', 'Chủ nhiệm CLB Lập trình PTIT là ai?', 'clb.md', 'Đặng Trung Hiếu'),
    ('T01-LIB', 'Người ngoài Học viện có được mượn sách thư viện về nhà không?', 'thu_vien.md', 'không mượn về nhà'),
    ('T01-OFFICE', 'Phòng Giáo vụ tiếp sinh viên buổi sáng vào giờ nào?', 'quy_che_chung.md', '08h30'),
    ('T01-INTERN', 'Ai làm đầu mối cấp giấy giới thiệu thực tập?', 'thuc_tap_viec_lam.md', 'Ban cán sự lớp'),
    ('T05-SPACE', 'quasar supernova astrophysics', None, None),
    ('T05-FOOD', 'Cách làm bánh pizza hải sản?', None, None),
]


def snapshot(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.glob('*.md'))}


def main():
    data = Path(os.getenv('DATA_DIR', str(ROOT / 'data')))
    before = snapshot(data)
    store = RagStore(offline=True)  # Open the active collection only; no ensure_index().
    if store.store is None:
        raise RuntimeError('No compatible index. Run ingest explicitly before evaluation.')
    knowledge = Knowledge(data, rag_store=store)
    rows = []
    for identifier, question, expected_file, expected_text in CASES:
        started = time.perf_counter()
        trace = {}
        sources = knowledge.retrieve(question, trace=trace)
        elapsed = (time.perf_counter() - started) * 1000
        passed = (any(s['source_file'] == expected_file and expected_text.casefold() in s['content'].casefold()
                      for s in sources) if expected_file else not sources)
        rows.append({'id': identifier, 'question': question, 'expected_file': expected_file,
                     'expected_text': expected_text, 'pass': passed, 'elapsed_ms': round(elapsed, 3),
                     'backend': trace.get('backend_used'),
                     'sources': [{'file': s['source_file'], 'title': s['title'], 'score': s['score'],
                                  'url': s['source_url']} for s in sources]})
    times = sorted(r['elapsed_ms'] for r in rows)
    after = snapshot(data)
    result = {'measured_at': datetime.now(timezone.utc).isoformat(),
              'scope': '10 development retrieval smoke cases, not held-out Recall@K or answer accuracy',
              'llm_called': False, 'data_unchanged': before == after, 'data_sha256': before,
              'dataset_bytes': sum(p.stat().st_size for p in data.glob('*.md')),
              'config': {k: os.getenv(k) for k in ['RETRIEVAL_BACKEND', 'EMBEDDING_MODEL_NAME', 'RAG_TOP_K', 'RAG_MIN_SCORE']},
              'manifest': store.manifest,
              'passed': sum(r['pass'] for r in rows), 'total': len(rows),
              'latency_ms': {'mean': round(statistics.mean(times), 3), 'median': statistics.median(times),
                             'p95_nearest_rank': times[-1], 'first_query': rows[0]['elapsed_ms']},
              'cases': rows}
    target = ROOT / 'docs/source_requirements_evaluation.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['passed', 'total', 'data_unchanged', 'latency_ms']}, ensure_ascii=False))
    store.close()
    if before != after:
        raise RuntimeError('Dataset changed during audit')


if __name__ == '__main__':
    main()
