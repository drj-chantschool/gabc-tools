from gabc_tools.gbchant import GBChant, GRETextCleaner
from pathlib import Path
import argparse
import logging

logger=logging.getLogger(__name__)
cleaner=GRETextCleaner().filter

def traverse_dirs( fp:Path, dry_run:bool=True ):
    for cp in fp.iterdir():
        if cp.is_dir():
            traverse_dirs(cp, dry_run)
        elif cp.suffix=='.gabc':
            txt_path = cp.with_suffix('.txt')
            try:
                new_content = cleaner( GBChant({'gabc':cp.read_text(encoding='utf-8')}).text )
            except EncodingWarning as e:
                logger.warning(f'{cp}: could not parse gabc: {e.args[0]}')
                continue
            if txt_path.exists():
                if txt_path.read_text() != new_content:
                    logger.warning(f'{txt_path} exists but differs from generated content')
            elif dry_run:
                print('----------------------------')
                print(cp.read_text())
                print('----------------------------')
                print(txt_path, new_content)
                print('----------------------------')
            else:
                txt_path.write_text(new_content)

def init():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder_path',type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--verbose','-v',action='count')
    args = parser.parse_args()
    if args.verbose == 0:
        logging.basicConfig(level=logging.WARNING)
    elif args.verbose==1:
        logging.basicConfig(level=logging.INFO)
    elif args.verbose==2:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.NOTSET)
    return args

if __name__=='__main__':
    args=init()
    traverse_dirs(args.folder_path, args.dry_run)
