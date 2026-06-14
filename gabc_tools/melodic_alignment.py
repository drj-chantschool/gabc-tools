"""
Alignment-based similarity for Gregorian chant melodies.

Two-tier approach:
1. Fast cosine similarity on TF-IDF feature vectors (pre-filter)
2. Needleman-Wunsch global alignment on melodic-word token sequences (precise)
"""
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Optional

from gabc_tools.melodic_vocab import MelodicVocabulary, TokenSeq


def _token_edit_distance(vocab: MelodicVocabulary, tid_a: int, tid_b: int) -> float:
    """
    Pitch-level edit distance between two melodic-word tokens, normalized to [0,1].
    Used to score substitutions in NW alignment.
    """
    tok_a = vocab.id_to_token[tid_a]
    tok_b = vocab.id_to_token[tid_b]
    # Extract just pitch letters (skip '|' boundary markers)
    pitches_a = [p for p in tok_a if p != '|' and p != '|BOUNDARY|']
    pitches_b = [p for p in tok_b if p != '|' and p != '|BOUNDARY|']

    if not pitches_a and not pitches_b:
        return 0.0

    # Standard Levenshtein on pitch letters
    m, n = len(pitches_a), len(pitches_b)
    dp = np.zeros((m + 1, n + 1), dtype=int)
    for i in range(m + 1):
        dp[i, 0] = i
    for j in range(n + 1):
        dp[0, j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if pitches_a[i - 1] == pitches_b[j - 1] else 1
            dp[i, j] = min(dp[i - 1, j] + 1, dp[i, j - 1] + 1, dp[i - 1, j - 1] + cost)

    return dp[m, n] / max(m, n)


def _is_reciting_tone_token(vocab: MelodicVocabulary, tid: int) -> bool:
    """Check if a token is a simple reciting-tone token (1 unique pitch)."""
    tok = vocab.id_to_token[tid]
    pitches = [p for p in tok if p != '|' and p != '|BOUNDARY|']
    return len(set(pitches)) <= 1


def needleman_wunsch(
    seq_a: TokenSeq,
    seq_b: TokenSeq,
    vocab: MelodicVocabulary,
    match_score: float = 2.0,
    gap_penalty_reciting: float = -0.5,
    gap_penalty_melismatic: float = -1.5,
) -> float:
    """
    Needleman-Wunsch global alignment of two melodic-word token sequences.

    Returns normalized alignment score in [0, 1] (higher = more similar).
    """
    m, n = len(seq_a), len(seq_b)
    if m == 0 and n == 0:
        return 1.0
    if m == 0 or n == 0:
        return 0.0

    # Build scoring matrix
    dp = np.full((m + 1, n + 1), -np.inf)
    dp[0, 0] = 0.0

    # Initialize gap rows/columns
    for i in range(1, m + 1):
        gp = gap_penalty_reciting if _is_reciting_tone_token(vocab, seq_a[i - 1]) else gap_penalty_melismatic
        dp[i, 0] = dp[i - 1, 0] + gp
    for j in range(1, n + 1):
        gp = gap_penalty_reciting if _is_reciting_tone_token(vocab, seq_b[j - 1]) else gap_penalty_melismatic
        dp[0, j] = dp[0, j - 1] + gp

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            # Match/substitution
            if seq_a[i - 1] == seq_b[j - 1]:
                sub_score = match_score
            else:
                edit_dist = _token_edit_distance(vocab, seq_a[i - 1], seq_b[j - 1])
                sub_score = match_score * (1.0 - edit_dist) - edit_dist

            diag = dp[i - 1, j - 1] + sub_score

            # Gap in seq_b (inserting from seq_a)
            gp_a = gap_penalty_reciting if _is_reciting_tone_token(vocab, seq_a[i - 1]) else gap_penalty_melismatic
            up = dp[i - 1, j] + gp_a

            # Gap in seq_a (inserting from seq_b)
            gp_b = gap_penalty_reciting if _is_reciting_tone_token(vocab, seq_b[j - 1]) else gap_penalty_melismatic
            left = dp[i, j - 1] + gp_b

            dp[i, j] = max(diag, up, left)

    # Normalize: perfect match of shorter sequence would score match_score * min(m,n)
    max_possible = match_score * min(m, n)
    if max_possible <= 0:
        return 0.0
    return max(0.0, min(1.0, dp[m, n] / max_possible))


def pairwise_distance_matrix(
    encoded_chants: List[TokenSeq],
    feature_matrix: np.ndarray,
    vocab: MelodicVocabulary,
    top_k: int = 50,
) -> np.ndarray:
    """
    Two-tier pairwise distance matrix.

    Tier 1: Cosine similarity on feature vectors to find top-k candidates.
    Tier 2: NW alignment for precise distance among candidates.

    Returns an (n, n) distance matrix (0 = identical, 1 = maximally different).
    """
    n = len(encoded_chants)
    top_k = min(top_k, n - 1)

    # Tier 1: cosine similarity
    cos_sim = cosine_similarity(feature_matrix)

    # Initialize distance matrix with cosine-based distances
    dist = 1.0 - cos_sim
    np.fill_diagonal(dist, 0.0)

    # Tier 2: NW alignment for top-k most similar pairs per chant
    for i in range(n):
        # Find top-k neighbors by cosine similarity (excluding self)
        neighbors = np.argsort(cos_sim[i])[::-1]
        neighbors = [j for j in neighbors if j != i][:top_k]

        for j in neighbors:
            if i < j:  # only compute once per pair
                nw_score = needleman_wunsch(encoded_chants[i], encoded_chants[j], vocab)
                nw_dist = 1.0 - nw_score
                # Use the NW distance (more precise) for these pairs
                dist[i, j] = nw_dist
                dist[j, i] = nw_dist

    # Ensure symmetry and non-negativity
    dist = (dist + dist.T) / 2
    np.fill_diagonal(dist, 0.0)
    dist = np.maximum(dist, 0.0)

    return dist
