"""
Feature extraction for Gregorian chant melody analysis.

Combines melodic-word TF-IDF features with structural features,
with genre-specific configuration.
"""
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler

from gabc_tools.gbchant import SyllableData, GBChant
from gabc_tools.melodic_vocab import MelodicVocabulary, TokenSeq


@dataclass
class FeatureConfig:
    """Genre-specific feature extraction settings."""
    vocab_size: int = 300
    melodic_weight: float = 1.0       # weight for TF-IDF melodic-word features
    structural_weight: float = 0.3    # weight for structural features
    ngram_range: tuple = (1, 2)       # n-gram range over melodic-word tokens


# Preset configs per office-part
GENRE_CONFIGS = {
    'rb': FeatureConfig(vocab_size=150, melodic_weight=0.7, structural_weight=0.5),
    'gr': FeatureConfig(vocab_size=400, melodic_weight=1.0, structural_weight=0.2),
    'an': FeatureConfig(vocab_size=200, melodic_weight=0.8, structural_weight=0.4),
    'in': FeatureConfig(vocab_size=300, melodic_weight=0.9, structural_weight=0.3),
    'of': FeatureConfig(vocab_size=350, melodic_weight=1.0, structural_weight=0.2),
    'co': FeatureConfig(vocab_size=250, melodic_weight=0.9, structural_weight=0.3),
}


def get_config(office_part: str) -> FeatureConfig:
    return GENRE_CONFIGS.get(office_part, FeatureConfig())


def compute_structural_features(syllables_list: List[List[SyllableData]]) -> np.ndarray:
    """
    Compute structural features for a list of chants.

    Returns an (n_chants, n_features) array with:
    - reciting_tone_ratio: fraction of syllables with a single repeated pitch or single pitch
    - avg_pitches_per_syllable: melismatic density
    - pitch_range: highest - lowest pitch (as ordinal distance)
    - pitch_histogram: distribution across 13 pitch slots (a-m)
    """
    features = []
    for syllables in syllables_list:
        pitched = [s for s in syllables if s.pitches and not s.is_boundary]
        if not pitched:
            features.append(np.zeros(16))
            continue

        # Reciting tone ratio: syllables with 1 pitch or all-same pitches
        reciting = sum(1 for s in pitched if len(set(s.pitches)) <= 1) / len(pitched)

        # Average pitches per syllable
        avg_pitches = np.mean([len(s.pitches) for s in pitched])

        # Collect all pitches for range and histogram
        all_pitches = []
        for s in pitched:
            all_pitches.extend(s.pitches)

        if all_pitches:
            pitch_ords = [ord(p) - ord('a') for p in all_pitches if 'a' <= p <= 'z']
            if pitch_ords:
                pitch_range = max(pitch_ords) - min(pitch_ords)
                # 13-bin histogram (a through m, but allow for transposition overflow)
                hist = np.zeros(13)
                for po in pitch_ords:
                    if 0 <= po < 13:
                        hist[po] += 1
                if hist.sum() > 0:
                    hist = hist / hist.sum()
            else:
                pitch_range = 0
                hist = np.zeros(13)
        else:
            pitch_range = 0
            hist = np.zeros(13)

        feat = np.concatenate([[reciting, avg_pitches, pitch_range], hist])
        features.append(feat)

    return np.array(features)


class FeatureExtractor:
    """
    Extracts combined melodic-word and structural features from chants.
    """

    def __init__(self, vocab: MelodicVocabulary, config: Optional[FeatureConfig] = None):
        self.vocab = vocab
        self.config = config or FeatureConfig()
        self._tfidf = None
        self._scaler = StandardScaler()
        self._fitted = False

    def _tokenize_to_strings(self, syllables: List[SyllableData]) -> str:
        """Convert syllables to a space-separated string of token IDs for TfidfVectorizer."""
        token_ids = self.vocab.encode(syllables)
        return ' '.join(f't{tid}' for tid in token_ids)

    def fit_transform(self, chants_syllables: List[List[SyllableData]]) -> np.ndarray:
        """
        Fit on corpus and return combined feature matrix.

        Returns (n_chants, n_features) dense array.
        """
        # Melodic-word TF-IDF
        token_strings = [self._tokenize_to_strings(s) for s in chants_syllables]
        self._tfidf = TfidfVectorizer(
            ngram_range=self.config.ngram_range,
            token_pattern=r't\d+',
        )
        X_tfidf = self._tfidf.fit_transform(token_strings)

        # Structural features
        X_struct = compute_structural_features(chants_syllables)
        X_struct_scaled = self._scaler.fit_transform(X_struct)

        # Combine with weighting
        X_melodic = X_tfidf.toarray() * self.config.melodic_weight
        X_structural = X_struct_scaled * self.config.structural_weight

        self._fitted = True
        return np.hstack([X_melodic, X_structural])

    def transform(self, chants_syllables: List[List[SyllableData]]) -> np.ndarray:
        """Transform new chants using fitted vocabulary and scaler."""
        if not self._fitted:
            raise RuntimeError("FeatureExtractor not fitted yet.")

        token_strings = [self._tokenize_to_strings(s) for s in chants_syllables]
        X_tfidf = self._tfidf.transform(token_strings)
        X_struct = compute_structural_features(chants_syllables)
        X_struct_scaled = self._scaler.transform(X_struct)

        X_melodic = X_tfidf.toarray() * self.config.melodic_weight
        X_structural = X_struct_scaled * self.config.structural_weight

        return np.hstack([X_melodic, X_structural])
