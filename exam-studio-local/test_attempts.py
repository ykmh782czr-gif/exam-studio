import unittest
from unittest.mock import patch
import attempts
import server
import io
from email.message import Message


class AttemptTests(unittest.TestCase):
    def setUp(self):attempts.ATTEMPTS.clear()

    def start(self,kind='combined',mode='simulation',timed=False):
        with patch('attempts.time.time',return_value=1000):return attempts.handle('start',{'kind':kind,'mode':mode,'timer_enabled':timed})['attempt']

    def test_section_times_and_combined_composition(self):
        for kind,seconds,count in [('manipulation',480,6),('interpretation',300,4),('combined',780,10)]:
            attempts.ATTEMPTS.clear();a=self.start(kind)
            self.assertEqual(a['deadline'],1000+seconds);self.assertEqual(len(a['question_ids']),count)
            self.assertEqual(len(a['question_ids']),len(set(a['question_ids'])))
            self.assertTrue(all(q in server.QUESTIONS for q in a['question_ids']))

    def test_submission_freezes_snapshot_and_cannot_be_edited(self):
        a=self.start();qid=a['question_ids'][0];work={qid:{'answer':'original','method':'my method'}}
        with patch('attempts.time.time',return_value=1010):
            submitted=attempts.handle('submit',{'id':a['id'],'answers':work})['attempt']
            work[qid]['answer']='changed'
            after=attempts.handle('save',{'id':a['id'],'answers':work})['attempt']
        self.assertEqual(submitted['state'],'submitted');self.assertEqual(after['answers'][qid]['answer'],'original')

    def test_exam_picker_matches_questions_and_downloads(self):
        catalogue = attempts.exam_catalogue()
        for kind, exams in catalogue.items():
            for exam in exams:
                attempts.ATTEMPTS.clear()
                with self.subTest(kind=kind, exam=exam['id']):
                    attempt = attempts.handle('start', {
                        'kind': kind, 'mode': 'simulation', 'exam_id': exam['id'],
                    }, server.QUESTIONS)['attempt']
                    questions = list(attempt['question_snapshot'].values())
                    self.assertEqual(attempt['exam_title'], exam['title'])
                    self.assertEqual(attempt['duration'], attempts.DURATION[kind])
                    self.assertEqual(sum(bool(q.get('model')) for q in questions), 0 if kind == 'manipulation' else 4)
                    sql = [q for q in questions if q.get('tool') == 'SQL']
                    self.assertEqual(len(sql), 0 if kind == 'interpretation' else 3)
                    self.assertEqual({q['dataset'] for q in sql}, set(exam['files']) - {'NYC_Film_Permits.xlsx'})
                    self.assertEqual(sum(not q.get('tool') for q in questions), 0 if kind == 'interpretation' else 3)
        attempts.ATTEMPTS.clear()
        with self.assertRaises(attempts.AttemptError):
            attempts.handle('start', {'kind': 'interpretation', 'mode': 'simulation', 'exam_id': 'm02'})

    def test_deadline_is_fixed_and_late_work_cannot_change_snapshot(self):
        a=self.start('interpretation');qid=a['question_ids'][0]
        with patch('attempts.time.time',return_value=1299):attempts.handle('save',{'id':a['id'],'answers':{qid:{'answer':'before'}}})
        with patch('attempts.time.time',return_value=1300):
            frozen=attempts.handle('save',{'id':a['id'],'answers':{qid:{'answer':'late'}}})['attempt']
        self.assertEqual(frozen['reason'],'time-expired');self.assertEqual(frozen['submitted_at'],1300);self.assertEqual(frozen['answers'][qid]['answer'],'before')

    def test_simulation_ai_lock_ends_after_submission(self):
        a=self.start()
        with patch('attempts.time.time',return_value=1001):
            self.assertTrue(attempts.simulation_active())
            attempts.handle('submit',{'id':a['id'],'answers':{}})
            self.assertFalse(attempts.simulation_active())

    def test_timed_practice_does_not_auto_submit_or_lock_tutor(self):
        a=self.start('interpretation','practice',True)
        with patch('attempts.time.time',return_value=2000):
            self.assertEqual(attempts.handle('status',{'id':a['id']})['attempt']['state'],'active')
            self.assertFalse(attempts.simulation_active())

    def test_no_second_active_attempt(self):
        self.start()
        with patch('attempts.time.time',return_value=1001),self.assertRaises(attempts.AttemptError):attempts.handle('start',{'kind':'combined','mode':'practice'})

    def test_answers_reject_wrong_question_and_oversize_fields(self):
        a=self.start();qid=a['question_ids'][0]
        for values in [{'not-in-attempt':{'answer':'x'}},{qid:{'answer':'x'*4001}},{qid:{'unknown':'x'}}]:
            with patch('attempts.time.time',return_value=1001),self.assertRaises(attempts.AttemptError):attempts.handle('save',{'id':a['id'],'answers':values})

    def test_interpretation_context_uses_supplied_model_only(self):
        payload=server.make_payload({'question_id':'REST-REG-I','messages':[{'role':'user','text':'Explain my interaction interpretation.'}]})
        context=payload['system_instruction']['parts'][0]['text']
        self.assertIn('Supplied model only',context);self.assertIn('Earlier sales',context);self.assertNotIn('Shooting Permit',context)

    def test_server_endpoint_blocks_ai_before_provider_call(self):
        self.start()
        handler=object.__new__(server.Handler);handler.path='/api/chat';handler.headers=Message()
        body=b'{"question_id":"PWC-EXCEL-001","messages":[{"role":"user","text":"Help"}]}'
        for key,value in {'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:8765','X-Exam-Studio-Token':server.TOKEN,'Content-Type':'application/json','Content-Length':str(len(body))}.items():handler.headers[key]=value
        handler.rfile=io.BytesIO(body);responses=[];handler.respond=lambda status,data:responses.append((status,data))
        with patch('attempts.time.time',return_value=1001),patch('server.google_request') as provider:
            handler.do_POST();provider.assert_not_called()
        self.assertEqual(responses[0][0],409);self.assertIn('disabled',responses[0][1]['error'])

    def test_content_snapshot_is_detached_from_later_edits(self):
        catalog={q:dict(server.QUESTIONS[q]) for q in attempts.SET_IDS['interpretation']}
        with patch('attempts.time.time',return_value=1000):a=attempts.handle('start',{'kind':'interpretation','mode':'simulation'},catalog)['attempt']
        catalog['REST-REG-P']['prompt']='later edit'
        self.assertNotEqual(a['question_snapshot']['REST-REG-P']['prompt'],'later edit')


if __name__=='__main__':unittest.main()
