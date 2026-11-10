"""Stage only site assets and split downloads that exceed the host's file limit."""

import hashlib
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'exam-studio-local'))
from excel_cases import EXCEL_CASE_FILES

SOURCE = HERE.parent / 'exam-studio-preview'
OUTPUT = HERE / 'assets.generated'
PAGE_FILES = ('index.html', 'style.css', 'app.js', 'sessions.js', 'questions.js')
DATA_FILES = ('NYC_Film_Permits.xlsx', 'songs.db', 'Chinook_Sqlite.sqlite',
              'movies.db', 'pcards.db', *EXCEL_CASE_FILES)
ASSET_LIMIT = 25 * 1024 * 1024
PART_SIZE = 20 * 1024 * 1024


def main():
    (OUTPUT / 'files').mkdir(parents=True, exist_ok=True)
    (OUTPUT / '_dataset_parts').mkdir(exist_ok=True)
    expected = set()
    for filename in PAGE_FILES:
        shutil.copyfile(SOURCE / filename, OUTPUT / filename)
        expected.add(filename)

    manifest = {}
    for filename in DATA_FILES:
        source = SOURCE / 'files' / filename
        size = source.stat().st_size
        if size <= ASSET_LIMIT:
            shutil.copyfile(source, OUTPUT / 'files' / filename)
            expected.add('files/' + filename)
            continue

        parts = []
        digest = hashlib.sha256()
        with source.open('rb') as data:
            while chunk := data.read(PART_SIZE):
                path = f'_dataset_parts/{filename}.{len(parts):02}.part'
                (OUTPUT / path).write_bytes(chunk)
                expected.add(path)
                digest.update(chunk)
                parts.append({'path': '/' + path, 'bytes': len(chunk)})
        if sum(part['bytes'] for part in parts) != size:
            raise ValueError(f'{filename} changed during staging.')
        manifest[filename] = {'bytes': size, 'sha256': digest.hexdigest(), 'parts': parts}

    actual = {path.relative_to(OUTPUT).as_posix() for path in OUTPUT.rglob('*') if path.is_file()}
    if actual != expected:
        raise ValueError(f'Unexpected files in staged assets: {sorted(actual - expected)}')
    if any((OUTPUT / path).stat().st_size > ASSET_LIMIT for path in actual):
        raise ValueError('A staged asset exceeds the per-file size limit.')
    (HERE / 'downloads.generated.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Staged {len(actual)} assets, including {len(manifest)} split downloads.')


if __name__ == '__main__':
    main()
