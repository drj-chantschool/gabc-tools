"""
Pure GABC parsing, transposition, and text-cleaning utilities.

Everything in this module operates on in-memory GABC text or a row-like
dict (``gbrow``) — it has no database access. Callers that load chant rows
from the ``liturgio`` database (e.g. ``liturgio_tools.gregobase.load_chants``)
construct :class:`GBChant` instances from the rows they fetch.
"""
import functools
import json
import re
from typing import List, NamedTuple

from unidecode import unidecode


class SyllableData(NamedTuple):
    text: str           # syllable text
    neume_raw: str      # transposed neume string (modifiers intact)
    pitches: tuple      # just the [a-m] pitch letters after transposition
    is_boundary: bool   # True if this is a phrase boundary (;,:,::,,)


def compose2(f, g):
    return lambda *a, **kw: f(g(*a, **kw))


def compose(*fs):
    return functools.reduce(compose2, fs)


class GRENeumeCleaner:
    @staticmethod
    def dedup(mystr: str) -> str:
        return ''.join(x for x, y in zip(mystr, ' ' + mystr[:-1]) if x != y)

    @staticmethod
    def strip_special_horiz_episemae(s: str):
        return re.sub(r'\[[^]]*\]', '', s)

    @staticmethod
    def strip_positioning_numbers(s: str):
        return re.sub(r'([._])\d+', r'\g<1>', s)

    @staticmethod
    def strip_epizemae(s: str):
        return s.replace('_', '').replace("'", '')

    @staticmethod
    def split_long_neumes(s: str):
        return re.sub('/', ' ', s)

    @staticmethod
    def dedup_spaces(s: str):
        return re.sub(r'\s+', ' ', s)

    def makeFiltFunc(self, funcs: list):
        if len(funcs):
            func = funcs.pop(0)
            return lambda x: func(self.makeFiltFunc(funcs)(x))
        else:
            return lambda x: x


class GRETextCleaner:

    def __init__(self, method='h'):
        if method == 'h':
            self.filter = compose(
                unidecode, self._fix_spaces, self._fix_caps, self._strip_specs, self._strip_braces, self._strip_html, self._strip_colons
            )

    @staticmethod
    def _strip_colons(mystr):
        return re.sub(r':', '', mystr)

    @staticmethod
    def _strip_html(mystr):
        return re.sub(r'<[^>]*>', '', mystr)

    @staticmethod
    def _strip_braces(mystr):
        return re.sub(r'{|}', '', mystr)

    @staticmethod
    def _strip_specs(mystr):
        return re.sub(r'((R|V)/\s*\.?)|\*|(E u o u a e\s*\.?)|~|i\s*j\s*\.?|(\\greheightstar)|\'', '', mystr)

    @staticmethod
    def _fix_spaces(mystr):
        return re.sub(r'^\s*', '', re.sub(r'\s+', ' ', mystr))

    @staticmethod
    def _fix_caps(mystr: str):
        return ' '.join(word[0] + word[1:].lower() for word in mystr.split() if len(word))

    @staticmethod
    def textfilter(s: str):
        return ''.join([i for i in unidecode(s) if i.isalpha() or i.isspace()])


class GREToken:
    ...


class GBChant:
    _clefcycle = [5, 1, 4, 0, 3, 6, 2]
    _clefAdder = {
        f'c{y}': x for x, y in enumerate(_clefcycle)
    }
    _gabc: str

    def __init__(self, gbrow):
        self.gbrow = gbrow
        self.mode = gbrow.get('mode')
        self.id = gbrow.get('id')
        self.verses = gbrow.get('tex_verses')
        self.commentary = gbrow.get('commentary')
        self.incipit = gbrow.get('incipit')
        try:
            mygabcobj = json.loads(gbrow['gabc'])
            if isinstance(mygabcobj, str):
                self.gabc = mygabcobj
            else:
                for myattr in mygabcobj:
                    if myattr[0] == 'gabc':
                        self.gabc = myattr[1]
        except:
            self.gabc = (gbrow.get('gabc', '') or '') + (gbrow.get('gabc_verses', '') or '')
        if self.gabc is None:
            raise ValueError('Could not extract gabc:', mygabcobj, type(mygabcobj))

    @staticmethod
    def f_clef_to_c(myneumes: str):
        return re.sub(r'f(\d+)', lambda s: f'c{(int(s.group(1))+2)%7}', myneumes)

    @property
    def text(self):
        return ''.join(x[0] for x in self._gabc)

    @property
    def neumes(self):
        return ' '.join(x[1] for x in self._gabc)

    @property
    def neumes_c5(self):
        #return GBChant.f_clef_to_c( self.neumes )
        return 'f3 ' + ''.join(((z + ' ') if len(z) else '') + ''.join(chr(ord(y) + GBChant._clefAdder[x]) if re.match('[A-Ma-m]', y) else y for y in ys) for z, x, ys in
                                re.findall(r'(?:z0(::))?(c\d) ((?:(?!(?:z0::)c\d).)*)', GBChant.f_clef_to_c(self.neumes))
                                )

    @property
    def syllables_c5(self) -> List[SyllableData]:
        """Per-syllable data with pitches transposed to c5 reference."""
        result = []
        active_clef = None
        _BOUNDARY_RE = re.compile(r'[:;,]')
        _PITCH_RE = re.compile(r'[A-Ma-m]')

        for syl_text, neume in self._gabc:
            # Convert f-clefs to c-clefs in this neume
            neume_c = GBChant.f_clef_to_c(neume)

            # Check for clef changes within this neume
            clef_match = re.search(r'(c\d)', neume_c)
            if clef_match:
                active_clef = clef_match.group(1)

            # Skip pure clef entries and empty neumes
            is_boundary = bool(_BOUNDARY_RE.search(neume))
            # Strip clef from neume content for transposition
            neume_content = re.sub(r'c\d\s*', '', neume_c)

            if active_clef is None:
                # No clef seen yet — shouldn't happen in valid GABC but be safe
                active_clef = 'c5'

            adder = GBChant._clefAdder.get(active_clef, 0)

            # Transpose pitch letters and build the raw transposed neume
            transposed = []
            pitches = []
            for ch in neume_content:
                if _PITCH_RE.match(ch):
                    shifted = chr(ord(ch) + adder)
                    transposed.append(shifted)
                    if ch.islower():  # lowercase = actual pitches, uppercase = special
                        pitches.append(shifted)
                else:
                    transposed.append(ch)

            transposed_str = ''.join(transposed)
            result.append(SyllableData(
                text=syl_text,
                neume_raw=transposed_str,
                pitches=tuple(pitches),
                is_boundary=is_boundary,
            ))
        return result

    @property
    def gabc(self):
        return ''.join(f'{x}({y})' for x, y in self._gabc)

    @gabc.setter
    def gabc(self, other: str):
        other = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', other)
        other = other.split('%%')[-1]
        self._gabc = re.findall(r'((?:[^()]|(?:<v>[()]</v>))*)\((.*?)\)', other.strip())
        if self.gabc != other.strip():
            raise EncodingWarning('gabc was not properly parsed', other, self.gabc)


def extract_gabc_body(gabc_raw: str) -> str:
    """
    Extract the GABC body (everything after ``%%``) from a raw ``gabc`` field.

    Handles both JSON-encoded ``gabc`` fields (as stored in
    ``gregobase_chants``, sometimes a JSON string or a list of
    ``[key, value]`` pairs with a ``gabc`` entry) and plain
    ``header\\n%%\\nbody`` text.
    """
    if not gabc_raw:
        return ''
    try:
        obj = json.loads(gabc_raw)
        if isinstance(obj, str):
            gabc_raw = obj
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (list, tuple)) and item[0] == 'gabc':
                    gabc_raw = item[1]
                    break
    except (ValueError, TypeError):
        pass
    parts = gabc_raw.split('%%')
    return parts[-1].strip() if len(parts) > 1 else gabc_raw.strip()


def parse_gabc_header(gabc_text: str) -> dict:
    """Parse the ``key:value;`` header lines of a GABC file into a dict."""
    header_text = gabc_text.split('%%')[0]
    header = {}
    for line in header_text.splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        key, _, value = line.partition(':')
        header[key.strip()] = value.strip().rstrip(';').strip()
    return header


def build_gabc_file(header: dict, body: str) -> str:
    """Build a full GABC file (header + ``%%`` + body) from a header dict and body string."""
    lines = [f'{key}:{value};' for key, value in header.items()]
    return '\n'.join(lines) + '\n%%\n' + body.strip()
