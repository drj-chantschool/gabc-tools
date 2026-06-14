"""
Melodic vocabulary learning for Gregorian chant analysis.

Two approaches behind a common interface:
- BPEVocabulary: Byte-Pair Encoding adapted to pitch-tuple sequences
- FreqPatternVocabulary: Frequent contiguous subsequence mining
"""
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from typing import List, Tuple, Optional
import pickle
import re

from gabc_tools.gbchant import SyllableData

# Type aliases
PitchTuple = tuple  # e.g. ('g', 'h', 'g')
TokenSeq = List[int]  # sequence of token IDs


class MelodicVocabulary(ABC):
    """Base class for melodic vocabulary learners."""

    def __init__(self):
        self.token_to_id: dict[tuple, int] = {}
        self.id_to_token: dict[int, tuple] = {}
        self._fitted = False

    @abstractmethod
    def fit(self, corpus: List[List[SyllableData]], vocab_size: int = 300) -> 'MelodicVocabulary':
        """Learn vocabulary from a corpus of chants (each a list of SyllableData)."""
        ...

    def encode(self, syllables: List[SyllableData]) -> TokenSeq:
        """Encode a chant's syllables into a sequence of token IDs."""
        if not self._fitted:
            raise RuntimeError("Vocabulary not fitted yet. Call fit() first.")
        return self._encode_impl(syllables)

    @abstractmethod
    def _encode_impl(self, syllables: List[SyllableData]) -> TokenSeq:
        ...

    @property
    def vocab(self) -> dict[int, tuple]:
        return dict(self.id_to_token)

    @property
    def size(self) -> int:
        return len(self.token_to_id)

    def _register_token(self, token: tuple) -> int:
        if token not in self.token_to_id:
            tid = len(self.token_to_id)
            self.token_to_id[token] = tid
            self.id_to_token[tid] = token
        return self.token_to_id[token]

    def save(self, path: str):
        with open(path, 'wb') as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str) -> 'MelodicVocabulary':
        with open(path, 'rb') as f:
            return pickle.load(f)

    def token_str(self, tid: int) -> str:
        """Human-readable representation of a token."""
        tok = self.id_to_token[tid]
        # Token is a tuple of pitch letters, possibly with '|' syllable boundaries
        return ''.join(tok)


def _extract_pitch_seqs(corpus: List[List[SyllableData]]) -> List[List[PitchTuple]]:
    """Convert corpus to list of chants, each a list of pitch tuples (skipping boundaries/empty)."""
    result = []
    for chant in corpus:
        seq = []
        for syl in chant:
            if syl.pitches and not syl.is_boundary:
                seq.append(syl.pitches)
            elif syl.is_boundary and seq:
                # Keep boundary as a special marker
                seq.append(('|BOUNDARY|',))
        result.append(seq)
    return result


class BPEVocabulary(MelodicVocabulary):
    """
    Byte-Pair Encoding adapted to pitch-tuple sequences.

    Base tokens are individual syllable pitch-tuples. Merging combines
    adjacent tokens into longer melodic "words".
    """

    def __init__(self):
        super().__init__()
        self.merges: List[Tuple[tuple, tuple]] = []  # ordered merge operations

    def fit(self, corpus: List[List[SyllableData]], vocab_size: int = 300) -> 'BPEVocabulary':
        pitch_seqs = _extract_pitch_seqs(corpus)

        # Step 1: Build initial vocabulary from all unique syllable pitch-tuples
        for chant in pitch_seqs:
            for pt in chant:
                self._register_token(pt)

        # Step 2: Represent each chant as a mutable list of tokens (as tuples)
        # Each "token" is itself a tuple of pitch letters (possibly spanning multiple syllables)
        encoded_corpus = [list(chant) for chant in pitch_seqs]

        # Step 3: Iteratively merge most frequent adjacent pair
        while self.size < vocab_size:
            # Count adjacent pairs
            pair_counts = Counter()
            for chant in encoded_corpus:
                for i in range(len(chant) - 1):
                    a, b = chant[i], chant[i + 1]
                    # Don't merge across boundaries
                    if a == ('|BOUNDARY|',) or b == ('|BOUNDARY|',):
                        continue
                    pair_counts[(a, b)] += 1

            if not pair_counts:
                break

            # Find the most frequent pair
            best_pair, best_count = pair_counts.most_common(1)[0]
            if best_count < 2:
                break  # No pair appears more than once

            # Create merged token
            merged = best_pair[0] + ('|',) + best_pair[1]  # '|' marks syllable boundary within token
            self._register_token(merged)
            self.merges.append(best_pair)

            # Apply merge across corpus
            encoded_corpus = [self._apply_merge(chant, best_pair, merged) for chant in encoded_corpus]

        self._fitted = True
        return self

    @staticmethod
    def _apply_merge(seq: list, pair: tuple, merged: tuple) -> list:
        """Replace all occurrences of pair in seq with merged token."""
        if len(seq) < 2:
            return seq
        result = []
        i = 0
        while i < len(seq):
            if i < len(seq) - 1 and seq[i] == pair[0] and seq[i + 1] == pair[1]:
                result.append(merged)
                i += 2
            else:
                result.append(seq[i])
                i += 1
        return result

    def _encode_impl(self, syllables: List[SyllableData]) -> TokenSeq:
        # Build pitch tuple sequence
        seq = []
        for syl in syllables:
            if syl.pitches and not syl.is_boundary:
                seq.append(syl.pitches)
            elif syl.is_boundary and seq:
                seq.append(('|BOUNDARY|',))

        # Apply merges in order
        for pair in self.merges:
            merged = pair[0] + ('|',) + pair[1]
            seq = self._apply_merge(seq, pair, merged)

        # Convert to token IDs (unknown tokens get registered on-the-fly as base tokens)
        ids = []
        for tok in seq:
            if tok == ('|BOUNDARY|',):
                continue
            if tok in self.token_to_id:
                ids.append(self.token_to_id[tok])
            else:
                # Unseen base token — register it
                ids.append(self._register_token(tok))
        return ids


class FreqPatternVocabulary(MelodicVocabulary):
    """
    Frequent contiguous subsequence mining for melodic vocabulary.

    Finds all contiguous pitch subsequences (spanning 1+ syllables) that
    appear above a frequency threshold, then greedily selects the most
    informative ones for the vocabulary.
    """

    def __init__(self, max_span: int = 6, min_support: int = 3):
        super().__init__()
        self.max_span = max_span    # max number of syllables a pattern can span
        self.min_support = min_support
        self._patterns_by_length: dict[int, list] = {}  # length -> [(pattern, count)]

    def fit(self, corpus: List[List[SyllableData]], vocab_size: int = 300) -> 'FreqPatternVocabulary':
        pitch_seqs = _extract_pitch_seqs(corpus)

        # Step 1: Register all unique single-syllable tokens
        for chant in pitch_seqs:
            for pt in chant:
                if pt != ('|BOUNDARY|',):
                    self._register_token(pt)

        # Step 2: Count all contiguous subsequences of length 2..max_span
        # A subsequence is a tuple of adjacent pitch-tuples joined with '|' boundary markers
        pattern_counts = Counter()
        for chant in pitch_seqs:
            # Split on boundaries to get phrases
            phrases = []
            current_phrase = []
            for pt in chant:
                if pt == ('|BOUNDARY|',):
                    if current_phrase:
                        phrases.append(current_phrase)
                    current_phrase = []
                else:
                    current_phrase.append(pt)
            if current_phrase:
                phrases.append(current_phrase)

            # Extract subsequences within each phrase
            for phrase in phrases:
                for span in range(2, min(self.max_span + 1, len(phrase) + 1)):
                    for start in range(len(phrase) - span + 1):
                        subseq = tuple(phrase[start:start + span])
                        # Flatten into a single token with '|' between syllables
                        flat = subseq[0]
                        for s in subseq[1:]:
                            flat = flat + ('|',) + s
                        pattern_counts[flat] += 1

        # Step 3: Filter by min_support
        frequent = {p: c for p, c in pattern_counts.items() if c >= self.min_support}

        # Step 4: Greedy selection — prioritize by (count * length) to favor
        # patterns that are both frequent and cover more material
        def pattern_score(item):
            pattern, count = item
            n_pitches = sum(1 for x in pattern if x != '|')
            return count * n_pitches

        sorted_patterns = sorted(frequent.items(), key=pattern_score, reverse=True)

        for pattern, count in sorted_patterns:
            if self.size >= vocab_size:
                break
            self._register_token(pattern)

        self._fitted = True
        return self

    def _encode_impl(self, syllables: List[SyllableData]) -> TokenSeq:
        # Build pitch tuple sequence, split on boundaries
        raw_seq = []
        for syl in syllables:
            if syl.pitches and not syl.is_boundary:
                raw_seq.append(syl.pitches)
            elif syl.is_boundary:
                raw_seq.append(None)  # boundary marker

        # Greedy left-to-right longest-match encoding
        ids = []
        i = 0
        while i < len(raw_seq):
            if raw_seq[i] is None:
                i += 1
                continue

            # Try longest match first
            best_len = 1
            best_token = raw_seq[i]  # fallback: single syllable token

            for span in range(min(self.max_span, len(raw_seq) - i), 1, -1):
                # Check no boundaries in this span
                segment = raw_seq[i:i + span]
                if any(s is None for s in segment):
                    continue
                # Build the flattened token
                flat = segment[0]
                for s in segment[1:]:
                    flat = flat + ('|',) + s
                if flat in self.token_to_id:
                    best_len = span
                    best_token = flat
                    break

            if best_token in self.token_to_id:
                ids.append(self.token_to_id[best_token])
            else:
                ids.append(self._register_token(best_token))
            i += best_len

        return ids
