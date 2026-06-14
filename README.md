# gabc-tools

Pure GABC parsing, transposition, and melodic-similarity analysis for
Gregorian chant. **No database access** — this package operates entirely on
in-memory GABC text and chant objects.

## Contents

- `gabc_tools.gbchant` — `GBChant` (parses a GABC header/body into syllables,
  neumes, and transposed pitches), `SyllableData`, and convenience functions
  `extract_gabc_body()`, `parse_gabc_header()`, `build_gabc_file()` for
  reading/writing `.gabc` files without the full melodic-analysis machinery.
- `gabc_tools.melodic_vocab` — `BPEVocabulary` / `FreqPatternVocabulary` for
  learning a vocabulary of melodic "words" from `SyllableData`.
- `gabc_tools.feature_extraction` — TF-IDF feature extraction over the
  learned vocabulary, with per-genre `FeatureConfig`s.
- `gabc_tools.melodic_alignment` — Needleman-Wunsch alignment + cosine
  similarity for pairwise chant distances.
- `gabc_tools.pipeline` — `MelodicPipeline`, orchestrating vocabulary
  learning, feature extraction, alignment, clustering, and t-SNE over a
  caller-supplied list of `GBChant` objects.
- `gabc_tools.cli.extract_text` — generate `.txt` sidecar files from local
  `.gabc` files.
- `gabc_tools.cli.hyphenate` — hyphenate GABC lyrics syllable-by-syllable.

## Loading chants

This package never opens a database connection. Callers load `GBChant`
objects themselves (e.g. from local `.gabc` files, or via
[`liturgio-tools`](https://github.com/drj-chantschool/liturgio-tools)'s
`liturgio_tools.gregobase.load_chants()` for the `liturgio` database) and
pass them into `MelodicPipeline.run(chants=...)`.

## Install

```
pip install -e .
pip install -e ".[viz]"  # adds bokeh, for visualization examples
```

## Tests

```
pytest
```
