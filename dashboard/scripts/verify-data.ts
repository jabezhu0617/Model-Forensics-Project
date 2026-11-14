import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { load } from 'cheerio';
import type { Dataset, Run } from '../src/types';
const root=resolve(import.meta.dir,'..');
const d=JSON.parse(await readFile(resolve(root,'public/data/index.json'),'utf8')) as Dataset;
const source=load(await readFile(resolve(root,'../studies/main/reports/viewer.html'),'utf8'));
const entries=JSON.parse(source('script#data').text()) as {experiment:string;pages:Record<string,string>}[];
let verified=0;
for(const e of entries){
  const records=JSON.parse(load(e.pages.transcripts??'')('script#records').text()) as Run[];
  for(const r of records){
    const exported=JSON.parse(await readFile(resolve(root,'public/data/runs',`${r.id}.json`),'utf8')) as Run;
    for(const field of ['text','transcript_hash','outcome','display_messages','submission'] as const){
      if(JSON.stringify(r[field])!==JSON.stringify(exported[field]))throw new Error(`Changed ${field}: ${r.id}`);
    }
    verified++;
  }
}
if(verified!==d.totalRuns||entries.length!==d.totalExperiments)throw new Error('Counts do not match');
const baseline=d.experiments.find(e=>e.id==='r1-baseline');
if(!baseline||baseline.counts.concealed!==20||baseline.runs.length!==60)throw new Error('Baseline changed');
if(d.hypotheses.length!==31||d.counts.concealed!==113||d.counts.reported!==567)throw new Error('Unexpected aggregate counts');
console.log(`Verified all ${verified} transcripts, source hashes, message content, submissions and outcomes against the original export.`);

const plotDir=resolve(root,'src/assets/plots');
const plot=JSON.parse(await readFile(resolve(plotDir,'concealment-data.json'),'utf8')) as {bars:{experiment:string;count:number;total:number;rate:number}[];svg_sha256:string;png_sha256:string};
const expectedIds=['r1-baseline',...['H0','H1','H2','H3','H4'].flatMap(id=>{
  const h=d.hypotheses.find(h=>h.id===id&&h.round===0);
  if(!h)throw new Error(`Missing hypothesis ${id}`);
  return ['−','+'].map(sign=>d.experiments.find(e=>h.arms.includes(e.id)&&e.sign===sign)!.id);
})];
if(JSON.stringify(plot.bars.map(b=>b.experiment))!==JSON.stringify(expectedIds))throw new Error('Matplotlib chart has incorrect experiment groups');
for(const bar of plot.bars){
  const e=d.experiments.find(e=>e.id===bar.experiment)!;
  if(bar.count!==e.counts.concealed||bar.total!==e.runs.length||Math.abs(bar.rate-bar.count/bar.total*100)>1e-10)throw new Error('Matplotlib chart is stale; rerun scripts/plot-results.py');
}
for(const format of ['svg','png'] as const){
  const hash=createHash('sha256').update(await readFile(resolve(plotDir,`concealment.${format}`))).digest('hex');
  if(hash!==plot[`${format}_sha256`])throw new Error(`Matplotlib ${format} does not match its verified data`);
}
console.log('Verified all 11 Matplotlib bars and both image checksums against the exported study data.');
