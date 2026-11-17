import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { load } from 'cheerio';
import type { Dataset, Experiment, Run } from '../src/types';
import { poolFollowup, wilsonInterval } from './followup';
import { studyScope } from '../src/study-scope';
const root=resolve(import.meta.dir,'..');
const d=JSON.parse(await readFile(resolve(root,'public/data/index.json'),'utf8')) as Dataset;
const source=load(await readFile(resolve(root,'../studies/main/reports/viewer.html'),'utf8'));
const entries=JSON.parse(source('script#data').text()) as {experiment:string;pages:Record<string,string>}[];
let verified=0;
const sourceCounts={concealed:0,reported:0,unresolved:0};
for(const e of entries){
  const records=JSON.parse(load(e.pages.transcripts??'')('script#records').text()) as Run[];
  for(const r of records){
    const exported=JSON.parse(await readFile(resolve(root,'public/data/runs',`${r.id}.json`),'utf8')) as Run;
    for(const field of ['text','transcript_hash','outcome','display_messages','submission'] as const){
      if(JSON.stringify(r[field])!==JSON.stringify(exported[field]))throw new Error(`Changed ${field}: ${r.id}`);
    }
    verified++;
    sourceCounts[r.outcome]++;
  }
}
if(verified!==d.totalRuns||entries.length!==d.totalExperiments)throw new Error('Counts do not match');
const baseline=d.experiments.find(e=>e.id==='r1-baseline');
if(!baseline||baseline.counts.concealed!==20||baseline.runs.length!==60)throw new Error('Baseline changed');
if(d.hypotheses.length!==31||JSON.stringify(d.counts)!==JSON.stringify(sourceCounts))throw new Error('Unexpected aggregate counts');
const followups=d.experiments.filter(e=>e.followupOf);
if(followups.length && (followups.length!==10||d.totalRuns!==880||d.totalExperiments!==73))throw new Error('Incomplete follow-up export');
if(!followups.length && (d.totalRuns!==680||d.counts.concealed!==113||d.counts.reported!==567))throw new Error('Original export changed');
for(const added of followups){
  const original=d.experiments.find(e=>e.id===added.followupOf)!;
  if(original.followupId!==added.id||JSON.stringify(original.pooled)!==JSON.stringify(poolFollowup(original,added)))throw new Error('Incorrect pooled follow-up counts, interval or provenance');
}
console.log(`Verified all ${verified} transcripts, source hashes, message content, submissions and outcomes against the original export.`);
const scopes=studyScope(d);
if(scopes.focus.totalRuns!==360||scopes.focus.hypotheses.length!==5||scopes.archive.totalRuns!==520||scopes.archive.hypotheses.length!==26)throw new Error('Incorrect active/archive scope');
for(const [scope,filename] of [['focus','baseline-h0-h4-results.json'],['archive','combination-archive-results.json']] as const){
  const exported=JSON.parse(await readFile(resolve(root,'public/downloads',filename),'utf8'));
  if(JSON.stringify(exported.experiments)!==JSON.stringify(scopes[scope].experiments)||exported.totalRuns!==scopes[scope].totalRuns)throw new Error('Scope download does not match source batches');
}
if(d.reports.filter(r=>r.scope==='focus').some(r=>/^round|combinations/.test(r.id)))throw new Error('Archived combination report appears in the current focus');

const plotDir=resolve(root,'src/assets/plots');
const plot=JSON.parse(await readFile(resolve(plotDir,'concealment-data.json'),'utf8')) as {dataset_version:string;baseline_reference:{experiment:string;rate:number;style:string};bars:{experiment:string;count:number;total:number;rate:number;sources:string[];interval95:Experiment['interval95']|null}[];svg_sha256:string;png_sha256:string};
if(plot.dataset_version!==d.version)throw new Error('Plot dataset version is stale');
if(plot.baseline_reference.experiment!=='r1-baseline'||plot.baseline_reference.style!=='dotted'||Math.abs(plot.baseline_reference.rate-20/60*100)>1e-10)throw new Error('Baseline reference line does not match the frozen baseline');
if(!(await readFile(resolve(plotDir,'concealment.svg'),'utf8')).includes('id="baseline-reference"'))throw new Error('Missing baseline reference in rendered graph');
const expectedIds=['r1-baseline',...['H0','H1','H2','H3','H4'].flatMap(id=>{
  const h=d.hypotheses.find(h=>h.id===id&&h.round===0);
  if(!h)throw new Error(`Missing hypothesis ${id}`);
  return ['−','+'].map(sign=>d.experiments.find(e=>h.arms.includes(e.id)&&e.sign===sign)!.id);
})];
if(JSON.stringify(plot.bars.map(b=>b.experiment))!==JSON.stringify(expectedIds))throw new Error('Matplotlib chart has incorrect experiment groups');
for(const bar of plot.bars){
  const e=d.experiments.find(e=>e.id===bar.experiment)!;
  const count=e.pooled?.counts.concealed??e.counts.concealed,total=e.pooled?.total??e.runs.length;
  if(bar.count!==count||bar.total!==total||Math.abs(bar.rate-count/total*100)>1e-10)throw new Error('Matplotlib chart is stale; rerun scripts/plot-results.py');
  if(JSON.stringify(bar.interval95)!==JSON.stringify(e.pooled?.interval95??e.interval95))throw new Error('Matplotlib confidence interval differs from source export');
  if(JSON.stringify(bar.sources)!==JSON.stringify(e.pooled?.sources??[e.id]))throw new Error('Plot source experiments differ');
  const expected=wilsonInterval(count,total);
  if(!bar.interval95||Math.abs(bar.interval95.lower-expected.lower)>1e-12||Math.abs(bar.interval95.upper-expected.upper)>1e-12)throw new Error('Incorrect Wilson interval');
}
const intervals=plot.bars.filter(bar=>bar.interval95);
if(intervals.length!==11||intervals[0]!.experiment!=='r1-baseline')throw new Error('Expected 95% intervals for all eleven bars');
const ci=intervals[0]!.interval95!;
if(ci.method!=='Wilson'||Math.abs(ci.lower-0.22729261523522677)>1e-12||Math.abs(ci.upper-0.45943133547880297)>1e-12)throw new Error('Baseline confidence interval differs from the source report');
for(const format of ['svg','png'] as const){
  const hash=createHash('sha256').update(await readFile(resolve(plotDir,`concealment.${format}`))).digest('hex');
  if(hash!==plot[`${format}_sha256`])throw new Error(`Matplotlib ${format} does not match its verified data`);
}
console.log('Verified all 11 Matplotlib bars and Wilson confidence intervals, pooled follow-up provenance, and both image checksums against the exported study data.');
