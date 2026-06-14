from pathlib import Path

from gabc_tools.gbchant import GBChant, extract_gabc_body, parse_gabc_header, build_gabc_file

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
