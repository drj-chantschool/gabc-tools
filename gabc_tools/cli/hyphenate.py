import os, sys
import re
from pyphen import Pyphen
import argparse

argparser = argparse.ArgumentParser()
argparser.add_argument('--cwd')
argparser.add_argument('--verses')
argparser.add_argument('--gabc')
argparser.add_argument('--out', type=argparse.FileType('w') , default=sys.stdout)
options = argparser.parse_args()
print(options)
cwd = options.cwd

class Hyphenator:
    def __init__(self,*args, **kwargs):
        self.pph = Pyphen(*args, **kwargs)
    def syllables(self, word):
        return self.pph.inserted(word).split('-')

h = Hyphenator(lang='en_EN')

hyph_overrides = {
    'mercy': ['mer','cy']
    ,'awaited':['a','wait','ed']
    ,'blessed':['bles','sed']
    ,'clearly':['clear','ly']
    ,'crafty':['craf','ty']
    ,'creation':['cre','a','tion']
    ,'elderly':['el','der','ly']
    ,'ever':['e','ver']
    ,'trinity':['Tri','ni','ty']
    ,'everlasting':['e','ver','last','ing']
    ,'eternally':['e','ter','nal','ly']
    ,'graciously':['gra','cious','ly']
    ,'guilty':['guil','ty']
    ,'glory':['glo','ry']
    ,'heav\'nly':['heav\'n','ly']
    ,'lowly':['low','ly']
    ,'mary':['ma','ry']
    ,'noble':['no','ble']
    ,'ruler':['ru','ler']
    ,'simeon':['si','me','on']
    ,'singing':['sing','ing']
    ,'temple':['tem','ple']
    ,'upon':['up','on']
    ,'homage':['hom','age']
    ,'holy':['ho','ly']
    ,'forevermore':['for','ev','er','more']
    ,'over':['o','ver']
    ,'avoid':['a','void']
    ,'away':['a','way']
    ,'paraclete':['pa','ra','clete']
    ,'people\'s':['peo','ple\'s']
    ,'prayers': ['prayers']
    ,'prayer': ['prayer']
    ,'predicted':['pre','dict','ed']
    ,'father':['fa','ther']
    ,'eternity':['e','ter','ni','ty']
    ,'coequal':['co','e','qual']
    ,'eternal':['e','ter','nal']
    ,'unity':['u','ni','ty']
    ,'weapons':['wea','pons']
    ,'worthy':['wor','thy']
    ,'humbly':['hum','bly']
    ,'ev\'ry':['ev','\'ry']
}

def filterNeumes( neumes_flat):
    return [ neume for neume in neumes_flat if not
        (re.match( r'\([:;,]+\)' , neume)
        or re.match( r'\([cf][0-9]\)' , neume ))
    ]

def upperThese( mystr:str, idxs, offset = 0):
    buf = ''
    for i,x in enumerate(mystr):
        if i + offset in idxs:
            buf += x.upper()
        else:
            buf += x
    return buf

def hyphenate(line:str):
    hyph = []
    first_word = True
    for word in line.split():
        punct = ''
        if not word[-1].isalpha():
            punct = word[-1]
            word = word[:-1]
        caps = [ x for x,y in enumerate(word) if y==y.upper() ]
        mylen = 0
        syllables = []
        for syl in hyph_overrides.get( word.lower(),
                h.syllables(word.lower())):
            syllables.append( upperThese( syl, caps, mylen ) )
            mylen += len(syl)
        if len(syllables) == 0:
            syllables = [word]
        if not first_word:
            syllables[0] = ' ' + syllables[0]
        syllables[-1] += punct
        hyph = hyph + syllables
        first_word=False
    return hyph

def neume_zip( verse, neumes ):
    if isinstance(verse, list):
        verse = ' '.join(verse)
    syls = hyphenate(verse)

    if re.match('[0-9]', syls[0]): #Add verse number to first "syllable"
        syl = syls.pop(0)
        syls[0] = syl + syls[0]
    buf = ''
    for ix, neume in enumerate( neumes ):
        try:
            if re.match( r'\([:;,]+\)' , neume): #breaths/phrases
                buf += ' ' + neume + '\n'
            elif re.match( r'\([cf][0-9]\)' , neume ): #clef
                buf += neume + ' '
            else:
                buf += syls.pop(0) + neume
        except:
            print( hyphenate(verse) )
            print( ' '.join(neumes ))
            print( ' '*len( ' '.join(neumes) ) + '^' )
            print(buf)
            raise
    return buf

if __name__ == '__main__':

    versesraw = ''
    gabcraw = ''

    if options.gabc:
        with open(options.gabc) as fr:
            gabcraw = fr.read()
    else:
        for f in os.scandir( os.path.join( cwd, '' ) ):
            if re.search( r'\.gabc', f.name ) and not re.search( 'english', f.name ):
                with open(f) as fr:
                    gabcraw = fr.read()
    if options.verses:
        with open(options.verses) as fr:
            versesraw = fr.read()
    else:
        for f in os.scandir( os.path.join( cwd, '' ) ):
            if re.search( r'verses', f.name ):
                with open(f) as fr:
                    versesraw = fr.read()

    if gabcraw == '':
        raise FileNotFoundError('No gabc file found')
    if versesraw=='':
        raise FileNotFoundError('No verses file found')

    verses = [
        [z.strip(' \\') for z in x.split('\n')
            if not z.strip().startswith('%')
            and not z.strip().startswith('\\')]
        for x in versesraw.split('\n\n')]
    #print(verses)

    print(gabcraw.split('%%')[0], file=options.out)
    print('%%', file=options.out)

    neumes_flat = re.findall('\(.+?\)', gabcraw.split('%%')[1].split('(::)')[0].strip() + '(::)')
    for verse in verses:
        print( neume_zip( verse, neumes_flat) , file=options.out)

    amen = re.findall('\(.+?\)', gabcraw.split('%%')[1].split('(::)')[-2].strip() + '(::)')
    if len(filterNeumes(amen)) == 2:
        print( neume_zip( ['A','men.'], amen ), file=options.out)
