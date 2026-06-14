from pathlib import Path

from gabc_tools.gbchant import GBChant
from gabc_tools.pipeline import MelodicPipeline

FIXTURE = Path(__file__).parent / 'fixtures' / 'ky--kyrie_iv--solesmes.1.gabc'


def test_pipeline_runs_on_in_memory_chants():
    """MelodicPipeline.run() operates purely on caller-supplied chants, no DB access."""
    raw = FIXTURE.read_text(encoding='utf-8')
    chants = [
        GBChant({'gabc': raw, 'incipit': f'Kyrie {i}', 'id': i, 'mode': '1'})
        for i in range(35)
    ]

    pipeline = MelodicPipeline('ky', vocab_method='freq')
    result = pipeline.run(chants, n_clusters=3, alignment_top_k=5)

    assert len(result.chants) == 35
    assert len(result.syllables) == 35
    assert result.features.shape[0] == 35
    assert result.distance_matrix.shape == (35, 35)
    assert len(result.cluster_labels) == 35
    assert result.tsne_coords.shape == (35, 2)
