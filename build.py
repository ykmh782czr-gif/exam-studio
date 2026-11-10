"""Build the app using a local copy of the course's materials directory."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
LOCAL = ROOT / 'exam-studio-local'
PUBLIC = ROOT / 'exam-studio-preview'
sys.path.insert(0, str(LOCAL))

from excel_cases import workbook_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('materials', type=Path, help='Path to the original course materials folder')
    args = parser.parse_args()
    materials = args.materials.expanduser().resolve()
    film = materials / '1. Excel Part 1/PWC Excel Assignment'
    songs = materials / '2. SQL part 1/Assignments/cs50 assignment/songs'
    if not (film / 'Assignment_01_Excel-SQL.xlsx').is_file() or not (songs / 'requierements.txt').is_file():
        parser.error('Choose the course materials folder containing the Excel and SQL assignment directories.')

    question_rows = workbook_rows(film / 'Assignment_01_Excel-SQL.xlsx', 1)
    labels = json.loads((LOCAL / 'film-question-labels.json').read_text())
    indexed = {int(row['A']):row['B'] for row in question_rows
               if row.get('A', '').isdigit() and row.get('B')}
    questions = [
        dict(label, id=f'PWC-EXCEL-{index:03}', source_index=index,
             source_row=index+2, prompt=indexed[index])
        for index, label in enumerate(labels, 1)
    ]
    song_lines = (songs / 'requierements.txt').read_text().splitlines()
    first = next(i for i, line in enumerate(song_lines) if line.startswith('In 1.sql'))
    questions.append(dict(id='CS50-SONGS-001', source_index=1, title='List song names and energy',
                          skill='Selecting columns', tool='SQL', case='CS50 Songs',
                          source_file='songs/requierements.txt', source_section='Before relational · 1.sql',
                          prompt=song_lines[first], output_requirement=song_lines[first+1],
                          source_issue='The source output sentence is awkwardly worded; the prompt specifies song name and energy as the two columns.',
                          dataset='songs.db'))
    files = PUBLIC / 'files'
    files.mkdir(exist_ok=True)
    shutil.copyfile(film / 'NYC_Film_Permits.xlsx', files / 'NYC_Film_Permits.xlsx')
    shutil.copyfile(songs / 'songs.db', files / 'songs.db')
    (PUBLIC / 'questions.js').write_text('window.EXAM_QUESTIONS = ' + json.dumps(questions, ensure_ascii=False) + ';\n')
    (ROOT / 'exam-studio-discovery').mkdir(exist_ok=True)
    environment = dict(os.environ, EXAM_STUDIO_MATERIALS=str(materials))
    for folder, scripts in [
        (LOCAL, ['prepare_regression.py', 'prepare_restaurant_variants.py', 'prepare_references.py']),
        (ROOT / 'exam-studio-hosted', ['build_content.py', 'build_assets.py']),
    ]:
        for script in scripts:
            subprocess.run([sys.executable, str(folder / script)], env=environment, check=True)


if __name__ == '__main__':
    main()
