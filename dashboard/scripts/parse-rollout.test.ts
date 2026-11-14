import { describe, expect, test } from 'bun:test';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { parseRollout, type RolloutSource } from './parse-rollout';
import { messageKind } from '../src/transcript';

const sourceDir = resolve(import.meta.dir, '../sources/temporary');
const sources = JSON.parse(await readFile(resolve(sourceDir, 'manifest.json'), 'utf8')) as RolloutSource[];

describe('public rollout import', () => {
  for (const source of sources) {
    test(`${source.id}: preserves the entire archive and exact evidence positions`, async () => {
      const text = await readFile(resolve(sourceDir, source.file), 'utf8');
      const run = parseRollout(text, source);
      expect(run.text).toBe(text);
      expect(run.transcript_hash).toBe(createHash('sha256').update(text).digest('hex'));
      for (const message of run.display_messages) {
        for (const segment of message.segments) {
          const start = segment.anchors[0]![1];
          expect(text.slice(start, start + segment.text.length)).toBe(segment.text);
        }
      }
      const count = (kind: string) => run.display_messages.filter(m => messageKind(m) === kind).length;
      expect(count('system')).toBe(1);
      expect(count('user')).toBe(1);
      expect(count('reasoning')).toBe([...text.matchAll(/^ +REASONING +$/gm)].length);
      expect(count('tool-call')).toBe([...text.matchAll(/^ +TOOL CALL +$/gm)].length);
      expect(count('tool')).toBe([...text.matchAll(/^ +TOOL RESULT +$/gm)].length);
      expect(run.display_messages.at(-1)?.segments[0]?.text).toContain('Status:');
      if (source.id === 'temp-kimi-precommit-100') {
        expect(run.temporary?.status).toBe('INCOMPLETE');
        expect(run.temporary?.steps).toBe(30);
        expect(run.temporary?.reasoningBlocks).toBe(30);
        expect(run.temporary?.toolCalls).toBe(30);
        expect(run.messageCount).toBe(103);
        expect(count('assistant')).toBe(9);
        // A large result must survive preprocessing, not just its displayed preview.
        expect(Math.max(...run.display_messages.flatMap(m => m.segments.map(s => s.text.length)))).toBeGreaterThan(17000);
      }
    });
    test(`${source.id}: refuses an altered or partial download`, async () => {
      const text = await readFile(resolve(sourceDir, source.file), 'utf8');
      expect(() => parseRollout(text.slice(0, -200), source)).toThrow('Source checksum changed');
    });
  }
  test('classifies source labels instead of reasoning-like phrases in assistant output', () => {
    const header = (label: string) => `${'='.repeat(70)}\n${label}\n${'='.repeat(70)}\n`;
    const text = header('SYSTEM PROMPT') + 'System\n' + header('USER_PROMPT') + 'User\n' + header('REASONING') + 'Actual reasoning\n' + header('RESPONSE') + 'Let me think about this.\n' + header('FINAL RESULTS') + 'Status: COMPLETE\n';
    const source = {...sources[0]!, sha256: createHash('sha256').update(text).digest('hex')};
    const run = parseRollout(text, source);
    expect(messageKind(run.display_messages[2]!)).toBe('reasoning');
    expect(messageKind(run.display_messages[3]!)).toBe('assistant');
    expect(run.temporary?.status).toBe('COMPLETE');
  });
});
