"""Export the checked tutor context for the hosted backend, outside static assets."""

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'exam-studio-local'))

from server import QUESTIONS, make_payload
from attempts import DURATION, exam_catalogue, MANIPULATION_EXAMS, INTERPRETATION_EXAMS
from reference_library import get_reference
from excel_cases import EXCEL_CASE_FILES


def main():
    contexts = {}
    for question_id in QUESTIONS:
        payload = make_payload({
            'question_id': question_id,
            'messages': [{'role': 'user', 'text': 'Context validation'}],
        })
        contexts[question_id] = payload['system_instruction']['parts'][0]['text']
    exams = exam_catalogue()
    question_ids = {}
    for kind, options in exams.items():
        question_ids[kind] = {}
        for exam in options:
            exam_id = exam['id']
            if kind == 'interpretation':
                ids = INTERPRETATION_EXAMS[exam_id][1]
            else:
                manipulation, _, interpretation = exam_id.partition('-')
                ids = list(MANIPULATION_EXAMS[manipulation][2])
                if kind == 'combined':
                    ids.extend(INTERPRETATION_EXAMS[interpretation or 'i01'][1])
            assert all(question_id in QUESTIONS for question_id in ids)
            question_ids[kind][exam_id] = ids
    content = dict(contexts=contexts, exams=exams, durations=DURATION, examQuestions=question_ids,
                   courseFiles=EXCEL_CASE_FILES,
                   questions=QUESTIONS, references={key: get_reference(q) for key, q in QUESTIONS.items()})
    (HERE / 'content.generated.json').write_text(
        json.dumps(content, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f'Prepared server-side context for {len(contexts)} questions.')


if __name__ == '__main__':
    main()
