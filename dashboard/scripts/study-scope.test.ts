import { expect, test } from 'bun:test';
import { readFile } from 'node:fs/promises';
import { studyScope } from '../src/study-scope';
import type { Dataset } from '../src/types';

test('current work contains baseline and all five thirty-trial hypotheses; combinations remain disjoint',async()=>{
  const data=JSON.parse(await readFile(new URL('../public/data/index.json',import.meta.url),'utf8')) as Dataset;
  const {focus,archive}=studyScope(data);
  expect(focus.hypotheses.map(h=>h.id).sort()).toEqual(['H0','H1','H2','H3','H4']);
  const variants=focus.experiments.filter(e=>e.variant);
  expect([0,5,10]).toContain(variants.length);
  expect(focus.totalRuns).toBe(360+30*variants.length);expect(focus.promptArms).toBe(11+variants.length);
  expect(focus.experiments.filter(e=>e.followupOf)).toHaveLength(10);
  expect(archive.hypotheses).toHaveLength(26);expect(archive.totalRuns).toBe(520);
  expect(focus.totalRuns+archive.totalRuns).toBe(data.totalRuns);
  const active=new Set(focus.experiments.flatMap(e=>e.runs.map(r=>r.id)));
  expect(archive.experiments.every(e=>e.runs.every(r=>!active.has(r.id)))).toBe(true);
  expect(focus.experiments.length+archive.experiments.length).toBe(data.experiments.length);
});
