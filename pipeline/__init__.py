"""pipeline – normalise, dedupe, classify, and safety-filter feed items."""
from .classifier import classify
from .dedupe import DedupeDB, canonical_id, slugify, similarity
from .normalizer import normalize
from .safety_filter import check as safety_check

__all__ = [
    "classify",
    "DedupeDB",
    "canonical_id",
    "slugify",
    "similarity",
    "normalize",
    "safety_check",
]
