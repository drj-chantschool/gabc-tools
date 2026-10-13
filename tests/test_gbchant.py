import json
from pathlib import Path

from gabc_tools.gbchant import (
    GBChant, build_gabc_file, extract_gabc_body, gabc_elements, parse_gabc_header,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'ky--kyrie_iv--solesmes.1.gabc'


def test_gbchant_round_trips_body():
    raw = FIXTURE.read_text(encoding='utf-8')
    chant = GBChant({'gabc': raw})

    body = raw.split('%%', 1)[1].strip()
    assert chant.gabc == body


def test_syllables_c5_transposed_pitches():
    raw = FIXTURE.read_text(encoding='utf-8')
    chant = GBChant({'gabc': raw})

    syllables = chant.syllables_c5
    assert len(syllables) > 0
    assert any(s.pitches for s in syllables)
    assert any(s.is_boundary for s in syllables)


def test_extract_gabc_body_matches_gbchant():
    raw = FIXTURE.read_text(encoding='utf-8')
    chant = GBChant({'gabc': raw})

    assert extract_gabc_body(raw) == chant.gabc


def test_parse_and_build_gabc_header_round_trip():
    raw = FIXTURE.read_text(encoding='utf-8')
    header = parse_gabc_header(raw)

    assert header['name'] == 'Kyrie IV'
    assert header['office-part'] == 'Kyriale'
    assert header['mode'] == '1'

    rebuilt = build_gabc_file(header, extract_gabc_body(raw))
    assert parse_gabc_header(rebuilt) == header
    assert extract_gabc_body(rebuilt) == extract_gabc_body(raw)


MULTIPART = json.dumps([
    ['tex', r'\grechangedim{linepunctummorashift}{-0.02 cm}{scalable}', {}],
    ['gabc', 'name:x;\n%%\n(c4) A(f)men.(f) (::)'],
    ['tex', r'\vspace{1em}{\it Rubric}', {}],
    ['gabc', '(c4) Ky(f)ri(g)e.(f) (::)'],
])


def test_extract_gabc_body_joins_every_gabc_element():
    assert extract_gabc_body(MULTIPART) == '(c4) A(f)men.(f) (::)\n(c4) Ky(f)ri(g)e.(f) (::)'
    assert [k for k, _ in gabc_elements(MULTIPART)] == ['tex', 'gabc', 'tex', 'gabc']


def test_gbchant_and_extract_agree_on_multipart():
    assert GBChant({'gabc': MULTIPART}).gabc == extract_gabc_body(MULTIPART)


def test_json_string_and_plain_forms_agree():
    body = '(c4) A(f)men.(f) (::)'
    assert extract_gabc_body(json.dumps(body)) == extract_gabc_body(body) == body


def test_gabc_verses_only_when_asked():
    raw, verses = '(c4) Ve(f)ni.(f) (::)', '2. Qui(f) (::)\n'
    chant = GBChant({'gabc': raw, 'gabc_verses': verses})
    assert chant.gabc == extract_gabc_body(raw) == raw
    assert chant.full_gabc() == extract_gabc_body(raw, verses) == raw + '\n2. Qui(f) (::)'
