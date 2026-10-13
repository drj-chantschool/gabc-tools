from gabc_tools.tex_text import tex_to_html, verses_html


def test_pointing_breaks_and_accents():
    h = tex_to_html("2.~Confund\\'antur et re\\textit{vere}{\\bf \\'an}tur, * qui.\\\\\n3.~Avert\\'antur.")
    assert h == ('2.\u00a0Confundántur et re<i>vere</i><b>án</b>tur, * qui.<br> '
                 '3.\u00a0Avertántur.')


def test_blank_line_is_stanza_gap_and_ae_accent():
    h = tex_to_html("\\noindent 5. pr\\'\\ae nites,\\\\\nAmen.\\\\\n\n\\noindent 6. Next")
    assert h == '5. prǽnites,<br> Amen.<span class="tv-gap"></span>6. Next'


def test_red_signs_and_textcolor():
    h = tex_to_html("\\Vbar . Dominus.\\\\\n\\textcolor{red}{Ant.} {\\rb}. Alleluia.")
    assert h == ('<span class="tv-red">℣</span>. Dominus.<br> '
                 '<span class="tv-red">Ant.</span> <span class="tv-red">℟</span>. Alleluia.')


def test_tabular_becomes_table():
    h = tex_to_html("\\begin{tabular}{@{}ll}\n\\hspace*{3mm}A & B\\\\\n\\\\\nC & D\n\\end{tabular}\n\\Rbar.  X")
    assert h == ('<table class="tv-table"><tr><td>&emsp;A</td><td>B</td></tr>'
                 '<tr class="tv-gaprow"><td></td></tr><tr><td>C</td><td>D</td></tr></table>'
                 '<span class="tv-red">℟</span>.  X')


def test_unbalanced_braces_and_escaping():
    h = tex_to_html("\\item 2. Salv\\'avit {\\textbf{d\\'ex}tera <x> & y")
    assert h == '2. Salvávit <b>déx</b>tera &lt;x&gt;   y'


def test_gabc_verses_take_precedence():
    assert verses_html('2. A(g)', '2. text') is None
    assert verses_html(None, '', '2.~text') == '2.\u00a0text'
    assert verses_html(None, None) is None


def test_gap_not_merged_into_red_run():
    h = tex_to_html("\\textcolor{red}{2} A.\n\n\\textcolor{red}{3} B.")
    assert h == ('<span class="tv-red">2</span> A.<span class="tv-gap"></span>'
                 '<span class="tv-red">3</span> B.')
