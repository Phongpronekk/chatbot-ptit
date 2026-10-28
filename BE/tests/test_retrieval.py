import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from langchain_core.embeddings import Embeddings
from BE.knowledge import Knowledge
from BE.rag_store import RagStore


class FakeEmbeddings(Embeddings):
    def __init__(self):
        self.calls = 0
        self.fail = False
    def embed_documents(self, texts):
        if self.fail:
            raise RuntimeError('test encoder outage')
        self.calls += len(texts)
        return [[1., 0., 0.] if 'Học phí' in t else [0., 1., 0.] for t in texts]
    def embed_query(self, text):
        return [1., 0., 0.]


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / 'storage'
        root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root, ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        self.data = self.root / 'data'
        self.data.mkdir()
        self.env = patch.dict(os.environ, {'RETRIEVAL_BACKEND': 'vector', 'EMBEDDING_MODEL_NAME': 'test',
            'CHUNK_SIZE': '400', 'CHUNK_OVERLAP': '60', 'RAG_MIN_SCORE': '0.35'})
        self.env.start()
        (self.data / 'fees.md').write_text('---\nsource_url: https://ptit.edu.vn/fees\nfetched_date: 2026-10-28\ntopic_group: Học phí\n---\n# Học phí\nMức thu là 10 triệu đồng.\n', encoding='utf-8')
        self.encoder = FakeEmbeddings()
        self.store = RagStore(self.root / 'chroma', embeddings=self.encoder)
        self.chunks = Knowledge(self.data).chunks()

    def tearDown(self):
        self.store.close()
        self.env.stop()
        self.tmp.cleanup()

    def build(self, chunks=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.store.ensure_index(chunks or self.chunks)

    def test_idempotent_persistent_index_and_cosine_score(self):
        self.assertTrue(self.build())
        self.assertFalse(self.build())
        self.assertEqual(self.encoder.calls, 1)
        reopened = RagStore(self.root / 'chroma', embeddings=self.encoder)
        trace = {}
        result = reopened.search('chi phí học tập', trace=trace)
        self.assertEqual(result[0]['score'], 1.0)
        self.assertEqual(result[0]['content'], 'Mức thu là 10 triệu đồng.')
        self.assertEqual(result[0]['source_url'], 'https://ptit.edu.vn/fees')
        self.assertEqual(trace['embedding']['dimensions'], 3)

    def test_threshold_filters_every_result(self):
        other = {**self.chunks[0], 'title': 'Thư viện', 'content': 'Đọc sách', 'source_file': 'library.md'}
        self.build([self.chunks[0], other])
        result = self.store.search('học phí', limit=2)
        self.assertEqual(len(result), 1)
        with patch.dict(os.environ, {'RAG_MIN_SCORE': '1.1', 'RETRIEVAL_HYBRID': 'false'}):
            self.assertEqual(self.store.search('học phí'), [])

    def test_hybrid_recovers_full_term_and_acronym_below_vector_threshold(self):
        insurance = {**self.chunks[0], 'title': 'Gia hạn BHYT', 'content': 'Gia hạn thẻ BHYT năm 2026.',
                     'source_url': 'https://ptit.edu.vn/insurance'}
        # Fake encoder ranks insurance orthogonal to queries: lexical must rescue it.
        self.build([insurance])
        with patch.dict(os.environ, {'RAG_MIN_SCORE': '.80', 'RETRIEVAL_HYBRID': 'true'}):
            for query in ['BHYT', 'bảo hiểm y tế', 'bao hiem  y te']:
                trace = {}
                found = self.store.search(query, trace=trace)
                self.assertEqual(len(found), 1)
                self.assertEqual(found[0]['source_url'], insurance['source_url'])
                self.assertEqual(found[0]['score_type'], 'bm25')
                self.assertIn('hybrid_search', trace)

    def test_hybrid_does_not_use_weak_partial_keyword_overlap(self):
        insurance = {**self.chunks[0], 'title': 'BHYT', 'content': 'Thông tin BHYT.'}
        self.build([insurance])
        with patch.dict(os.environ, {'RAG_MIN_SCORE': '.80', 'RETRIEVAL_HYBRID': 'true'}):
            self.assertEqual(self.store.search('bảo hiểm thất nghiệp'), [])

    def test_hybrid_ranks_agreement_and_limits_results(self):
        other = {**self.chunks[0], 'title': 'Khác', 'content': 'Không có thông tin.', 'source_file': 'other.md'}
        self.build([other, self.chunks[0]])
        results = self.store.search('hoc phi', limit=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['source_file'], 'fees.md')

    def test_lexical_mode_shares_alias_and_accent_normalization(self):
        path = self.data / 'insurance.md'
        path.write_text('---\nsource_url: https://ptit.edu.vn/insurance\nfetched_date: 2026-01-01\n'
                        'topic_group: Bảo hiểm\n---\n# BHYT\nGia hạn thẻ BHYT năm 2026.\n', encoding='utf-8')
        with patch.dict(os.environ, {'RETRIEVAL_BACKEND': 'lexical'}):
            knowledge = Knowledge(self.data)
            for query in ['bao hiem  y te', 'BHYT']:
                found = knowledge.retrieve(query)
                self.assertEqual(found[0]['source_file'], 'insurance.md')
                self.assertEqual(found[0]['score_type'], 'bm25')
            self.assertEqual(knowledge.retrieve('cách làm bánh pizza'), [])

    def test_source_requirements_update_and_remove_document(self):
        # T07: edit/add/delete isolated fixtures, never the project's data/.
        self.build()
        path = self.data / 'fees.md'
        path.write_text(path.read_text(encoding='utf-8').replace('10 triệu', '12 triệu'), encoding='utf-8')
        second = self.data / 'fees2.md'
        second.write_text(path.read_text(encoding='utf-8').replace('12 triệu', '15 triệu'), encoding='utf-8')
        updated = Knowledge(self.data).chunks()
        self.assertTrue(self.build(updated))
        results = self.store.search('học phí', limit=4)
        self.assertEqual({s['source_file'] for s in results}, {'fees.md', 'fees2.md'})
        self.assertTrue(all('10 triệu' not in s['content'] for s in results))
        second.unlink()
        remaining = Knowledge(self.data).chunks()
        self.assertTrue(self.build(remaining))
        self.assertFalse(self.build(remaining))
        reopened = RagStore(self.root / 'chroma', embeddings=self.encoder)
        results = reopened.search('học phí', limit=4)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['content'], 'Mức thu là 12 triệu đồng.')

    def test_failed_rebuild_preserves_active_collection(self):
        self.build()
        before = self.store.marker.read_bytes()
        self.encoder.fail = True
        with self.assertRaises(RuntimeError):
            self.build([{**self.chunks[0], 'content': 'NEW_FAIL'}])
        self.assertEqual(before, self.store.marker.read_bytes())
        self.assertEqual(self.store.search('học phí')[0]['score'], 1.0)

    def test_vector_error_falls_back_but_empty_result_does_not(self):
        fake = Mock()
        fake.search.side_effect = RuntimeError('test vector outage')
        knowledge = Knowledge(self.data, rag_store=fake)
        trace = {}
        result = knowledge.retrieve('học phí', trace=trace)
        self.assertTrue(result)
        self.assertEqual(trace['backend_used'], 'lexical')
        self.assertTrue(trace['fallback_reason'])
        fake.search.side_effect = None
        fake.search.return_value = []
        self.assertEqual(knowledge.retrieve('học phí'), [])

    def test_recursive_chunking_preserves_tail_and_metadata(self):
        path = self.data / 'fees.md'
        path.write_text(path.read_text(encoding='utf-8') + ('Nội dung học phí. ' * 500) + 'TAIL_MARKER', encoding='utf-8')
        chunks = Knowledge(self.data).chunks()
        self.assertTrue(all(len(c['content']) <= 400 for c in chunks))
        self.assertIn('TAIL_MARKER', chunks[-1]['content'])
        self.assertTrue(all(c['source_url'] == 'https://ptit.edu.vn/fees' for c in chunks))

    def test_plain_note_colon_is_read_without_modifying_data(self):
        path = self.data / 'fees.md'
        original = path.read_text(encoding='utf-8').replace('topic_group: Học phí', 'topic_group: Học phí\nnote: Giờ tiếp nhận: sáng 8h00, chiều 13h30.')
        path.write_text(original, encoding='utf-8')
        source = Knowledge(self.data).sources()[0]
        self.assertEqual(source['note'], 'Giờ tiếp nhận: sáng 8h00, chiều 13h30.')
        self.assertEqual(path.read_text(encoding='utf-8'), original)

    def test_article_metadata_does_not_leak_between_articles(self):
        path = self.data / 'fees.md'
        front = path.read_text(encoding='utf-8').split('# Học phí')[0]
        articles = []
        for i in (1, 2):
            meta = {'source_url': f'https://ptit.edu.vn/article-{i}', 'publish_date': f'2026-01-0{i}',
                    'title': f'Bài {i}', 'note': f'ghi chú {i}'}
            articles.append('<!-- source_metadata: ' + json.dumps(meta, ensure_ascii=False) + ' -->\n'
                            f'# Bài {i}\nNội dung bài {i}.\n## Điều kiện\nĐiều kiện {i}.')
        path.write_text(front + '\n'.join(articles), encoding='utf-8')
        chunks = Knowledge(self.data).chunks()
        self.assertEqual(len(chunks), 4)
        for chunk in chunks:
            i = 1 if 'Bài 1' in chunk['title'] else 2
            self.assertEqual(chunk['source_url'], f'https://ptit.edu.vn/article-{i}')
            self.assertEqual(chunk['publish_date'], f'2026-01-0{i}')
            self.assertIn(f'ghi chú {i}', chunk['note'])
            self.assertNotIn('source_metadata', chunk['content'])


if __name__ == '__main__':
    unittest.main()
