import { copyFile, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { parseRollout, type RolloutSource } from './parse-rollout';
import type { TemporarySummary } from '../src/types';

export async function exportTemporary(dataDir: string, downloads: string) {
  const sourceDir = resolve(import.meta.dir, '../sources/temporary');
  const sources = JSON.parse(await readFile(resolve(sourceDir, 'manifest.json'), 'utf8')) as RolloutSource[];
  const index: TemporarySummary[] = [];
  const ids = new Set<string>();
  await mkdir(resolve(dataDir, 'temporary'), {recursive: true});
  await rm(resolve(downloads, 'temporary'), {recursive: true, force: true});
  await mkdir(resolve(downloads, 'temporary'), {recursive: true});
  for (const source of sources) {
    if (!/^temp-[a-z0-9-]+$/.test(source.id) || ids.has(source.id)) throw new Error('Invalid or duplicate temporary ID');
    if (!/^[a-z0-9-]+\.log$/.test(source.file)) throw new Error('Invalid source filename');
    ids.add(source.id);
    const raw = await readFile(resolve(sourceDir, source.file), 'utf8');
    const run = parseRollout(raw, source);
    await writeFile(resolve(dataDir, 'runs', `${run.id}.json`), JSON.stringify(run));
    await copyFile(resolve(sourceDir, source.file), resolve(downloads, 'temporary', `${run.id}.log`));
    index.push({id: run.id, messageCount: run.messageCount, ...run.temporary!});
  }
  await writeFile(resolve(dataDir, 'temporary/index.json'), JSON.stringify(index));
  console.log(`Exported ${index.length} temporary archive transcripts, excluded from study totals.`);
}
