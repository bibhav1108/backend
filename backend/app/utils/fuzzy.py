from difflib import SequenceMatcher
from typing import List, Tuple

def get_similarity(a: str, b: str) -> float:
    """Returns a similarity score between 0 and 1."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def find_best_matches(query: str, choices: List[str], threshold: float = 0.5, limit: int = 5) -> List[Tuple[str, float]]:
    """
    Finds the best matches for a query from a list of choices.
    Returns a list of (match, score) tuples, sorted by score descending.
    """
    results = []
    for choice in choices:
        score = get_similarity(query, choice)
        if score >= threshold:
            results.append((choice, score))
    
    # Sort by score descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:limit]
