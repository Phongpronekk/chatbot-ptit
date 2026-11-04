"""Persistent Chroma cosine retrieval, with resumable embedding cache."""
from contextlib import closing
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from threading import Lock
import time
from uuid import uuid4

if __package__:
    from .search_text import KeywordIndex, canonical, normalize_query, terms
else:
    from search_text import KeywordIndex, canonical, normalize_query, terms

import numpy as np
from langchain_core.embeddings import Embeddings

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = 'intfloat/multilingual-e5-small'


def config():
    size, overlap = int(os.getenv('CHUNK_SIZE', '400')), int(os.getenv('CHUNK_OVERLAP', '60'))
    if size <= 0 or not 0 <= overlap < size:
        raise ValueError('Cần CHUNK_SIZE > CHUNK_OVERLAP >= 0')
    return {'model': os.getenv('EMBEDDING_MODEL_NAME', DEFAULT_MODEL),
            'chunk_size': size, 'overlap': overlap, 'version': 2}


def persist_dir():
    path = Path(os.getenv('CHROMA_DIR', str(ROOT / 'BE/chroma_db')))
    return path if path.is_absolute() else ROOT / path


class E5Embeddings(Embeddings):
    """E5-small ONNX int8: same encoder and prefixes for passages and queries."""
    def __init__(self, offline=False):
        self.lock = Lock()
        from fastembed import TextEmbedding
        from fastembed.common.model_description import ModelSource, PoolingType
        if not any(m['model'] == DEFAULT_MODEL for m in TextEmbedding.list_supported_models()):
            TextEmbedding.add_custom_model(model=DEFAULT_MODEL, pooling=PoolingType.MEAN, normalization=True,
                sources=ModelSource(hf='Xenova/multilingual-e5-small'), dim=384,
                model_file='onnx/model_quantized.onnx')
        if not offline:
            import ssl
            import truststore
            import httpx
            from huggingface_hub import set_client_factory
            set_client_factory(lambda: httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT), follow_redirects=True))
        self.model = TextEmbedding(model_name=DEFAULT_MODEL,
            cache_dir=str(ROOT / 'BE/storage/embedding_models'), local_files_only=offline,
            threads=int(os.getenv('EMBEDDING_THREADS', '4')), providers=['CPUExecutionProvider'])

    def embed_documents(self, texts):
        with self.lock:
            return [v.tolist() for v in self.model.passage_embed(['passage: ' + t for t in texts], batch_size=32)]

    def embed_query(self, text):
        with self.lock:
            return next(iter(self.model.query_embed('query: ' + text))).tolist()


def build_embeddings(model_name, offline=False):
    if model_name == DEFAULT_MODEL:
        return E5Embeddings(offline=offline)
    from langchain_huggingface import HuggingFaceEmbeddings
    base = HuggingFaceEmbeddings(model_name=model_name,
        model_kwargs={'local_files_only': offline}, encode_kwargs={'normalize_embeddings': True})
    class Adapter(Embeddings):
        def embed_documents(self, texts):
            if 'vietnamese-bi-encoder' in model_name:
                from pyvi import ViTokenizer
                texts = [ViTokenizer.tokenize(t) for t in texts]
            elif 'e5' in model_name:
                texts = ['passage: ' + t for t in texts]
            return base.embed_documents(texts)
        def embed_query(self, text):
            if 'vietnamese-bi-encoder' in model_name:
                from pyvi import ViTokenizer
                text = ViTokenizer.tokenize(text)
            elif 'e5' in model_name:
                text = 'query: ' + text
            return base.embed_query(text)
    return Adapter()


class RagStore:
    def __init__(self, directory=None, model_name=None, embeddings=None, offline=False):
        import chromadb
        from langchain_chroma import Chroma
        self.persist_dir = Path(directory or persist_dir()).resolve()
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name or config()['model']
        self.embeddings = embeddings or build_embeddings(self.model_name, offline=offline)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir),
            settings=chromadb.Settings(anonymized_telemetry=False))
        self.marker = self.persist_dir / 'manifest.json'
        self.manifest = json.loads(self.marker.read_text(encoding='utf-8')) if self.marker.exists() else None
        self.store = None
        self._keyword_index = None
        self._keyword_lock = Lock()
        if self.manifest and self.manifest['config'] == {**config(), 'model': self.model_name}:
            self.store = Chroma(client=self.client, collection_name=self.manifest['collection'],
                                embedding_function=self.embeddings, create_collection_if_not_exists=False)

    @staticmethod
    def fingerprint(chunks, model_name):
        h = hashlib.sha256(json.dumps({**config(), 'model': model_name}, sort_keys=True).encode())
        for chunk in chunks:
            h.update(json.dumps(chunk, ensure_ascii=False, sort_keys=True).encode())
        return h.hexdigest()

    def ensure_index(self, chunks):
        fingerprint = self.fingerprint(chunks, self.model_name)
        if self.manifest and self.manifest['fingerprint'] == fingerprint and self.store and self.store._collection.count() == len(chunks):
            return False
        if not chunks:
            raise ValueError('Không có chunk để lập chỉ mục')
        # A separate generation keeps the last complete collection available on failure.
        name = 'ptit_' + uuid4().hex
        collection = self.client.create_collection(name, metadata={'hnsw:space': 'cosine'})
        cache = self.persist_dir / 'embedding_cache.sqlite3'
        started = time.monotonic()
        with closing(sqlite3.connect(cache)) as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS embeddings (digest TEXT PRIMARY KEY, vector BLOB NOT NULL)')
            connection.commit()
            for offset in range(0, len(chunks), 128):
                batch = chunks[offset:offset+128]
                passages = [c['title'][:200] + '\n' + c['content'] for c in batch]
                hashes = [hashlib.sha256((json.dumps({**config(), 'model': self.model_name}, sort_keys=True) + '\0' + t).encode()).hexdigest() for t in passages]
                vectors, missing = {}, {}
                for digest, text in zip(hashes, passages):
                    row = connection.execute('SELECT vector FROM embeddings WHERE digest=?', (digest,)).fetchone()
                    if row:
                        vectors[digest] = np.frombuffer(row[0], dtype=np.float32).tolist()
                    else:
                        missing[digest] = text
                if missing:
                    values = self.embeddings.embed_documents(list(missing.values()))
                    for digest, vector in zip(missing, values):
                        vector = np.asarray(vector, dtype=np.float32)
                        vector /= max(float(np.linalg.norm(vector)), 1e-12)
                        vectors[digest] = vector.tolist()
                        connection.execute('INSERT OR REPLACE INTO embeddings VALUES (?,?)', (digest, vector.tobytes()))
                    connection.commit()
                collection.add(ids=[hashlib.sha1(f'{c["source_file"]}|{offset+i}|{c["content"]}'.encode()).hexdigest() for i,c in enumerate(batch)],
                    embeddings=[vectors[d] for d in hashes], documents=passages,
                    metadatas=[{**{k:str(v) for k,v in c.items()}, '_content': c['content']} for c in batch])
                print(f'Indexed {min(offset+128,len(chunks))}/{len(chunks)}; {time.monotonic()-started:.1f}s', flush=True)
        manifest = {'collection': name, 'fingerprint': fingerprint, 'config': {**config(), 'model': self.model_name},
                    'chunk_count': len(chunks), 'document_count': len({c['source_file'] for c in chunks}),
                    'embedding_dimensions': len(vectors[hashes[0]]),
                    'built_at': datetime.now(timezone.utc).isoformat()}
        temporary = self.persist_dir / (name + '.tmp')
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.marker)
        self.manifest = manifest
        from langchain_chroma import Chroma
        self.store = Chroma(client=self.client, collection_name=name, embedding_function=self.embeddings)
        self._keyword_index = None
        return True

    @staticmethod
    def _record_key(metadata):
        return hashlib.sha256(json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def _keywords(self):
        with self._keyword_lock:
            if self._keyword_index is None:
                data = self.store._collection.get(include=['documents', 'metadatas'])
                self._keyword_index = KeywordIndex([
                    {'key': self._record_key(meta), 'text': text, 'metadata': meta}
                    for text, meta in zip(data['documents'], data['metadatas'])])
            return self._keyword_index

    def warm_up(self):
        if self.store is not None and os.getenv('RETRIEVAL_HYBRID', 'true').lower() in ('true', '1', 'yes'):
            self._keywords()

    def search(self, query, limit=4, trace=None):
        if self.store is None:
            raise RuntimeError('Chưa có chỉ mục Chroma phù hợp; chạy python -m BE.scripts.ingest')
        trace = trace if trace is not None else {}
        start = time.perf_counter()
        normalized = normalize_query(query)
        if not terms(normalized):
            trace['query_processing'] = {'original': query, 'normalized': normalized, 'variants': []}
            return []
        expanded = canonical(normalized)
        hybrid = os.getenv('RETRIEVAL_HYBRID', 'true').lower() in ('true', '1', 'yes')
        variants = list(dict.fromkeys([expanded, normalized])) if hybrid else [normalized]
        trace['query_processing'] = {'original': query, 'normalized': normalized,
                                     'canonical': expanded, 'variants': variants}
        vector = self.embeddings.embed_query(variants[0])
        trace['embedding'] = {'model': self.model_name, 'dimensions': len(vector), 'vector_preview': vector[:8],
                              'elapsed_ms': round((time.perf_counter()-start)*1000, 3)}
        start = time.perf_counter()
        pool_size = min(max(limit * 4, 16), self.store._collection.count()) if hybrid else limit
        matches = self.store.similarity_search_by_vector_with_relevance_scores(vector, k=pool_size)
        extra_embedding_ms = 0.
        for variant in variants[1:]:
            embed_start = time.perf_counter()
            extra = self.embeddings.embed_query(variant)
            extra_embedding_ms += (time.perf_counter()-embed_start)*1000
            matches.extend(self.store.similarity_search_by_vector_with_relevance_scores(extra, k=pool_size))
        trace['embedding']['elapsed_ms'] = round(trace['embedding']['elapsed_ms'] + extra_embedding_ms, 3)
        trace['embedding']['variant_count'] = len(variants)
        threshold = float(os.getenv('RAG_MIN_SCORE', '0.35'))
        sources, ranked, candidates = [], [], {}
        for doc, distance in matches:
            similarity = 1 - float(distance)
            ranked.append({'source_file': doc.metadata['source_file'], 'cosine_distance': float(distance),
                           'cosine_similarity': similarity, 'accepted': similarity >= threshold})
            metadata = dict(doc.metadata)
            key = self._record_key(metadata)
            if key not in candidates or similarity > candidates[key]['semantic']:
                candidates[key] = {'metadata': metadata, 'semantic': similarity}
        trace['vector_search'] = {'metric': 'cosine', 'min_score': threshold, 'candidates': ranked,
                                  'acceptance_note': 'Cosine threshold only; hybrid_search contains final decisions when enabled.',
                                  'elapsed_ms': round((time.perf_counter()-start)*1000-extra_embedding_ms, 3)}
        vector_ranks = {key: rank for rank, key in enumerate(
            sorted(candidates, key=lambda k: -candidates[k]['semantic']), 1)}
        keyword_rows = []
        keyword_ranks = {}
        keyword_started = time.perf_counter()
        if hybrid:
            index = self._keywords()
            keyword_rows, _ = index.search(expanded, pool_size)
            for rank, row in enumerate(keyword_rows, 1):
                record = index.records[row['index']]
                candidate = candidates.setdefault(record['key'], {'metadata': record['metadata'], 'semantic': None})
                candidate.update(lexical=row['score'], coverage=row['coverage'], strong=row['strong'])
                keyword_ranks[record['key']] = rank
        query_terms = set(terms(expanded))
        decisions = []
        for key, candidate in candidates.items():
            score = candidate['semantic']
            lexical_ok = hybrid and candidate.get('strong', False)
            # Weak semantic-only matches without any keyword support are prone to
            # false positives. Keep high-confidence semantic paraphrases available.
            overlap = query_terms.intersection(terms(candidate['metadata'].get('title', '') + ' ' + candidate['metadata']['_content']))
            coverage = len(overlap) / max(len(query_terms), 1)
            supported = coverage >= (1. if len(query_terms) <= 5 else .4)
            margin = float(os.getenv('RAG_SEMANTIC_ONLY_MARGIN', '.08'))
            vector_ok = score is not None and score >= threshold and (not hybrid or supported or score >= threshold + margin)
            accepted = vector_ok or lexical_ok
            decisions.append({'source_file': candidate['metadata']['source_file'],
                              'cosine_similarity': score, 'bm25': candidate.get('lexical'),
                              'keyword_coverage': candidate.get('coverage'), 'accepted': accepted})
            if not accepted:
                continue
            # Reciprocal Rank Fusion combines rankings, never incomparable raw scores.
            fusion = sum(1 / (60 + ranks[key]) for ranks in (vector_ranks, keyword_ranks) if key in ranks)
            metadata = dict(candidate['metadata'])
            content = metadata.pop('_content')
            sources.append({**metadata, 'content': content,
                            'score': round(score if vector_ok else candidate['lexical'], 5),
                            'score_type': 'cosine_similarity' if vector_ok else 'bm25',
                            'semantic_score': round(score, 5) if score is not None else None,
                            'lexical_score': round(candidate.get('lexical', 0), 5),
                            'fusion_score': fusion})
        sources.sort(key=lambda s: -s['fusion_score'])
        if hybrid:
            trace['hybrid_search'] = {'strategy': 'BM25 + vector, reciprocal rank fusion',
                'candidate_pool_per_branch': pool_size, 'elapsed_ms': round((time.perf_counter()-keyword_started)*1000, 3),
                'candidates': decisions, 'note': 'RAG_MIN_SCORE applies to cosine; strong keyword matches can also qualify.'}
        return sources[:limit]

    def close(self):
        pass  # Chroma shares its persistent client across collections in the process.
