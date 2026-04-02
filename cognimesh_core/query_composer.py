"""T2 SQL composition from Silver table metadata.

The QueryComposer protocol and TemplateComposer implementation allow
CogniMesh to answer ad-hoc questions that have no pre-built Gold view,
by inspecting Silver table metadata and composing safe, bounded SQL.
"""

from __future__ import annotations

import math
import re
from typing import Protocol, runtime_checkable

from cognimesh_core.config import CogniMeshConfig
from cognimesh_core.models import ComposedQuery


# ------------------------------------------------------------------
# Protocol
# ------------------------------------------------------------------

@runtime_checkable
class QueryComposer(Protocol):
    """Protocol for T2 SQL composition. Pluggable — swap in LLM adapter later."""

    def compose(self, question: str, table_metadata: list[dict]) -> ComposedQuery | None:
        """Compose SQL from a natural language question + table metadata.
        Returns ComposedQuery or None if cannot compose."""
        ...


# ------------------------------------------------------------------
# Constants for intent detection
# ------------------------------------------------------------------

_AGG_KEYWORDS: dict[str, str] = {
    "total": "SUM",
    "sum": "SUM",
    "revenue": "SUM",
    "sales": "SUM",
    "spend": "SUM",
    "average": "AVG",
    "avg": "AVG",
    "mean": "AVG",
    "count": "COUNT",
    "how many": "COUNT",
    "number of": "COUNT",
    "max": "MAX",
    "maximum": "MAX",
    "highest": "MAX",
    "min": "MIN",
    "minimum": "MIN",
    "lowest": "MIN",
}

_TIME_FILTERS: dict[str, str] = {
    "last quarter": "now() - interval '3 months'",
    "last 3 months": "now() - interval '3 months'",
    "last month": "now() - interval '1 month'",
    "last 30 days": "now() - interval '30 days'",
    "last 7 days": "now() - interval '7 days'",
    "last week": "now() - interval '7 days'",
    "last year": "now() - interval '1 year'",
    "last 12 months": "now() - interval '12 months'",
    "last 90 days": "now() - interval '90 days'",
    "last 60 days": "now() - interval '60 days'",
    "this year": "date_trunc('year', now())",
    "this month": "date_trunc('month', now())",
    "this quarter": "date_trunc('quarter', now())",
    "today": "now() - interval '1 day'",
    "yesterday": "now() - interval '2 days'",
}

_SORT_KEYWORDS: dict[str, str] = {
    "top": "DESC",
    "best": "DESC",
    "highest": "DESC",
    "most": "DESC",
    "largest": "DESC",
    "biggest": "DESC",
    "bottom": "ASC",
    "worst": "ASC",
    "lowest": "ASC",
    "least": "ASC",
    "smallest": "ASC",
    "fewest": "ASC",
}

# Columns commonly used as date/time filters
_DATE_COLUMN_HINTS = {"created_at", "updated_at", "order_date", "date", "timestamp", "event_date"}


# ------------------------------------------------------------------
# TemplateComposer
# ------------------------------------------------------------------

class TemplateComposer:
    """Template-based SQL composition using Silver table metadata.

    This is the key CogniMesh differentiator for T2:
    - Has all metadata on Silver tables (column names, types, FK relationships)
    - Can reason about whether a question is answerable
    - Can compose a SQL query, estimate cost, and decide to serve or reject
    - REST has NO equivalent — it just returns 404
    """

    def __init__(self, config: CogniMeshConfig):
        self.config = config
        self._rich_tables: dict = {}  # table_name -> dbook TableMeta (injected via set_rich_metadata)
        self._concepts: dict = {}     # term -> {tables, columns} (injected via set_concepts)

    # ------------------------------------------------------------------
    # Public: dbook metadata injection
    # ------------------------------------------------------------------

    def set_rich_metadata(self, tables: dict) -> None:
        """Inject dbook TableMeta objects for enhanced T2 composition.

        Args:
            tables: dict mapping table_name -> dbook TableMeta objects
        """
        self._rich_tables = tables

    def set_concepts(self, concepts: dict) -> None:
        """Inject dbook concept index for better column matching.

        Args:
            concepts: dict mapping term -> {tables: [...], columns: [...], aliases: [...]}
        """
        self._concepts = concepts

    def compose(self, question: str, table_metadata: list[dict]) -> ComposedQuery | None:
        """Compose SQL from question + metadata.

        Steps:
        1. Tokenize question, extract meaningful keywords
        2. Match keywords against column names across all Silver tables
        3. Identify the best source table(s) based on column coverage
        4. Detect query intent (aggregation, grouping, filtering, sorting, limit)
        5. Compose SQL from template
        6. Estimate row count from column cardinality / table size
        7. Return ComposedQuery with confidence score
        """
        if not table_metadata:
            return None

        # Organize metadata by table
        tables = self._organize_metadata(table_metadata)
        if not tables:
            return None

        # Tokenize question
        tokens = self._tokenize(question)
        if not tokens:
            return None

        # Match tokens to columns and score tables
        table_scores = self._score_tables(tokens, tables)
        if not table_scores:
            return None

        # Pick the best table
        best_table, match_info = max(table_scores.items(), key=lambda x: x[1]["score"])
        matched_columns = match_info["matched_columns"]
        total_tokens = match_info["total_meaningful_tokens"]

        # Confidence based on match ratio
        if total_tokens == 0:
            return None
        match_ratio = len(matched_columns) / total_tokens
        confidence = self._compute_confidence(match_ratio, matched_columns)
        if confidence < 0.3:
            return None

        # Detect intent
        intent = self._detect_intent(question, tokens, tables[best_table])

        # Compose SQL
        schema = tables[best_table]["schema"]
        qualified_table = f"{schema}.{best_table}"
        sql, params = self._compose_sql(qualified_table, tables[best_table], matched_columns, intent)

        # Estimate rows
        estimated_rows = self._estimate_rows(tables[best_table], intent)

        # Estimate cost (simple model: base 20 + rows * 0.001)
        estimated_cost = 20.0 + (estimated_rows * 0.001)

        return ComposedQuery(
            sql=sql,
            params=params,
            estimated_rows=estimated_rows,
            estimated_cost_units=estimated_cost,
            source_tables=[qualified_table],
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Internal: Metadata organization
    # ------------------------------------------------------------------

    def _organize_metadata(self, table_metadata: list[dict]) -> dict[str, dict]:
        """Organize flat metadata rows into a per-table structure.

        Returns:
            {table_name: {schema, columns: [{name, type, ordinal}], column_names: set}}

        When dbook rich metadata is available (via set_rich_metadata), each
        table entry is enriched with foreign_keys, enum_values, row_count,
        and primary_key.
        """
        tables: dict[str, dict] = {}
        for row in table_metadata:
            tname = row["table_name"]
            if tname not in tables:
                tables[tname] = {
                    "schema": row["table_schema"],
                    "columns": [],
                    "column_names": set(),
                }
            tables[tname]["columns"].append({
                "name": row["column_name"],
                "type": row["data_type"],
                "ordinal": row["ordinal_position"],
            })
            tables[tname]["column_names"].add(row["column_name"])

        # Enrich with dbook rich metadata when available
        if self._rich_tables:
            for tname, tinfo in tables.items():
                rich_table = self._rich_tables.get(tname)
                if rich_table is None:
                    continue

                # Foreign keys
                fk_list = []
                for fk in getattr(rich_table, "foreign_keys", []):
                    fk_list.append({
                        "columns": getattr(fk, "columns", []),
                        "referred_table": getattr(fk, "referred_table", ""),
                        "referred_columns": getattr(fk, "referred_columns", []),
                    })
                tinfo["foreign_keys"] = fk_list

                # Enum values
                tinfo["enum_values"] = dict(getattr(rich_table, "enum_values", {}))

                # Row count
                tinfo["row_count"] = getattr(rich_table, "row_count", None)

                # Primary key
                tinfo["primary_key"] = getattr(rich_table, "primary_key", None)

        return tables

    # ------------------------------------------------------------------
    # Internal: Tokenization
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(question: str) -> list[str]:
        """Tokenize question into meaningful lowercase words.

        Strips stop words and punctuation.
        """
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "shall", "should", "may", "might", "must", "can",
            "could", "of", "in", "to", "for", "with", "on", "at", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "out", "off", "over", "under", "again",
            "further", "then", "once", "here", "there", "when", "where",
            "why", "how", "all", "each", "every", "both", "few", "more",
            "most", "other", "some", "such", "no", "nor", "not", "only",
            "own", "same", "so", "than", "too", "very", "just", "because",
            "but", "and", "or", "if", "while", "about", "against",
            "that", "this", "what", "which", "who", "whom", "its", "it",
            "i", "me", "my", "we", "our", "you", "your", "he", "him",
            "his", "she", "her", "they", "them", "their", "show", "give",
            "tell", "list", "get", "find", "display", "return",
        }
        # Remove punctuation, lowercase, split
        cleaned = re.sub(r"[^\w\s]", " ", question.lower())
        tokens = cleaned.split()
        return [t for t in tokens if t not in stop_words and len(t) > 1]

    # ------------------------------------------------------------------
    # Internal: Table scoring
    # ------------------------------------------------------------------

    def _score_tables(
        self, tokens: list[str], tables: dict[str, dict]
    ) -> dict[str, dict]:
        """Score each table by how many question tokens match its columns.

        Uses fuzzy matching: token "revenue" matches column "revenue_30d",
        token "region" matches column "customer_region".

        When dbook concepts are available (via set_concepts), applies an
        IDF-weighted concept boost to tables whose columns overlap with
        concept-mapped columns.
        """
        results: dict[str, dict] = {}

        for tname, tinfo in tables.items():
            col_names = tinfo["column_names"]
            matched: dict[str, str] = {}  # token -> matched column

            for token in tokens:
                # Exact match
                if token in col_names:
                    matched[token] = token
                    continue

                # Fuzzy: token is a substring of column name
                for col in col_names:
                    if token in col or col in token:
                        matched[token] = col
                        break

                # Fuzzy: token matches table name itself
                if token not in matched and (token in tname or tname in token):
                    matched[token] = f"__table__{tname}"

            if matched:
                results[tname] = {
                    "score": len(matched),
                    "matched_columns": matched,
                    "total_meaningful_tokens": len(tokens),
                }

        # Concept boost (IDF-weighted)
        if self._concepts:
            for token in tokens:
                if token in self._concepts:
                    concept = self._concepts[token]
                    concept_tables = concept.get("tables", [])
                    concept_columns = concept.get("columns", [])
                    # IDF: less boost if concept maps to many tables
                    idf_weight = 1.0 / max(len(concept_tables), 1)
                    for table_name, table_info in tables.items():
                        col_names = table_info.get("column_names", set())
                        overlap = sum(
                            1 for col in concept_columns
                            if any(c in col for c in col_names)
                        )
                        if overlap > 0:
                            bonus = overlap * 0.15 * idf_weight
                            if table_name in results:
                                results[table_name]["score"] = (
                                    results[table_name].get("score", 0) + bonus
                                )
                            else:
                                # Concept match creates a new entry for this table
                                results[table_name] = {
                                    "score": bonus,
                                    "matched_columns": {},
                                    "total_meaningful_tokens": len(tokens),
                                }

        return results

    # ------------------------------------------------------------------
    # Internal: Confidence
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_confidence(match_ratio: float, matched_columns: dict) -> float:
        """Compute confidence score from match ratio."""
        # Filter out table-name-only matches for column confidence
        col_matches = [v for v in matched_columns.values() if not v.startswith("__table__")]

        if match_ratio >= 0.8 and len(col_matches) >= 2:
            return 0.9
        elif match_ratio >= 0.6 and len(col_matches) >= 1:
            return 0.7
        elif match_ratio >= 0.4 and len(col_matches) >= 1:
            return 0.5
        elif len(col_matches) >= 1:
            return 0.3
        else:
            return 0.1  # Only table name matched, not enough

    # ------------------------------------------------------------------
    # Internal: Intent detection
    # ------------------------------------------------------------------

    def _detect_intent(
        self,
        question: str,
        tokens: list[str],
        table_info: dict,
    ) -> dict:
        """Detect query intent: aggregation, grouping, filtering, sorting, limit.

        Returns dict with keys: agg_func, agg_column, group_by, where_clauses,
                                 order_dir, limit.
        """
        q_lower = question.lower()
        col_names = table_info["column_names"]
        columns = table_info["columns"]

        intent: dict = {
            "agg_func": None,
            "agg_column": None,
            "group_by": [],
            "where_clauses": [],
            "where_params": [],
            "order_dir": "DESC",
            "limit": 100,
        }

        # --- Aggregation ---
        for keyword, func in _AGG_KEYWORDS.items():
            if keyword in q_lower:
                intent["agg_func"] = func
                # Try to find the value column for aggregation
                # Look for numeric columns that match nearby tokens
                agg_col = self._find_agg_column(keyword, tokens, columns)
                if agg_col:
                    intent["agg_column"] = agg_col
                break

        # --- Grouping: "by {field}" pattern ---
        by_match = re.findall(r"\bby\s+(\w+)", q_lower)
        for field_token in by_match:
            matched_col = self._fuzzy_match_column(field_token, col_names)
            if matched_col:
                intent["group_by"].append(matched_col)

        # Also detect "per {field}"
        per_match = re.findall(r"\bper\s+(\w+)", q_lower)
        for field_token in per_match:
            matched_col = self._fuzzy_match_column(field_token, col_names)
            if matched_col and matched_col not in intent["group_by"]:
                intent["group_by"].append(matched_col)

        # --- Time filtering ---
        date_col = self._find_date_column(columns)
        for time_phrase, time_expr in _TIME_FILTERS.items():
            if time_phrase in q_lower and date_col:
                intent["where_clauses"].append(f"{date_col} >= {time_expr}")
                break

        # --- Value filtering: "category {value}" or "{column} {value}" ---
        table_enums = table_info.get("enum_values", {})
        for col_info in columns:
            col = col_info["name"]
            # Look for pattern: column_name followed by a value
            pattern = rf"\b{re.escape(col)}\s+['\"]?(\w+)['\"]?"
            val_match = re.search(pattern, q_lower)
            if val_match:
                filter_value = val_match.group(1)
                # Don't treat aggregation keywords or stop words as values
                if filter_value not in _AGG_KEYWORDS and len(filter_value) > 1:
                    # If we have enum values for this column, validate/correct
                    if col in table_enums:
                        known_values = table_enums[col]
                        # Try exact match first (case-insensitive)
                        matched_enum = next(
                            (v for v in known_values if v.lower() == filter_value.lower()),
                            None,
                        )
                        if matched_enum:
                            filter_value = matched_enum  # Use correctly-cased value
                        else:
                            # Try fuzzy: partial match
                            matched_enum = next(
                                (v for v in known_values if filter_value.lower() in v.lower()),
                                None,
                            )
                            if matched_enum:
                                filter_value = matched_enum

                    intent["where_clauses"].append(f"{col} = %s")
                    intent["where_params"].append(filter_value)

        # --- Sorting ---
        for keyword, direction in _SORT_KEYWORDS.items():
            if keyword in q_lower:
                intent["order_dir"] = direction
                break

        # --- Limit ---
        limit_match = re.search(r"\btop\s+(\d+)\b", q_lower)
        if limit_match:
            intent["limit"] = min(int(limit_match.group(1)), 10000)
        else:
            limit_match = re.search(r"\bfirst\s+(\d+)\b", q_lower)
            if limit_match:
                intent["limit"] = min(int(limit_match.group(1)), 10000)
            else:
                limit_match = re.search(r"\blimit\s+(\d+)\b", q_lower)
                if limit_match:
                    intent["limit"] = min(int(limit_match.group(1)), 10000)

        return intent

    # ------------------------------------------------------------------
    # Internal: SQL composition
    # ------------------------------------------------------------------

    def _compose_sql(
        self,
        qualified_table: str,
        table_info: dict,
        matched_columns: dict[str, str],
        intent: dict,
    ) -> tuple[str, list]:
        """Compose a SQL query from the detected intent and matched columns.

        Returns (sql, params) where params are bind values for %s placeholders.
        """
        agg_func = intent["agg_func"]
        agg_column = intent["agg_column"]
        group_by = intent["group_by"]
        where_clauses = intent["where_clauses"]
        where_params: list = intent.get("where_params", [])
        order_dir = intent["order_dir"]
        limit = intent["limit"]

        # Resolve actual column names from matched_columns
        real_columns = [
            v for v in matched_columns.values()
            if not v.startswith("__table__")
        ]

        # Build SELECT clause
        if agg_func and agg_column:
            if group_by:
                group_cols_str = ", ".join(group_by)
                if agg_func == "COUNT":
                    select = f"{group_cols_str}, {agg_func}(*) AS agg_result"
                else:
                    select = f"{group_cols_str}, {agg_func}({agg_column}) AS agg_result"
            else:
                if agg_func == "COUNT":
                    select = f"{agg_func}(*) AS agg_result"
                else:
                    select = f"{agg_func}({agg_column}) AS agg_result"
        elif agg_func and not agg_column:
            # Aggregation detected but no specific column — use COUNT(*)
            if group_by:
                group_cols_str = ", ".join(group_by)
                select = f"{group_cols_str}, COUNT(*) AS agg_result"
            else:
                select = "COUNT(*) AS agg_result"
        elif group_by:
            # Group by without explicit aggregation — count per group
            group_cols_str = ", ".join(group_by)
            select = f"{group_cols_str}, COUNT(*) AS cnt"
        else:
            # No aggregation — select matched columns or all
            if real_columns:
                select = ", ".join(sorted(set(real_columns)))
            else:
                select = "*"

        # Build WHERE clause
        where = ""
        if where_clauses:
            where = " WHERE " + " AND ".join(where_clauses)

        # Build GROUP BY clause
        group_sql = ""
        if group_by and (agg_func or not real_columns):
            group_sql = " GROUP BY " + ", ".join(group_by)

        # Build ORDER BY clause
        if agg_func or (group_by and not real_columns):
            order_col = "agg_result" if agg_func else "cnt"
            order_sql = f" ORDER BY {order_col} {order_dir}"
        elif real_columns:
            order_sql = f" ORDER BY {real_columns[0]} {order_dir}"
        else:
            order_sql = ""

        # Build LIMIT
        limit_sql = f" LIMIT {limit}"

        sql = f"SELECT {select} FROM {qualified_table}{where}{group_sql}{order_sql}{limit_sql}"  # noqa: S608 — constructed from trusted metadata, not user input
        return sql, where_params

    # ------------------------------------------------------------------
    # Internal: Row estimation
    # ------------------------------------------------------------------

    def _estimate_rows(self, table_info: dict, intent: dict) -> int:
        """Estimate result row count based on intent.

        When dbook provides actual row_count, uses it for better estimation.
        Otherwise falls back to heuristics:
        - Pure aggregation without GROUP BY: 1 row
        - GROUP BY with N groups: estimate N (default 10-50)
        - With WHERE filter: reduce by ~10x
        - With LIMIT: cap at limit value
        - No aggregation on large table: could be many rows
        """
        limit = intent.get("limit", 100)

        # If dbook provides actual row count, use it for better estimation
        actual_count = table_info.get("row_count")
        if actual_count is not None:
            if intent.get("agg_func") in ("COUNT", "SUM", "AVG", "MAX", "MIN"):
                return 1  # scalar aggregation
            if intent.get("group_by"):
                # Estimate groups as sqrt of total rows, capped
                return min(int(math.sqrt(actual_count)), intent.get("limit", 100))
            if intent.get("limit"):
                return min(intent["limit"], actual_count)
            return min(actual_count, self.config.t2_max_rows)

        if intent["agg_func"] and not intent["group_by"]:
            # Scalar aggregation — always 1 row
            return 1

        if intent["group_by"]:
            # Estimate group count — heuristic: 5-50 groups
            # If the group column name suggests low cardinality, use lower estimate
            group_col = intent["group_by"][0]
            if any(hint in group_col for hint in ("region", "category", "type", "status", "country")):
                estimated = 10
            else:
                estimated = 50
            # WHERE clauses reduce further
            if intent["where_clauses"]:
                estimated = max(1, estimated // 2)
            return min(estimated, limit)

        # No aggregation — estimate based on limit and filters
        if intent["where_clauses"]:
            # Filtered query — estimate smaller result set
            return min(1000, limit)

        # Unfiltered select — could return many rows
        return limit

    # ------------------------------------------------------------------
    # Internal: Helper methods
    # ------------------------------------------------------------------

    def _find_agg_column(
        self, agg_keyword: str, tokens: list[str], columns: list[dict]
    ) -> str | None:
        """Find the best column to aggregate on.

        Looks for numeric columns that match tokens near the aggregation keyword.
        Falls back to first numeric column.
        """
        numeric_types = {"integer", "bigint", "numeric", "real", "double precision", "smallint"}
        numeric_cols = [c for c in columns if c["type"] in numeric_types]

        if not numeric_cols:
            return None

        # Try to match aggregation keyword itself to a column name
        # e.g., "revenue" -> "revenue_30d"
        for col in numeric_cols:
            if agg_keyword in col["name"] or col["name"] in agg_keyword:
                return col["name"]

        # Try to match other tokens to numeric columns
        for token in tokens:
            for col in numeric_cols:
                if token in col["name"] or col["name"] in token:
                    return col["name"]

        # Fall back to first numeric column
        return numeric_cols[0]["name"]

    @staticmethod
    def _fuzzy_match_column(token: str, col_names: set[str]) -> str | None:
        """Fuzzy-match a token against column names."""
        # Exact match
        if token in col_names:
            return token

        # Token is substring of column name
        for col in col_names:
            if token in col:
                return col

        # Column name is substring of token
        for col in col_names:
            if col in token:
                return col

        return None

    @staticmethod
    def _find_date_column(columns: list[dict]) -> str | None:
        """Find the best date/timestamp column for time filtering."""
        date_types = {
            "timestamp without time zone",
            "timestamp with time zone",
            "date",
        }
        # Prefer well-known date column names
        for col in columns:
            if col["type"] in date_types and col["name"] in _DATE_COLUMN_HINTS:
                return col["name"]
        # Fall back to any date column
        for col in columns:
            if col["type"] in date_types:
                return col["name"]
        return None
