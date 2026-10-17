"""A provenance-preserving hierarchical library for resonant Markdown corpora.

This is intentionally not a vector database wrapper.  It keeps a document /
section / fragment hierarchy, never merges leaves merely because they are
similar, and records cross-document relations as conditional edges with their
evidence.  The initial encoder is a deterministic lexical fingerprint so that
every decision can be inspected; it can later be replaced by a calibrated
semantic encoder without changing the identity or edge contracts.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import math
import re
from typing import Iterable


_STOPWORDS = frozenset("de la el los las un una y o en para por con que se es al del como no si sobre entre una".split())
_TOKEN = re.compile(r"[\wáéíóúüñ]{3,}", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def fingerprint(text: str) -> Counter[str]:
    return Counter(token.lower() for token in _TOKEN.findall(text) if token.lower() not in _STOPWORDS)


def cosine(left: Counter[str], right: Counter[str]) -> float:
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    if not dot:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / max(left_norm * right_norm, 1e-12)


@dataclass(frozen=True)
class LibraryNode:
    node_id: str
    source_id: str
    section_path: tuple[str, ...]
    ordinal: int
    text: str
    kind: str
    parent_id: str

    @property
    def identity(self) -> str:
        # A section is the parent scope, not the identity of all its leaves.
        # Including the ordinal prevents two paragraphs in one section from
        # being silently treated as one attractor.
        return f"{self.source_id}::{'/'.join(self.section_path)}::fragment:{self.ordinal}"


@dataclass(frozen=True)
class ResonantRelation:
    left: str
    right: str
    kind: str  # bridge | tension
    similarity: float
    evidence_terms: tuple[str, ...]
    contexts: tuple[str, ...]


class HierarchicalResonantLibrary:
    """Finite, inspectable hierarchical memory with conditional bridge edges."""
    def __init__(self) -> None:
        self.nodes: dict[str, LibraryNode] = {}
        self._vectors: dict[str, Counter[str]] = {}
        self.relations: list[ResonantRelation] = []

    def ingest_text(self, source_id: str, text: str) -> list[str]:
        lines = text.splitlines(); path: list[str] = [source_id]; stack: list[tuple[int, str]] = []
        fragments: list[tuple[tuple[str, ...], str, str]] = []
        buffer: list[str] = []

        def flush() -> None:
            cleaned = "\n".join(buffer).strip()
            buffer.clear()
            if len(fingerprint(cleaned)) >= 4:
                kind = "code" if cleaned.startswith("```") else "claim"
                fragments.append((tuple(path), cleaned, kind))

        for line in lines:
            match = _HEADING.match(line)
            if match:
                flush(); level, title = len(match.group(1)), match.group(2)
                while stack and stack[-1][0] >= level: stack.pop()
                stack.append((level, title)); path = [source_id] + [item[1] for item in stack]
                continue
            if not line.strip() and buffer:
                flush()
            else:
                buffer.append(line)
        flush()
        created = []
        for ordinal, (section, fragment, kind) in enumerate(fragments):
            node_id = f"{source_id}:{ordinal}"
            parent_id = f"{source_id}::{'/'.join(section[1:]) or 'root'}"
            node = LibraryNode(node_id, source_id, section, ordinal, fragment, kind, parent_id)
            self.nodes[node_id] = node; self._vectors[node_id] = fingerprint(fragment); created.append(node_id)
        return created

    def ingest_paths(self, paths: Iterable[tuple[str, str]]) -> dict[str, int]:
        counts = {}
        for source_id, path in paths:
            with open(path, "r", encoding="utf8") as handle:
                counts[source_id] = len(self.ingest_text(source_id, handle.read()))
        return counts

    def search(self, query: str, k: int = 5, per_parent: int = 2) -> list[dict]:
        q = fingerprint(query); ranked = sorted(((cosine(q, vector), node_id) for node_id, vector in self._vectors.items()), reverse=True)
        selected, parent_counts = [], Counter()
        for score, node_id in ranked:
            node = self.nodes[node_id]
            if parent_counts[node.parent_id] >= per_parent: continue
            parent_counts[node.parent_id] += 1
            selected.append({"node_id": node_id, "score": score, "source_id": node.source_id,
                             "section_path": list(node.section_path), "identity": node.identity,
                             "preview": " ".join(node.text.split())[:220]})
            if len(selected) == k: break
        return selected

    @staticmethod
    def _tension(left: str, right: str) -> bool:
        # A deliberately narrow, explainable rule: it marks explicit fusion
        # disagreement; broader contradiction belongs to a later symbolic layer.
        left, right = left.lower(), right.lower()
        return (("no debe fusionar" in left and "debe fusionar" in right) or
                ("no debe fusionar" in right and "debe fusionar" in left))

    def form_relations(self, query_contexts: Iterable[str], threshold: float = 0.22, max_edges: int = 150) -> list[ResonantRelation]:
        contexts = list(query_contexts); relations: list[ResonantRelation] = []
        # A bridge is evaluated only after co-activation by a concrete query
        # context.  Besides matching the intended dynamics, this bounds the
        # operation away from an all-pairs similarity sweep over the corpus.
        activated = {context: {hit["node_id"] for hit in self.search(context, k=12, per_parent=1)} for context in contexts}
        ids = sorted(set().union(*activated.values())) if activated else []
        for offset, left_id in enumerate(ids):
            for right_id in ids[offset + 1:]:
                left, right = self.nodes[left_id], self.nodes[right_id]
                if left.source_id == right.source_id: continue
                similarity = cosine(self._vectors[left_id], self._vectors[right_id])
                if similarity < threshold: continue
                shared = tuple(sorted(set(self._vectors[left_id]) & set(self._vectors[right_id]))[:8])
                if len(shared) < 2: continue
                co_contexts = tuple(context for context in contexts
                                    if left_id in activated[context] and right_id in activated[context])
                if not co_contexts: continue
                kind = "tension" if self._tension(left.text, right.text) else "bridge"
                relations.append(ResonantRelation(left_id, right_id, kind, similarity, shared, co_contexts))
        relations.sort(key=lambda edge: (edge.kind != "tension", -edge.similarity, edge.left, edge.right))
        self.relations = relations[:max_edges]
        return self.relations

    def audit(self) -> dict:
        identities = [node.identity for node in self.nodes.values()]
        return {"nodes": len(self.nodes), "unique_identities": len(set(identities)),
                "identity_collisions": len(identities) - len(set(identities)),
                "bridges": sum(edge.kind == "bridge" for edge in self.relations),
                "tensions": sum(edge.kind == "tension" for edge in self.relations),
                "relations": [asdict(edge) for edge in self.relations]}
