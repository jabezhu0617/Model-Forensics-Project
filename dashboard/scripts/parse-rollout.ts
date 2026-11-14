import { createHash } from 'node:crypto';
import type { Message, Run, TemporarySource } from '../src/types';

export interface RolloutSource {
  id: string; file: string; title: string; model: string; scenario: string; run: string;
  sourceUrl: string; sourceRevision: string; sha256: string;
}

// These are explicit archive section labels, never guesses based on the prose.
const headings = /^={70}\r?\n[ \t]*(SYSTEM PROMPT|USER_PROMPT|STEP \d+|REASONING|RESPONSE|TOOL CALL|TOOL RESULT|FINAL RESULTS)[ \t]*\r?\n={70}\r?\n/gm;
const sections: Record<string, {role: string; kind: string}> = {
  'SYSTEM PROMPT': {role: 'system', kind: 'text'},
  USER_PROMPT: {role: 'user', kind: 'text'},
  REASONING: {role: 'assistant', kind: 'reasoning'},
  RESPONSE: {role: 'assistant', kind: 'text'},
  'TOOL CALL': {role: 'assistant', kind: 'command'},
  'TOOL RESULT': {role: 'tool', kind: 'output'},
  'FINAL RESULTS': {role: 'event', kind: 'status'},
};

export function parseRollout(text: string, source: RolloutSource): Run {
  const hash = createHash('sha256').update(text).digest('hex');
  if (hash !== source.sha256) throw new Error(`Source checksum changed: ${source.id}`);
  const matches = [...text.matchAll(headings)];
  if (!matches.length) throw new Error(`No rollout sections: ${source.id}`);
  const messages: Message[] = [];
  const steps = new Set<number>();
  let step: number | undefined;
  const add = (start: number, end: number, role: string, kind: string, label = '') => {
    // Remove only archive framing and outer whitespace. Every displayed character
    // still maps to an exact position in the downloadable, unmodified source.
    const body = text.slice(start, end);
    const framing = /\r?\n={70}(?:\r?\n)*$/.exec(body);
    if (framing) end = start + framing.index;
    while (start < end && /\s/.test(text[start]!)) start++;
    while (end > start && /\s/.test(text[end - 1]!)) end--;
    if (start === end) return;
    const message: Message = {
      role, index: messages.length,
      segments: [{text: text.slice(start, end), anchors: [[0, start]], kind, label}],
      ...(step === undefined ? {} : {step}),
    };
    if (role === 'tool') {
      const exit = /^Exit code: (-?\d+)$/m.exec(text.slice(start, end));
      if (exit) message.exit_code = Number(exit[1]);
    }
    messages.push(message);
  };
  add(0, matches[0]!.index!, 'event', 'status', 'Setup');
  for (let i = 0; i < matches.length; i++) {
    const match = matches[i]!;
    const label = match[1]!;
    const start = match.index! + match[0].length;
    const end = matches[i + 1]?.index ?? text.length;
    if (label.startsWith('STEP ')) {
      step = Number(label.slice(5)); steps.add(step);
      if (text.slice(start, end).trim()) throw new Error(`Unexpected step content: ${source.id}`);
      continue;
    }
    const section = sections[label]!;
    if (label === 'FINAL RESULTS') step = undefined;
    add(start, end, section.role, section.kind, label === 'FINAL RESULTS' ? 'Run result' : '');
  }
  const result = messages.find(m => m.segments[0]?.label === 'Run result')?.segments[0]?.text;
  const status = result?.match(/^Status: (.+)$/m)?.[1]?.trim();
  if (!status || !messages.some(m => m.role === 'system') || !messages.some(m => m.role === 'user')) {
    throw new Error(`Missing prompt or final status: ${source.id}`);
  }
  const temporary: TemporarySource = {
    title: source.title, model: source.model, scenario: source.scenario, run: source.run,
    status, sourceUrl: source.sourceUrl, sourceRevision: source.sourceRevision,
    downloadUrl: `/downloads/temporary/${source.id}.log`, bytes: Buffer.byteLength(text),
    steps: steps.size,
    reasoningBlocks: messages.filter(m => m.segments[0]?.kind === 'reasoning').length,
    toolCalls: messages.filter(m => m.segments[0]?.kind === 'command').length,
  };
  return {
    id: source.id, experiment: 'temporary', outcome: 'unresolved', status,
    transcript_hash: hash, selected: false, support: '', excerpt: '',
    messageCount: messages.length, text, display_messages: messages,
    submission: null, annotation: {}, suggested_highlights: [],
    reasoning_available: temporary.reasoningBlocks > 0, temporary,
  };
}
