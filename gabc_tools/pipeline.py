"""
MelodicPipeline: orchestrator for chant melody analysis.

Ties together vocabulary learning, feature extraction, alignment,
and clustering into a single configurable pipeline.

This module has no database access: callers load chants (e.g. via
``liturgio_tools.gregobase.load_chants``) and pass them into
``MelodicPipeline.run(chants=...)``.
"""
from typing import List, Optional, Literal
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
from sklearn.manifold import TSNE

from gabc_tools.gbchant import GBChant, SyllableData
from gabc_tools.melodic_vocab import MelodicVocabulary, BPEVocabulary, FreqPatternVocabulary
from gabc_tools.feature_extraction import FeatureExtractor, FeatureConfig, get_config
from gabc_tools.melodic_alignment import pairwise_distance_matrix


class PipelineResult:
    """Container for pipeline outputs."""
    def __init__(self):
        self.chants: List[GBChant] = []
        self.syllables: List[List[SyllableData]] = []
        self.vocab: Optional[MelodicVocabulary] = None
        self.encoded: Optional[list] = None
        self.features: Optional[np.ndarray] = None
        self.distance_matrix: Optional[np.ndarray] = None
        self.cluster_labels: Optional[np.ndarray] = None
        self.tsne_coords: Optional[np.ndarray] = None


class MelodicPipeline:
    def __init__(
        self,
        office_part: str,
        version: str = '%Solesmes%',
        vocab_method: Literal['bpe', 'freq'] = 'bpe',
        config: Optional[FeatureConfig] = None,
    ):
        self.office_part = office_part
        self.version = version
        self.vocab_method = vocab_method
        self.config = config or get_config(office_part)

    def extract_syllables(self, chants: List[GBChant]) -> List[List[SyllableData]]:
        return [ch.syllables_c5 for ch in chants]

    def learn_vocabulary(
        self, syllables: List[List[SyllableData]]
    ) -> MelodicVocabulary:
        if self.vocab_method == 'bpe':
            vocab = BPEVocabulary()
        else:
            vocab = FreqPatternVocabulary()
        vocab.fit(syllables, vocab_size=self.config.vocab_size)
        return vocab

    def extract_features(
        self,
        syllables: List[List[SyllableData]],
        vocab: MelodicVocabulary,
    ) -> np.ndarray:
        extractor = FeatureExtractor(vocab, self.config)
        return extractor.fit_transform(syllables)

    def compute_distances(
        self,
        syllables: List[List[SyllableData]],
        vocab: MelodicVocabulary,
        features: np.ndarray,
        top_k: int = 50,
    ) -> np.ndarray:
        encoded = [vocab.encode(s) for s in syllables]
        return pairwise_distance_matrix(encoded, features, vocab, top_k=top_k)

    def cluster(
        self,
        distance_matrix: np.ndarray,
        n_clusters: Optional[int] = None,
        method: str = 'agglomerative',
    ) -> np.ndarray:
        if method == 'agglomerative':
            if n_clusters is None:
                # Auto-select k by silhouette score
                best_k, best_score = 2, -1
                max_k = min(20, len(distance_matrix) - 1)
                for k in range(2, max_k + 1):
                    clust = AgglomerativeClustering(
                        n_clusters=k, metric='precomputed', linkage='average'
                    )
                    labels = clust.fit_predict(distance_matrix)
                    score = silhouette_score(distance_matrix, labels, metric='precomputed')
                    if score > best_score:
                        best_k, best_score = k, score
                n_clusters = best_k
                print(f"Auto-selected {n_clusters} clusters (silhouette={best_score:.3f})")

            clust = AgglomerativeClustering(
                n_clusters=n_clusters, metric='precomputed', linkage='average'
            )
            return clust.fit_predict(distance_matrix)

        elif method == 'hdbscan':
            from sklearn.cluster import HDBSCAN
            clust = HDBSCAN(metric='precomputed', min_cluster_size=3)
            return clust.fit_predict(distance_matrix)

        else:
            raise ValueError(f"Unknown clustering method: {method}")

    def reduce_tsne(self, distance_matrix: np.ndarray) -> np.ndarray:
        tsne = TSNE(n_components=2, metric='precomputed', random_state=42, init='random')
        return tsne.fit_transform(distance_matrix)

    def run(
        self,
        chants: List[GBChant],
        n_clusters: Optional[int] = None,
        cluster_method: str = 'agglomerative',
        alignment_top_k: int = 50,
    ) -> PipelineResult:
        """Execute the full pipeline over a pre-loaded list of chants."""
        result = PipelineResult()
        result.chants = chants

        print(f"Extracting syllables for {len(result.chants)} chants...")
        result.syllables = self.extract_syllables(result.chants)

        print(f"Learning vocabulary ({self.vocab_method}, size={self.config.vocab_size})...")
        result.vocab = self.learn_vocabulary(result.syllables)
        print(f"  Vocabulary size: {result.vocab.size}")

        print("Extracting features...")
        result.features = self.extract_features(result.syllables, result.vocab)
        print(f"  Feature matrix: {result.features.shape}")

        print("Encoding chants...")
        result.encoded = [result.vocab.encode(s) for s in result.syllables]

        print(f"Computing distance matrix (top_k={alignment_top_k})...")
        result.distance_matrix = self.compute_distances(
            result.syllables, result.vocab, result.features, top_k=alignment_top_k
        )

        print(f"Clustering ({cluster_method})...")
        result.cluster_labels = self.cluster(
            result.distance_matrix, n_clusters=n_clusters, method=cluster_method
        )
        n_actual = len(set(result.cluster_labels) - {-1})
        print(f"  Found {n_actual} clusters")

        print("Running t-SNE...")
        result.tsne_coords = self.reduce_tsne(result.distance_matrix)

        return result
