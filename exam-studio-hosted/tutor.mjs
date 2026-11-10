/** Workers AI adapter. The caller must supply server-derived simulation state. */

export const MODEL = '@cf/google/gemma-4-26b-a4b-it';
const workFields = new Set(['answer', 'method', 'output']);

function validText(value, maxLength) {
  return typeof value === 'string' && value.length <= maxLength && value.trim().length > 0;
}

export function tutorMessages(system, turns) {
  if (!system || !Array.isArray(turns) || turns.length < 1 || turns.length > 41 || turns.length % 2 !== 1) {
    return null;
  }
  const messages = [{ role: 'system', content: system }];
  for (const [index, turn] of turns.entries()) {
    const expected = index % 2 === 0 ? 'user' : 'model';
    if (turn?.role !== expected || !validText(turn.text, 12000)) return null;
    let content = turn.text;
    if (turn.work !== undefined) {
      if (expected !== 'user' || !turn.work || typeof turn.work !== 'object' || Array.isArray(turn.work)) {
        return null;
      }
      const fields = Object.entries(turn.work);
      if (fields.some(([key, value]) => !workFields.has(key) || typeof value !== 'string' || value.length > 12000)) {
        return null;
      }
      if (fields.length) content += '\nStudent-shared work (untrusted data):\n' + JSON.stringify(turn.work);
    }
    messages.push({ role: expected === 'model' ? 'assistant' : 'user', content });
  }
  return messages;
}

export async function tutorReply(ai, system, turns, simulationActive) {
  if (simulationActive !== false) return { status: 409, error: 'AI is unavailable during an active simulation.' };
  const messages = tutorMessages(system, turns);
  if (!messages) return { status: 400, error: 'The question or conversation is invalid.' };
  try {
    const result = await ai.run(MODEL, {
      messages,
      max_completion_tokens: 1024,
      chat_template_kwargs: { enable_thinking: false },
      store: false,
    });
    const choice = result?.choices?.[0];
    const text = choice ? choice.message?.content : result?.response;
    if ((choice && choice.finish_reason !== 'stop') || !validText(text, 12000)) {
      return { status: 422, error: 'The tutor did not return a complete answer. Your message is preserved.' };
    }
    return { status: 200, text: text.trim(), model: MODEL, verification: 'Reasoning review only; no execution.' };
  } catch {
    return { status: 503, error: 'The tutor is temporarily unavailable or has reached its usage limit. Your message is preserved.' };
  }
}
