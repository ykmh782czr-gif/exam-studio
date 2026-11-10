"""Authoritative local attempt state and fixed deadlines; no student grading."""
import copy
import secrets
import time

ATTEMPTS = {}
SET_IDS = {
    'manipulation': ['PWC-EXCEL-001','PWC-EXCEL-008','PWC-EXCEL-011','CS50-SONGS-001','CS50-SONGS-002','CS50-SONGS-003'],
    'interpretation': ['REST-REG-P','REST-REG-S','REST-REG-Q','REST-REG-I']
}
SET_IDS['combined'] = SET_IDS['manipulation'] + SET_IDS['interpretation']
DURATION = {'manipulation':480,'interpretation':300,'combined':780}

MANIPULATION_EXAMS = {
    'm01': ('M01 · Records, categories and sorting', 'songs.db', SET_IDS['manipulation']),
    'm02': ('M02 · Data quality and invoice filters', 'Chinook_Sqlite.sqlite',
            ['PWC-EXCEL-002','PWC-EXCEL-003','PWC-EXCEL-004','CHINOOK-004','CHINOOK-005','CHINOOK-006']),
    'm03': ('M03 · Dates, boroughs and customer records', 'Chinook_Sqlite.sqlite',
            ['PWC-EXCEL-006','PWC-EXCEL-007','PWC-EXCEL-013','CHINOOK-002','CHINOOK-003','CHINOOK-009']),
    'm04': ('M04 · Durations, conditions and joins', 'songs.db',
            ['PWC-EXCEL-016','PWC-EXCEL-017','PWC-EXCEL-019','CS50-SONGS-004','CS50-SONGS-005','CS50-SONGS-006']),
    'm05': ('M05 · Permit timing and movie ratings', 'movies.db',
            ['PWC-EXCEL-012','PWC-EXCEL-018','PWC-EXCEL-020','CS50-MOVIES-001','CS50-MOVIES-004','CS50-MOVIES-007']),
}

INTERPRETATION_EXAMS = {'i01': ('I01 · Restaurant regression', SET_IDS['interpretation'])}
for number, title in enumerate((
    'Maximum temperature and weekend sales', 'Minimum temperature and precipitation',
    'Previous week sales and games', 'Earlier sales and weekends', 'Year-earlier sales and precipitation',
    'Maximum temperature and items sold', 'Minimum temperature and weekend items',
    'Previous week sales and items sold', 'Earlier sales and game-day items',
), 2):
    INTERPRETATION_EXAMS[f'i{number:02}'] = (
        f'I{number:02} · {title}', [f'REST-EXAM-{number:02}-{suffix}' for suffix in 'PSQI'],
    )


def exam_catalogue():
    manipulation = [
        {'id': key, 'title': title, 'files': ['NYC_Film_Permits.xlsx', database]}
        for key, (title, database, _) in MANIPULATION_EXAMS.items()
    ]
    interpretation = [{'id': key, 'title': title, 'files': []}
                      for key, (title, _) in INTERPRETATION_EXAMS.items()]
    combined = [{'id': exam['id'], 'title': exam['title'] + ' + Restaurant', 'files': exam['files']}
                for exam in manipulation]
    for index, interpretation_exam in enumerate(interpretation[1:]):
        exam = manipulation[index % len(manipulation)]
        combined.append({
            'id': f"{exam['id']}-{interpretation_exam['id']}",
            'title': exam['title'] + ' + ' + interpretation_exam['title'],
            'files': exam['files'],
        })
    return {
        'manipulation': manipulation,
        'combined': combined,
        'interpretation': interpretation,
    }


class AttemptError(Exception):
    pass


def refresh(attempt, now=None):
    now=time.time() if now is None else now
    if attempt['state']=='active' and attempt['mode']=='simulation' and now>=attempt['deadline']:
        attempt.update(state='submitted',submitted_at=attempt['deadline'],reason='time-expired')
    return attempt


def active():
    return next((a for a in ATTEMPTS.values() if refresh(a)['state']=='active'),None)


def simulation_active():
    a=active()
    return bool(a and a['mode']=='simulation')


def snapshot(a):
    if a is None:return {'attempt':None,'server_now':time.time()}
    return {'attempt':copy.deepcopy(refresh(a)),'server_now':time.time()}


def validate_answers(a,values):
    if not isinstance(values,dict) or any(q not in a['question_ids'] for q in values):raise AttemptError('Invalid question answers.')
    result={}
    for q,fields in values.items():
        if not isinstance(fields,dict) or any(k not in ('answer','method','output') or not isinstance(v,str) or len(v)>4000 for k,v in fields.items()):raise AttemptError('Each answer field must be at most 4,000 characters.')
        result[q]={k:fields.get(k,'') for k in ('answer','method','output')}
    return result


def handle(action,data,question_catalog=None):
    if action=='start':
        if active():raise AttemptError('An attempt is already active. Resume or submit it before starting another.')
        kind=data.get('kind');mode=data.get('mode')
        if kind not in SET_IDS or mode not in ('practice','simulation'):raise AttemptError('Invalid session type or mode.')
        exams = exam_catalogue()[kind]
        exam_id = data.get('exam_id', exams[0]['id'])
        exam = next((item for item in exams if item['id'] == exam_id), None)
        if exam is None:
            raise AttemptError('This exam is unavailable for the selected session type.')
        if kind == 'interpretation':
            question_ids = list(INTERPRETATION_EXAMS[exam_id][1])
        else:
            manipulation_id, _, interpretation_id = exam_id.partition('-')
            question_ids = list(MANIPULATION_EXAMS[manipulation_id][2])
            if kind == 'combined':
                question_ids.extend(INTERPRETATION_EXAMS[interpretation_id or 'i01'][1])
        now=time.time();timed=mode=='simulation' or data.get('timer_enabled') is True
        a={'id':secrets.token_urlsafe(24),'kind':kind,'mode':mode,'duration':DURATION[kind] if timed else None,'started_at':now,'deadline':now+DURATION[kind] if timed else None,'question_ids':question_ids,'exam_id':exam_id,'exam_title':exam['title'],'answers':{},'state':'active','reason':None,'submitted_at':None}
        if question_catalog is not None:
            if any(qid not in question_catalog for qid in a['question_ids']):raise AttemptError('Session content is incomplete.')
            a['question_snapshot']={qid:copy.deepcopy(question_catalog[qid]) for qid in a['question_ids']}
        ATTEMPTS[a['id']]=a;return snapshot(a)
    if action=='current':return snapshot(active())
    a=ATTEMPTS.get(data.get('id'))
    if a is None:raise AttemptError('This local attempt is unavailable, possibly because the server restarted. Your browser copy is retained for recovery.')
    refresh(a)
    if action=='status':return snapshot(a)
    if action not in ('save','submit'):raise AttemptError('Unknown session action.')
    if a['state']!='active':return snapshot(a)
    a['answers']=validate_answers(a,data.get('answers'))
    if action=='submit':a.update(state='submitted',submitted_at=time.time(),reason='submitted')
    return snapshot(a)
