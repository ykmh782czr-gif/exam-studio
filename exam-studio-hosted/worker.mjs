import content from './content.generated.json' with { type: 'json' };
import downloads from './downloads.generated.json' with { type: 'json' };
import { splitDownload } from './downloads.mjs';
import { MODEL, tutorReply } from './tutor.mjs';

const attemptPath = '/api/attempt/';
const fields = ['answer', 'method', 'output'];
const oneDay = 86400;
const response = (data, status=200) => Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
const error = (message, status) => response({ error: message }, status);
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const nowSeconds = () => Date.now() / 1000;

function expiredAttempt(attempt, now) {
  if (attempt?.state === 'active' && attempt.mode === 'simulation' && now >= attempt.deadline) {
    return { ...attempt, state: 'submitted', reason: 'time-expired', submitted_at: attempt.deadline };
  }
  return attempt;
}

function normalizeAnswers(attempt, answers) {
  if (!isObject(answers)) return null;
  const result = {};
  for (const [id, answer] of Object.entries(answers)) {
    if (!attempt.question_ids.includes(id) || !isObject(answer)) return null;
    if (Object.entries(answer).some(([key, value]) => !fields.includes(key) || typeof value !== 'string' || value.length > 4000)) return null;
    result[id] = Object.fromEntries(fields.map(key => [key, answer[key] ?? '']));
  }
  return result;
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (!isObject(value)) return value;
  return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
}

function matchingQuestion(snapshot, question) {
  if (!isObject(snapshot)) return false;
  const keys = ['id', 'prompt', 'model', 'dataset', 'category', 'output_requirement', 'additional_datasets'];
  const fieldsOf = value => keys.map(key => canonical(value[key] ?? null));
  return JSON.stringify(fieldsOf(snapshot)) === JSON.stringify(fieldsOf(question));
}

async function readBody(request) {
  if (!request.body || request.headers.get('Content-Type')?.split(';')[0] !== 'application/json') return null;
  const reader = request.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let size = 0, text = '';
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 200000) {
        await reader.cancel();
        return null;
      }
      text += decoder.decode(value, { stream: true });
    }
    const body = JSON.parse(text + decoder.decode());
    return isObject(body) ? body : null;
  } catch {
    return null;
  }
}

export class ExamAttempts {
  constructor(ctx, env) {
    this.storage = ctx.storage;
    this.env = env;
    this.busy = false;
  }

  async save(attempt) {
    await this.storage.put('attempt', attempt);
    await this.storage.setAlarm(Date.now() + oneDay * 1000);
  }

  async alarm() {
    await this.storage.delete('attempt');
  }

  async fetch(request) {
    if (this.busy) return error('Another request is still running. Please try again.', 409);
    this.busy = true;
    try {
      const body = await readBody(request);
      if (!body) return error('Invalid or oversized request.', 400);
      const path = new URL(request.url).pathname;
      const stored = await this.storage.get('attempt') ?? null;
      const now = nowSeconds();
      const attempt = expiredAttempt(stored, now);
      if (attempt !== stored) await this.save(attempt);
      if (path.startsWith(attemptPath)) return await this.handleAttempt(path.slice(attemptPath.length), body, attempt, now);

      const simulation = attempt?.state === 'active' && attempt.mode === 'simulation';
      if (simulation) return error('AI and solutions are unavailable during an active simulation.', 409);
      const id = body.question_id;
      if (typeof id !== 'string' || !Object.hasOwn(content.questions, id)) return error('Unknown question.', 400);
      const question = content.questions[id];
      if (body.question_snapshot != null && !matchingQuestion(body.question_snapshot, question)) {
        return error('The saved question differs from the current version. Your submission remains available.', 409);
      }
      if (path === '/api/reference') {
        const reference = content.references[id];
        return reference ? response({ reference }) : error('No worked solution is available.', 404);
      }
      if (path !== '/api/chat') return error('Not found.', 404);
      const { status, ...result } = await tutorReply(this.env.AI, content.contexts[id], body.messages, false);
      return response(result, status);
    } catch {
      return error('Exam Studio could not complete this request. Your browser draft is still available.', 500);
    } finally {
      this.busy = false;
    }
  }

  async handleAttempt(action, body, attempt, now) {
    const result = value => response({ attempt: value, server_now: now });
    if (action === 'current') return result(attempt?.state === 'active' ? attempt : null);
    if (action === 'start') {
      if (attempt?.state === 'active') return error('Resume or submit the active exam first.', 409);
      const { kind, mode, exam_id: examId } = body;
      if (!Object.hasOwn(content.exams, kind) || !['practice', 'simulation'].includes(mode)) {
        return error('Invalid exam type or mode.', 400);
      }
      const exam = content.exams[kind].find(option => option.id === (examId ?? content.exams[kind][0].id));
      if (!exam) return error('This exam is unavailable.', 400);
      const questionIds = content.examQuestions[kind][exam.id];
      const duration = mode === 'simulation' || body.timer_enabled === true ? content.durations[kind] : null;
      const created = {
        id: crypto.randomUUID(), kind, mode, duration, started_at: now,
        deadline: duration === null ? null : now + duration,
        exam_id: exam.id, exam_title: exam.title, question_ids: questionIds,
        question_snapshot: Object.fromEntries(questionIds.map(id => [id, content.questions[id]])),
        answers: {}, state: 'active', reason: null, submitted_at: null,
      };
      await this.save(created);
      return result(created);
    }
    if (!['status', 'save', 'submit'].includes(action)) return error('Unknown exam action.', 404);
    if (!attempt || attempt.id !== body.id) return error('This exam is unavailable. Your browser draft is still available.', 409);
    if (action === 'status' || attempt.state !== 'active') return result(attempt);
    const answers = normalizeAnswers(attempt, body.answers);
    if (!answers) return error('Invalid answers or a field exceeds 4,000 characters.', 400);
    const updated = { ...attempt, answers };
    if (action === 'submit') Object.assign(updated, { state: 'submitted', reason: 'submitted', submitted_at: now });
    await this.save(updated);
    return result(updated);
  }
}

async function canAccess(request, password) {
  const supplied = request.headers.get('Authorization') ?? '';
  const expected = 'Basic ' + btoa('examstudio:' + password);
  const encode = new TextEncoder();
  const [left, right] = await Promise.all([supplied, expected].map(value => crypto.subtle.digest('SHA-256', encode.encode(value))));
  return new Uint8Array(left).reduce((difference, byte, index) => difference | (byte ^ new Uint8Array(right)[index]), 0) === 0;
}

export default {
  async fetch(request, env) {
    if (!env.PREVIEW_PASSWORD) return error('Private preview is not configured.', 503);
    if (!(await canAccess(request, env.PREVIEW_PASSWORD))) {
      return new Response('Private Exam Studio preview.', {
        status: 401, headers: { 'WWW-Authenticate': 'Basic realm="Exam Studio Preview"', 'Cache-Control': 'no-store' },
      });
    }
    const url = new URL(request.url);
    if (url.pathname.startsWith('/_dataset_parts/')) return error('Not found.', 404);
    if (!url.pathname.startsWith('/api/')) {
      return splitDownload(request, env.ASSETS, downloads) ?? env.ASSETS.fetch(request);
    }
    const sessionId = request.headers.get('Cookie')?.match(/(?:^|;\s*)exam_session=([a-f0-9-]{36})(?:;|$)/)?.[1];
    if (url.pathname === '/api/status' && request.method === 'GET') {
      const token = sessionId ?? crypto.randomUUID();
      const status = response({ configured: !!env.AI, model: MODEL, token, exams: content.exams, provider: 'cloudflare' });
      if (!sessionId) status.headers.append('Set-Cookie', 'exam_session=' + token + '; Path=/; Secure; HttpOnly; SameSite=Strict');
      return status;
    }
    if (request.method !== 'POST' || !sessionId || request.headers.get('Origin') !== url.origin ||
        request.headers.get('X-Exam-Studio-Token') !== sessionId) return error('Reload the preview before continuing.', 403);
    if (!url.pathname.startsWith(attemptPath) && !['/api/chat', '/api/reference'].includes(url.pathname)) {
      return error('Not found.', 404);
    }
    return env.ATTEMPTS.getByName(sessionId).fetch(request);
  },
};
