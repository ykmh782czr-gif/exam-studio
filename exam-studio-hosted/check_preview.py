"""Smoke-test the private deployment without printing credentials."""

import base64
from email import message_from_bytes
import json
from pathlib import Path
import sys
import subprocess
import tempfile
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent


def main():
    origin = sys.argv[1].rstrip('/')
    url = urlsplit(origin)
    if url.scheme != 'https' or not url.hostname.endswith('.workers.dev') or url.path or url.query or url.fragment:
        raise SystemExit('Provide the HTTPS workers.dev origin.')
    password = json.loads((HERE / '.dev.vars.preview-deploy.json').read_text())['PREVIEW_PASSWORD']
    authorization = 'Basic ' + base64.b64encode(f'examstudio:{password}'.encode()).decode()

    def client():
        token = ''
        cookie = ''

        def send(path, payload=None, *, expected=200, auth=True, method=None, prefix=None):
            nonlocal cookie
            headers = ['Authorization: ' + authorization] if auth else []
            if cookie and auth:
                headers.append('Cookie: ' + cookie)
            if payload is not None:
                headers.extend(['Origin: ' + origin, 'Content-Type: application/json',
                                'X-Exam-Studio-Token: ' + token])
            with tempfile.TemporaryDirectory(prefix='exam-studio-check-') as temp:
                header_file = Path(temp) / 'headers'
                args = ['/usr/bin/curl', '--disable', '--silent', '--show-error', '--max-time', '70',
                        '--dump-header', str(header_file), '--config', '-', origin + path]
                if method == 'HEAD':
                    args.append('--head')
                config = ''.join('header = ' + json.dumps(header) + '\n' for header in headers)
                if payload is not None:
                    config += 'data-binary = ' + json.dumps(json.dumps(payload, ensure_ascii=True)) + '\n'
                if prefix is None:
                    result = subprocess.run(args, input=config.encode(), capture_output=True, check=True)
                    data = result.stdout
                else:
                    with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as run:
                        run.stdin.write(config.encode())
                        run.stdin.close()
                        data = run.stdout.read(prefix)
                        if run.poll() is None:
                            run.terminate()
                blocks = header_file.read_bytes().strip().split(b'\r\n\r\n')
                first_line, _, raw_headers = blocks[-1].partition(b'\r\n')
                code = int(first_line.split()[1])
                reply_headers = message_from_bytes(raw_headers)
                if code != expected:
                    raise RuntimeError(f'{path}: expected HTTP {expected}, got {code}')
                if reply_headers.get('Set-Cookie'):
                    cookie = reply_headers['Set-Cookie'].split(';')[0]
                if method == 'HEAD':
                    return reply_headers
                if reply_headers.get_content_type() == 'application/json':
                    return json.loads(data)
                return data

        send('/', expected=401, auth=False)
        status = send('/api/status')
        token = status['token']
        assert status['provider'] == 'cloudflare' and status['configured']
        return send

    send = client()
    assert b'What would you like to practise?' in send('/')
    files = HERE.parent / 'exam-studio-preview' / 'files'
    for path in files.iterdir():
        if path.name.startswith('.'):
            continue
        headers = send('/files/'+path.name, method='HEAD')
        if headers.get('Content-Length') is not None:
            assert int(headers['Content-Length']) == path.stat().st_size, path.name
    for filename in ('movies.db','pcards.db'):
        assert send('/files/'+filename, prefix=16) == b'SQLite format 3\x00'
    print('Private access and all 11 download routes passed.', flush=True)

    attempt = send('/api/attempt/start', {'kind':'combined','exam_id':'m05','mode':'simulation'})['attempt']
    assert len(attempt['question_ids']) == 10 and attempt['deadline'] - attempt['started_at'] == 780
    assert send('/api/attempt/current', {})['attempt']['deadline'] == attempt['deadline']
    question_id = attempt['question_ids'][0]
    send('/api/chat', {'question_id':question_id,'messages':[{'role':'user','text':'QA hint request'}]}, expected=409)
    send('/api/reference', {'question_id':question_id}, expected=409)
    submitted = send('/api/attempt/submit', {'id':attempt['id'],'answers':{question_id:{'answer':'Synthetic QA check'}}})
    assert submitted['attempt']['state'] == 'submitted'
    assert send('/api/reference', {'question_id':question_id})['reference']
    print('13-minute timer, simulation lock and post-submit solution passed.', flush=True)

    cases = [
        ('PWC-EXCEL-003', ['COUNTBLANK returned zero for the ZIP data range. Give me a hint.', 'Some cells contain literal N/A. Why did COUNTBLANK ignore them?']),
        ('CS50-SONGS-006', ["I joined songs and artists, but WHERE name = 'Drake' is ambiguous. Give me a hint.", 'I fixed the WHERE clause to artists.name. Why is SELECT name still ambiguous?']),
        ('REST-REG-P', ['At 60°F with no game, I calculated $3,123.34. Is that correct and how did you check?']),
    ]
    for question_id, questions in cases:
        turns = []
        for question in questions:
            turns.append({'role':'user','text':question})
            reply = send('/api/chat', {'question_id':question_id,'messages':turns})['text']
            turns.append({'role':'model','text':reply})
            print(f'{question_id}: {reply}', flush=True)


if __name__ == '__main__':
    main()
