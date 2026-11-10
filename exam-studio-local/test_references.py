import copy
import io
import json
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
import attempts
import reference_library
import server


class ReferenceTests(unittest.TestCase):
    def setUp(self):attempts.ATTEMPTS.clear()

    def test_all_references_bind_to_exact_current_content(self):
        values=json.loads((reference_library.DIRECTORY/'reference-solutions.json').read_text())
        self.assertEqual(set(values), set(server.QUESTIONS))
        for qid in values:self.assertIsNotNone(reference_library.get_reference(server.QUESTIONS[qid]),qid)
        self.assertEqual(len(server.QUESTIONS),121)

    def test_changed_model_cannot_use_old_reference(self):
        q=copy.deepcopy(server.QUESTIONS['REST-REG-P']);q['model']['terms'][0]['estimate']+=1
        self.assertIsNone(reference_library.get_reference(q))

    def test_correct_prediction_and_policy_reach_model_context(self):
        payload=server.make_payload({'question_id':'REST-REG-P','messages':[{'role':'user','text':'My answer is $3,123.34.'}]})
        prompt=payload['system_instruction']['parts'][0]['text']
        self.assertIn('3123.34',prompt);self.assertIn('Do not ask them to redo correct arithmetic',prompt);self.assertIn('not executed in Excel',prompt) if 'not executed in Excel' in prompt else self.assertIn('NO execution tools',prompt)

    def test_chinook_context_uses_actual_database_schema(self):
        payload=server.make_payload({'question_id':'CHINOOK-015','messages':[{'role':'user','text':'How should I group the data?'}]})
        prompt=payload['system_instruction']['parts'][0]['text'];self.assertIn('BillingCountry',prompt);self.assertIn('Chinook_Sqlite.sqlite',prompt);self.assertNotIn('songs.db',prompt)

    def test_payroll_comparison_uses_both_source_schemas(self):
        payload = server.make_payload({
            'question_id': 'INT-05',
            'messages': [{'role': 'user', 'text': 'Which columns should I add?'}],
        })
        prompt = payload['system_instruction']['parts'][0]['text']
        for field in ('Reg_Pay', 'OT_Pay', 'Gross_Wages', 'IntegrateCo-2016.csv'):
            self.assertIn(field, prompt)
        self.assertNotIn('Shooting Permit', prompt)
        question = dict(server.QUESTIONS['INT-05'], additional_datasets=['ETL-Case1.csv'])
        self.assertIsNone(reference_library.get_reference(question))

    def test_saved_question_mismatch_blocks_current_model_feedback(self):
        q=copy.deepcopy(server.QUESTIONS['REST-REG-P']);q['model']['terms'][0]['estimate']+=10
        with self.assertRaises(server.TutorError):server.make_payload({'question_id':q['id'],'question_snapshot':q,'messages':[{'role':'user','text':'Review this.'}]})

    def test_reference_endpoint_blocked_during_simulation(self):
        attempts.handle('start',{'kind':'interpretation','mode':'simulation'})
        handler=object.__new__(server.Handler);handler.path='/api/reference';handler.headers=Message();body=b'{"question_id":"REST-REG-P"}'
        for key,value in {'Host':'127.0.0.1:8765','Origin':'http://127.0.0.1:8765','X-Exam-Studio-Token':server.TOKEN,'Content-Type':'application/json','Content-Length':str(len(body))}.items():handler.headers[key]=value
        handler.rfile=io.BytesIO(body);responses=[];handler.respond=lambda status,value:responses.append((status,value));handler.do_POST()
        self.assertEqual(responses[0][0],409);self.assertNotIn('reference',responses[0][1])


if __name__=='__main__':unittest.main()
