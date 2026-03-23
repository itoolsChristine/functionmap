"""Search and scoring algorithm for function map queries."""
from __future__ import annotations

from typing import Optional


def search_functions(
    functions: list[dict],
    name_index: dict[str, list[int]],
    category_map: dict[str, list[int]],
    *,
    query: Optional[str] = None,
    name: Optional[str] = None,
    category: Optional[str] = None,
    class_name: Optional[str] = None,
    file: Optional[str] = None,
    language: Optional[str] = None,
    kind: Optional[str] = None,
    max_results: int = 20,
) -> list[dict]:
    """Search functions with filtering and relevance scoring.

    Returns list of result dicts sorted by relevance_score descending.
    """
    # Determine candidate set
    if name and not query and not category:
        # Name-focused search: start from name index for speed
        candidates = _candidates_from_name(functions, name_index, name)
    elif category and category in category_map:
        candidates = [(i, functions[i]) for i in category_map[category]]
    else:
        candidates = list(enumerate(functions))

    name_lower = name.lower() if name else None
    query_lower = query.lower() if query else None

    results = []
    for i, fn in candidates:
        # Hard filters
        if language and fn.get("language", "") != language:
            continue
        if kind and fn.get("kind", "") != kind:
            continue
        if class_name:
            fn_class = fn.get("class_name") or ""
            if class_name.lower() not in fn_class.lower():
                continue
        if file:
            fn_file = fn.get("file", "")
            if file.lower() not in fn_file.lower():
                continue
        if category and category in category_map:
            if i not in category_map[category]:
                continue

        # Score
        score = _score_function(fn, name_lower, query_lower)

        # Find this function's category (needed for scoring and output)
        fn_category = ""
        for cat_name, cat_indices in category_map.items():
            if i in cat_indices:
                fn_category = cat_name
                break

        # Boost score if query matches category name
        if query_lower and fn_category and query_lower in fn_category.lower():
            score += 30

        if score <= 0 and (name_lower or query_lower):
            continue  # No match when a search term was given

        # Build compact result
        result = _compact_result(fn, score, i)
        if fn_category:
            result["category"] = fn_category

        results.append(result)

    # Sort by score descending, then by name
    results.sort(key=lambda r: (-r["relevance_score"], r.get("short_name", "")))

    return results[:max_results]


def _candidates_from_name(
    functions: list[dict],
    name_index: dict[str, list[int]],
    name: str,
) -> list[tuple[int, dict]]:
    """Get candidate functions starting from the name index.

    Checks exact match first, then falls back to substring scan.
    """
    name_lower = name.lower()

    # Exact match on short_name
    if name_lower in name_index:
        indices = name_index[name_lower]
        candidates = [(i, functions[i]) for i in indices]
        # Also add prefix/substring matches from full scan
        for i, fn in enumerate(functions):
            if i not in set(indices):
                sn = fn.get("short_name", "").lower()
                full = fn.get("name", "").lower()
                if name_lower in sn or name_lower in full:
                    candidates.append((i, fn))
        return candidates

    # No exact match -- full scan for substring
    candidates = []
    for i, fn in enumerate(functions):
        sn = fn.get("short_name", "").lower()
        full = fn.get("name", "").lower()
        if name_lower in sn or name_lower in full:
            candidates.append((i, fn))
    return candidates


def _score_function(
    fn: dict,
    name_lower: Optional[str],
    query_lower: Optional[str],
) -> float:
    """Score a function against search terms.

    Multi-word queries are split into individual terms. Each term is scored
    independently and the results are summed. This means "email parse" matches
    functions containing "email" OR "parse" in their fields.

    Boosts (public, has summary, has doc) only apply when there's already a
    positive match score, preventing noise from metadata-only scoring.
    """
    match_score = 0.0
    short = fn.get("short_name", "").lower()
    full = fn.get("name", "").lower()
    summary = fn.get("summary", "").lower()
    doc = fn.get("doc", "").lower()
    fn_file = fn.get("file", "").lower()

    if name_lower:
        if short == name_lower:
            match_score += 200
        elif full == name_lower:
            match_score += 180
        elif short.startswith(name_lower):
            match_score += 100
        elif name_lower in short:
            match_score += 60
        elif name_lower in full:
            match_score += 40

    if query_lower:
        # Split multi-word queries and score each term
        terms = query_lower.split()
        for term in terms:
            if short == term:
                match_score += 150
            elif term in short:
                match_score += 80
            if term in summary:
                match_score += 50
            if term in doc:
                match_score += 20
            if term in fn_file:
                match_score += 10

    # Boosts only apply when there's an actual match
    if match_score > 0:
        if fn.get("visibility") == "public":
            match_score += 2
        if fn.get("summary"):
            match_score += 5
        if fn.get("doc"):
            match_score += 3

    # Base score when only filters are active (no name/query)
    if not name_lower and not query_lower:
        match_score = 10

    return match_score


def _compact_result(fn: dict, score: float, index: int) -> dict:
    """Build a compact result dict for a function."""
    result = {
        "name":            fn.get("name", ""),
        "short_name":      fn.get("short_name", ""),
        "kind":            fn.get("kind", ""),
        "language":        fn.get("language", ""),
        "params":          fn.get("params", ""),
        "return_type":     fn.get("return_type", ""),
        "file":            fn.get("file", ""),
        "line_start":      fn.get("line_start", 0),
        "summary":         fn.get("summary", ""),
        "relevance_score": score,
        "_index":          index,
    }
    if fn.get("class_name"):
        result["class_name"] = fn["class_name"]
    if fn.get("visibility"):
        result["visibility"] = fn["visibility"]
    if fn.get("is_static"):
        result["is_static"] = True
    return result
