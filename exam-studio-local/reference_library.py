"""Only return worked references that match the current public question content."""
from pathlib import Path
import hashlib
import json

DIRECTORY=Path(__file__).resolve().parent


def signature(q):
    content={key:q.get(key) for key in ('id','prompt','model','dataset','category','output_requirement')}
    if q.get('additional_datasets'):
        content['additional_datasets'] = q['additional_datasets']
    return hashlib.sha256(json.dumps(content,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def get_reference(q):
    values=json.loads((DIRECTORY/'reference-solutions.json').read_text())
    result=values.get(q['id'])
    if result and result.get('question_signature')==signature(q):return result
    return None


def dataset_context(q):
    if not q.get('dataset'):return None
    return json.loads((DIRECTORY/'dataset-contexts.json').read_text()).get(q['dataset'])


def tutor_policy():
    return (DIRECTORY/'tutor-policy.txt').read_text()
