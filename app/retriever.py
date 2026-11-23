"""Hybrid lexical retrieval: BM25 + TF-IDF cosine, merged with reciprocal rank fusion.

Both scorers are cheap, run on CPU and need no model download, so PaperPilot
works offline. BM25 rewards exact term matches; TF-IDF with bigrams catches
phrase overlap. Reciprocal rank fusion (RRF) combines the two rankings without
having to calibrate their very different score scales.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from .chunker import Chunk

TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
RRF_K = 60


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in ENGLISH_STOP_WORDS]


@dataclass
class Hit:
    chunk: Chunk
    score: float  # fused RRF score, higher is better
    bm25: float
    cosine: float


class HybridRetriever:
    def __init__(self, chunks: list[Chunk]):
        if not chunks:
            raise ValueError("Cannot build a retriever over zero chunks")
        self.chunks = chunks
        # Index the section heading with the text, so "limitations" finds the Limitations section.
        docs = [f"{c.section} {c.section} {c.text}" for c in chunks]
        tokenized = [tokenize(d) or ["_empty_"] for d in docs]
        self.bm25 = BM25Okapi(tokenized)
        self.vectorizer = TfidfVectorizer(
            tokenizer=tokenize, lowercase=False, ngram_range=(1, 2), sublinear_tf=True,
            token_pattern=None,
        )
        self.matrix = self.vectorizer.fit_transform(docs)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        bm25_scores = np.asarray(self.bm25.get_scores(q_tokens))
        q_vec = self.vectorizer.transform([query])
        cosine_scores = (self.matrix @ q_vec.T).toarray().ravel()

        fused = np.zeros(len(self.chunks))
        for scores in (bm25_scores, cosine_scores):
            order = np.argsort(-scores)
            for rank, idx in enumerate(order):
                if scores[idx] > 0:
                    fused[idx] += 1.0 / (RRF_K + rank + 1)

        best = [i for i in np.argsort(-fused)[:k] if fused[i] > 0]
        return [
            Hit(
                chunk=self.chunks[i],
                score=float(fused[i]),
                bm25=float(bm25_scores[i]),
                cosine=float(cosine_scores[i]),
            )
            for i in best
        ]
