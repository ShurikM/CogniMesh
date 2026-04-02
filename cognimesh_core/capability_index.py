"""Capability Index — in-memory index built from the UC registry.

Provides deterministic keyword matching for the gateway router and
an agent-facing discovery surface.
"""

from __future__ import annotations

from cognimesh_core.models import CapabilityDescriptor, UseCase

# Common English stop words to exclude from keyword matching.
_STOP_WORDS: set[str] = {
    "the", "a", "an", "is", "what", "which", "are", "of", "for", "in",
    "by", "to", "and", "or", "not", "it", "do", "does", "how", "that",
    "this", "with", "from", "on", "at", "be", "has", "have", "was",
    "were", "been", "their", "my", "our", "your", "its", "all", "each",
    "who", "whom", "where", "when", "why", "can", "could", "should",
    "would", "will", "shall", "may", "might", "about", "as", "but",
    "if", "so", "no", "yes", "up", "out", "then", "than",
}


def _tokenize(text: str) -> list[str]:
    """Lower-case split, strip punctuation, remove stop words."""
    tokens: list[str] = []
    for word in text.lower().split():
        cleaned = word.strip("?.,!;:'\"()-")
        if cleaned and cleaned not in _STOP_WORDS:
            tokens.append(cleaned)
    return tokens


class CapabilityIndex:
    """In-memory index of registered Use Cases for discovery and routing."""

    def __init__(self, registry):
        from cognimesh_core.registry import UCRegistry  # avoid circular at module level

        self._registry: UCRegistry = registry
        self._uc_index: dict[str, UseCase] = {}       # UC ID -> UC
        self._field_index: dict[str, list[str]] = {}   # field -> list of gold_views
        self._concepts: dict[str, dict[str, list[str]]] = {}
        self.rebuild()

    # ------------------------------------------------------------------
    # Concept injection
    # ------------------------------------------------------------------

    def set_concepts(self, concepts: dict[str, dict[str, list[str]]]) -> None:
        """Inject dbook concept index for semantic matching boost.

        Args:
            concepts: mapping of term -> {tables: [...], columns: [...], aliases: [...]}
        """
        self._concepts = concepts

    # ------------------------------------------------------------------
    # Index lifecycle
    # ------------------------------------------------------------------

    def rebuild(self) -> None:
        """Rebuild indexes from registry."""
        ucs = self._registry.list_active()
        self._uc_index.clear()
        self._field_index.clear()

        for uc in ucs:
            self._uc_index[uc.id] = uc
            if uc.gold_view:
                for field in uc.required_fields:
                    self._field_index.setdefault(field, [])
                    if uc.gold_view not in self._field_index[field]:
                        self._field_index[field].append(uc.gold_view)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def match_question(self, question: str) -> tuple[UseCase | None, float]:
        """Deterministic keyword matching with optional concept boosting.

        Tokenise the question, match against each UC's question tokens
        plus its required_field names.  When a dbook concept index has
        been injected via :meth:`set_concepts`, an IDF-weighted bonus is
        added for UCs whose required_fields overlap with concept columns.

        Returns (best_match, confidence).
        """
        if not self._uc_index:
            self.rebuild()

        q_tokens = _tokenize(question)
        if not q_tokens:
            return None, 0.0

        # Phase 1: keyword overlap scoring (per-UC)
        uc_scores: dict[str, float] = {}
        for uc_id, uc in self._uc_index.items():
            uc_tokens = set(_tokenize(uc.question))
            # Also match against field name parts (e.g. "customer_id" -> {"customer", "id"})
            for field in uc.required_fields:
                for part in field.split("_"):
                    cleaned = part.strip().lower()
                    if cleaned and cleaned not in _STOP_WORDS:
                        uc_tokens.add(cleaned)

            matched = sum(1 for t in q_tokens if t in uc_tokens)
            uc_scores[uc_id] = matched / len(q_tokens) if q_tokens else 0.0

        # Phase 2: concept boost (IDF-weighted) — only when concepts available
        if self._concepts:
            for token in q_tokens:
                if token in self._concepts:
                    concept = self._concepts[token]
                    concept_columns = concept.get("columns", [])
                    n_tables = max(len(concept.get("tables", [])), 1)
                    idf_weight = 1.0 / n_tables  # inverse document frequency

                    for uc_id, uc in self._uc_index.items():
                        # Check if UC's required_fields overlap with concept columns
                        overlap = sum(
                            1 for field in uc.required_fields
                            if any(field in col for col in concept_columns)
                        )
                        if overlap > 0:
                            bonus = overlap * 0.1 * idf_weight
                            uc_scores[uc_id] = uc_scores.get(uc_id, 0.0) + bonus

        # Pick best
        if not uc_scores:
            return None, 0.0

        best_uc_id = max(uc_scores, key=uc_scores.get)  # type: ignore[arg-type]
        best_score = min(uc_scores[best_uc_id], 1.0)  # cap at 1.0

        if best_score > 0:
            return self._uc_index[best_uc_id], best_score
        return None, 0.0

    def match_by_id(self, uc_id: str) -> UseCase | None:
        """Direct UC lookup by ID."""
        return self._uc_index.get(uc_id)

    # ------------------------------------------------------------------
    # Field-level discovery (T1 prep)
    # ------------------------------------------------------------------

    def find_fields(self, field_names: list[str]) -> dict[str, list[str]]:
        """For T1: find which Gold views contain which fields."""
        result: dict[str, list[str]] = {}
        for name in field_names:
            result[name] = self._field_index.get(name, [])
        return result

    # ------------------------------------------------------------------
    # Agent-facing discovery
    # ------------------------------------------------------------------

    def discover(self, agent_id: str | None = None) -> list[CapabilityDescriptor]:
        """Return active UCs as CapabilityDescriptors.

        If *agent_id* is provided, only UCs the agent is allowed to access
        are returned.  UCs with ``allowed_agents=None`` are open to everyone.
        """
        descriptors: list[CapabilityDescriptor] = []
        for uc in self._uc_index.values():
            if agent_id and uc.allowed_agents and agent_id not in uc.allowed_agents:
                continue
            descriptors.append(
                CapabilityDescriptor(
                    uc_id=uc.id,
                    question=uc.question,
                    parameters=uc.required_fields,
                    freshness_guarantee_seconds=uc.freshness_ttl_seconds,
                    access_pattern=uc.access_pattern,
                    available_fields=uc.required_fields,
                )
            )
        return descriptors
