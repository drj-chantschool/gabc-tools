"""
Render GregoBase ``tex_verses`` (LaTeX text set below the score) as HTML.

GregoBase's chant_img.php typesets ``tex_verses`` with LuaLaTeX under the
engraved first verse. This is a small, forgiving interpreter for the subset of
LaTeX that actually occurs in that column: line breaks (``\\\\``, ``\\newline``,
``\\item``, blank lines), bold/italic in both forms (``\\textbf{..}`` and
``{\\bf ..}``), red text, accents (``\\'a``, ``\\'{\\ae}``), ℣/℟ macros, ``†``,
and ``tabular``/``longtable`` (two-column hymn stanzas). Layout-only commands
(``\\hspace``, ``\\setlength``, ``\\noindent``...) are dropped. Unbalanced
braces, which exist in the data, are closed at the end instead of failing.

The output is plain inline HTML (``<b>``, ``<i>``, ``<span class="tv-red">``,
``<br>``, ``<span class="tv-gap">``, ``<table class="tv-table">``) with every
text run escaped, so it is safe to assign to ``innerHTML``.
"""
from __future__ import annotations

import html
import re
import unicodedata

__all__ = ['tex_to_html', 'verses_html']

# Control symbols / words that just produce a character.
_CHARS = {
    'ae': 'æ', 'AE': 'Æ', 'oe': 'œ', 'OE': 'Œ', 'dag': '†', 'ddag': '‡',
    'ss': 'ß', 'textdagger': '†', 'S': '§', 'P': '¶', 'ldots': '…', 'dots': '…',
    'textasciitilde': '~', 'textbackslash': '\\', 'quad': '\u2003', 'qquad': '\u2003\u2003',
    ' ': ' ', ',': '\u2009', ';': ' ', ':': ' ', '!': '', '/': '', '-': '',
    '&': '&', '%': '%', '$': '$', '#': '#', '_': '_', '{': '{', '}': '}',
    'hfill': ' ', 'hfil': ' ', 'enspace': '\u2002', 'thinspace': '\u2009',
}
# Signs GregoBase typesets in red.
_RED_CHARS = {'Vbar': '℣', 'Rbar': '℟', 'rb': '℟', 'vb': '℣', 'GreVBar': '℣', 'GreRBar': '℟'}
_ACCENTS = {"'": '\u0301', '`': '\u0300', '"': '\u0308', '^': '\u0302', '~': '\u0303',
            '=': '\u0304', 'u': '\u0306', 'v': '\u030C', 'c': '\u0327'}
# Font switches that last to the end of the enclosing group.
_SWITCHES = {'bf': ('b', True), 'bfseries': ('b', True), 'it': ('i', True), 'itshape': ('i', True),
             'em': ('i', True), 'sl': ('i', True), 'rm': (None, None), 'normalfont': (None, None),
             'upshape': ('i', False), 'mdseries': ('b', False)}
# Commands with one argument rendered in a changed style.
_STYLED = {'textbf': ('b', True), 'textit': ('i', True), 'emph': ('i', True), 'textsl': ('i', True),
           'textrm': (None, None), 'textnormal': (None, None), 'textup': ('i', False),
           'textsc': None, 'mbox': None, 'hbox': None, 'text': None, 'frot': None,
           'underline': None, 'textsuperscript': None}
# Commands to drop together with this many arguments.
_DROP = {'hspace': 1, 'vspace': 1, 'setlength': 2, 'addtolength': 2, 'setcounter': 2,
         'hyphenation': 1, 'label': 1, 'phantom': 1, 'hphantom': 1, 'vphantom': 1,
         'parindent': 0, 'parskip': 0, 'noindent': 0, 'indent': 0, 'centering': 0,
         'raggedright': 0, 'raggedleft': 0, 'small': 0, 'footnotesize': 0, 'normalsize': 0,
         'large': 0, 'Large': 0, 'scriptsize': 0, 'relax': 0, 'nobreak': 0, 'hline': 0,
         'smallskip': 0, 'medskip': 0, 'bigskip': 0, 'linebreak': 0, 'nolinebreak': 0,
         'pagebreak': 0, 'nopagebreak': 0, 'selectfont': 0}
_TABLE_ENVS = {'tabular', 'tabular*', 'longtable', 'tabularx', 'array'}
_BR, _PAR = '\x01', '\x02'


# ── Parsing ───────────────────────────────────────────────────────────────────
class _Group(list):
    pass


class _Env:
    def __init__(self, name, body):
        self.name, self.body = name, body


def _tokenize(src: str) -> list:
    """Tokens: ('t', text) | ('c', name) | '{' | '}' | '$' | '&' | ('p',)."""
    toks, i, n = [], 0, len(src)
    while i < n:
        ch = src[i]
        if ch == '\\':
            if i + 1 >= n:
                break
            nx = src[i + 1]
            if nx.isascii() and nx.isalpha():
                j = i + 1
                while j < n and src[j].isascii() and src[j].isalpha():
                    j += 1
                name = src[i + 1:j]
                if j < n and src[j] == '*':        # \hspace*, \\* etc.
                    j += 1
                while j < n and src[j] in ' \t':   # TeX eats spaces after a control word
                    j += 1
                toks.append(('c', name))
                i = j
            else:
                name, i = nx, i + 2
                if name == '\\':
                    if i < n and src[i] == '*':
                        i += 1
                    m = re.match(r'\s*\[[^\]]*\]', src[i:])   # \\[4pt]
                    if m:
                        i += m.end()
                toks.append(('c', name))
        elif ch in '{}$&':
            toks.append(ch)
            i += 1
        elif ch == '%':
            j = src.find('\n', i)
            i = n if j < 0 else j + 1
        elif ch == '\n':
            j = i
            while j < n and src[j] in ' \t\r\n':
                j += 1
            toks.append(('p',) if src.count('\n', i, j) > 1 else ('t', ' '))
            i = j
        else:
            j = i
            while j < n and src[j] not in '\\{}$&%\n':
                j += 1
            toks.append(('t', src[i:j]))
            i = j
    return toks


def _parse(toks: list) -> list:
    """Nest tokens into _Group (braces / math) and _Env (begin..end) nodes."""
    root: list = []
    stack = [(root, None)]                 # (children, closer)
    i = 0
    while i < len(toks):
        tk = toks[i]
        cur, closer = stack[-1]
        if tk == '{':
            g = _Group()
            cur.append(g)
            stack.append((g, '}'))
        elif tk == '}':
            if closer == '}':
                stack.pop()
            # stray '}' outside any group: ignore
        elif tk == '$':
            if closer == '$':
                stack.pop()
            else:
                g = _Group()
                cur.append(g)
                stack.append((g, '$'))
        elif tk == ('c', 'begin') and i + 3 < len(toks) and toks[i + 1] == '{' and toks[i + 3] == '}':
            name = toks[i + 2][1] if toks[i + 2][0] == 't' else ''
            env = _Env(name.strip(), [])
            cur.append(env)
            stack.append((env.body, ('end', env.name)))
            i += 3
        elif tk == ('c', 'end') and i + 3 < len(toks) and toks[i + 1] == '{' and toks[i + 3] == '}':
            name = toks[i + 2][1].strip() if toks[i + 2][0] == 't' else ''
            # close up to (and including) the matching env; tolerate unclosed groups
            for k in range(len(stack) - 1, 0, -1):
                if stack[k][1] == ('end', name):
                    del stack[k:]
                    break
            i += 3
        else:
            cur.append(tk)
        i += 1
    return root


# ── Rendering ─────────────────────────────────────────────────────────────────
def _wrap(text: str, st: dict) -> str:
    out = html.escape(text, quote=False)
    if st.get('i'):
        out = f'<i>{out}</i>'
    if st.get('b'):
        out = f'<b>{out}</b>'
    if st.get('red'):
        out = f'<span class="tv-red">{out}</span>'
    return out


def _plain(node) -> str:
    """Flatten a node to its literal text (for env names, colour names...)."""
    if isinstance(node, _Group):
        return ''.join(_plain(n) for n in node)
    if isinstance(node, tuple) and node[0] == 't':
        return node[1]
    return ''


def _apply(st: dict, key, val) -> dict:
    st = dict(st)
    if key is None:
        st['b'] = st['i'] = False
    else:
        st[key] = val
    return st


class _Renderer:
    def __init__(self, nodes):
        self.nodes, self.i = nodes, 0

    def _next_arg(self):
        """Consume the next argument: a group, or a single non-blank token."""
        while self.i < len(self.nodes):
            nd = self.nodes[self.i]
            self.i += 1
            if isinstance(nd, tuple) and nd[0] == 't' and not nd[1].strip():
                continue
            return nd
        return None

    def _skip_optional(self):
        if self.i < len(self.nodes):
            nd = self.nodes[self.i]
            if isinstance(nd, tuple) and nd[0] == 't' and nd[1].startswith('['):
                rest = nd[1][nd[1].find(']') + 1:] if ']' in nd[1] else ''
                self.nodes[self.i] = ('t', rest)

    def _accent(self, mark: str, st: dict) -> str:
        nd = self._next_arg()
        if nd is None:
            return ''
        if isinstance(nd, _Group):
            base = _Renderer(list(nd)).render_plain_first()
            rest = ''
        elif isinstance(nd, tuple) and nd[0] == 'c':
            base, rest = ('i' if nd[1] == 'i' else _CHARS.get(nd[1], '')), ''
        elif isinstance(nd, tuple) and nd[0] == 't':
            base, rest = nd[1][:1], nd[1][1:]
        else:
            return ''
        return _wrap(unicodedata.normalize('NFC', base + mark), st) + (_wrap(rest, st) if rest else '')

    def render_plain_first(self) -> str:
        for nd in self.nodes:
            if isinstance(nd, tuple) and nd[0] == 't' and nd[1]:
                return nd[1]
            if isinstance(nd, tuple) and nd[0] == 'c' and nd[1] in _CHARS:
                return _CHARS[nd[1]]
            if nd == ('c', 'i'):
                return 'i'
        return ''

    def render(self, st: dict) -> str:
        out = []
        while self.i < len(self.nodes):
            nd = self.nodes[self.i]
            self.i += 1
            if isinstance(nd, _Group):
                out.append(_Renderer(list(nd)).render(st))
            elif isinstance(nd, _Env):
                out.append(_render_env(nd, st))
            elif nd == '&':
                out.append(' ')
            elif nd[0] == 't':
                out.append(_wrap(nd[1].replace('~', '\u00a0'), st))
            elif nd[0] == 'p':
                out.append(_PAR)
            else:
                out.append(self._command(nd[1], st))
                if nd[1] in _SWITCHES:
                    st = _apply(st, *_SWITCHES[nd[1]])
                elif nd[1] == 'color':
                    st = dict(st, red='red' in _plain(self._next_arg() or ('t', '')))
        return ''.join(out)

    def _command(self, name: str, st: dict) -> str:
        if name in ('\\', 'newline', 'cr', 'tabularnewline'):
            self._skip_optional()
            return _BR
        if name == 'par':
            return _PAR
        if name == 'item':
            self._skip_optional()
            return _BR
        if name in _ACCENTS:
            return self._accent(_ACCENTS[name], st)
        if name in _CHARS:
            return _wrap(_CHARS[name], st)
        if name in _RED_CHARS:
            return _wrap(_RED_CHARS[name], dict(st, red=True))
        if name == 'i':
            return _wrap('ı', st)
        if name in _STYLED:
            arg = self._next_arg()
            mod = _STYLED[name]
            st2 = _apply(st, *mod) if mod else st
            return _render_node(arg, st2)
        if name == 'textcolor':
            colour = _plain(self._next_arg() or ('t', ''))
            return _render_node(self._next_arg(), dict(st, red='red' in colour))
        if name == 'hspace':
            arg = _plain(self._next_arg() or ('t', ''))
            return '&emsp;' if arg.strip() and not arg.strip().startswith('-') else ''
        if name in _DROP:
            for _ in range(_DROP[name]):
                self._next_arg()
            return ''
        return ''   # unknown command: LaTeX would error and drop it too


def _render_node(nd, st: dict) -> str:
    if nd is None:
        return ''
    if isinstance(nd, _Group):
        return _Renderer(list(nd)).render(st)
    return _Renderer([nd]).render(st)


def _render_env(env: _Env, st: dict) -> str:
    if env.name not in _TABLE_ENVS:
        return _Renderer(list(env.body)).render(st)
    body = list(env.body)
    # drop the column spec (and tabular*'s width) — leading group argument(s)
    nskip = 2 if env.name in ('tabular*', 'tabularx') else 1
    while body and nskip:
        nd = body.pop(0)
        if isinstance(nd, _Group):
            nskip -= 1
    rows, row, cell = [], [], []
    for nd in body:
        if nd == '&':
            row.append(cell)
            cell = []
        elif isinstance(nd, tuple) and nd[0] == 'c' and nd[1] in ('\\', 'tabularnewline'):
            row.append(cell)
            rows.append(row)
            row, cell = [], []
        else:
            cell.append(nd)
    if any(_plain_cell(c) for c in cell) or row:
        row.append(cell)
        rows.append(row)
    trs = []
    for r in rows:
        tds = [_finish(_Renderer(c).render(st)) for c in r]
        if not any(tds):
            trs.append('<tr class="tv-gaprow"><td></td></tr>')
        else:
            trs.append('<tr>' + ''.join(f'<td>{td}</td>' for td in tds) + '</tr>')
    return f'{_PAR}<table class="tv-table">{"".join(trs)}</table>{_PAR}'


def _plain_cell(cell) -> bool:
    return any(not (isinstance(n, tuple) and n[0] == 't' and not n[1].strip()) for n in cell)


def _finish(s: str) -> str:
    """Turn line markers into HTML: one break -> <br>, a blank line -> stanza gap."""
    s = s.strip(_BR + _PAR + ' \u00a0')

    def runs(m):
        r = m.group(0)
        return '<span class="tv-gap"></span>' if _PAR in r or r.count(_BR) > 1 else '<br>'
    s = re.sub(rf'[{_BR}{_PAR}](?:[ \u00a0]*[{_BR}{_PAR}])*', runs, s)
    s = s.replace('<table', '\x03').replace('</table>', '\x04')
    # no breaks hugging a table
    s = re.sub(r'(<br>|<span class="tv-gap"></span>)*\x03', '\x03', s)
    s = re.sub(r'\x04(\s|<br>|<span class="tv-gap"></span>)*', '\x04', s)
    # merge adjacent runs of the same style: <b>d</b><b>é</b> -> <b>dé</b>
    s = s.replace('</b><b>', '').replace('</i><i>', '')
    s = re.sub(r'(?<!<span class="tv-gap">)</span><span class="tv-red">', '', s)
    return s.replace('\x03', '<table').replace('\x04', '</table>').strip()


def tex_to_html(tex: str | None) -> str | None:
    """Convert a ``tex_verses`` value to inline HTML; None for empty input."""
    if not tex or not tex.strip():
        return None
    tex = tex.replace('\ufeff', '').replace('\r\n', '\n')
    nodes = _parse(_tokenize(tex))
    out = _finish(_Renderer(nodes).render({'b': False, 'i': False, 'red': False}))
    return out or None


def verses_html(gabc_verses: str | None, tex_verses: str | None,
                tex_verses_pdf: str | None = None) -> str | None:
    """
    The text-verse block GregoBase would set under the score, as HTML.

    GregoBase renders ``gabc_verses`` (as notation) in preference to
    ``tex_verses``, so a chant with both gets no text block. ``tex_verses_pdf``
    (our reconstruction, see liturgio_tools.gregobase_sync.tex_verses_pdf)
    stands in when the real TeX is missing.
    """
    if gabc_verses and gabc_verses.strip():
        return None
    return tex_to_html(tex_verses if tex_verses and tex_verses.strip() else tex_verses_pdf)
