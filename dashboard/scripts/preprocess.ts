import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir, rm, copyFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { load } from 'cheerio';
import type { Counts, Dataset, Experiment, Hypothesis, Run, RunSummary } from '../src/types';
import { exportTemporary } from './export-temporary';

// Study runs come only from the public viewer. Never open studies/*/sealed.
const root = resolve(import.meta.dir, '../..');
const reports = resolve(root, 'studies/main/reports');
const html = await readFile(resolve(reports, 'viewer.html'), 'utf8');
const embedded = load(html)('script#data').text();
if (!embedded) throw new Error('Viewer contains no embedded experiment data');
interface Entry {
  id: string; experiment: string; display_name?: string; pair_label?: string; title: string;
  requested: number; pages: Record<string,string>; round_id?: string;
  arm: null | { group: string; sign: '−'|'+'; score: number | null; point: number | null; attempt_count: number };
}
const entries = JSON.parse(embedded) as Entry[];
const dataDir = resolve(import.meta.dir, '../public/data');
const downloads = resolve(import.meta.dir, '../public/downloads');
await rm(dataDir, {recursive:true, force:true});
await mkdir(resolve(dataDir, 'runs'), {recursive:true});
await mkdir(resolve(dataDir, 'experiments'), {recursive:true});
await mkdir(downloads, {recursive:true});
const counts = (): Counts => ({concealed:0, reported:0, unresolved:0});
const experiments: Experiment[] = [];
const groups = new Map<string,Hypothesis>();
const manifest: Record<string,string> = {};
const totals = counts();
let worst = {id:'', bytes:0};
const output = async (file:string, value:unknown) => writeFile(file, JSON.stringify(value));
for (const entry of entries) {
  if (!/^[a-zA-Z0-9_-]+$/.test(entry.experiment)) throw new Error('Invalid experiment ID');
  const transcriptPage = entry.pages.transcripts;
  if (!transcriptPage) throw new Error(`Missing transcript page: ${entry.experiment}`);
  const records = JSON.parse(load(transcriptPage)('script#records').text()) as Run[];
  const runSummaries: RunSummary[] = [];
  const experimentCounts = counts();
  for (const record of records) {
    if (!/^[a-zA-Z0-9_-]+$/.test(record.id)) throw new Error('Invalid run ID');
    if (manifest[record.id]) throw new Error(`Duplicate run: ${record.id}`);
    const suspicious = record.submission?.suspicious_observations ?? '';
    const summary: RunSummary = {
      id:record.id, outcome:record.outcome, status:record.status, transcript_hash:record.transcript_hash,
      selected:record.selected, support:record.support, excerpt:suspicious.slice(0,260),
      messageCount:record.display_messages.length,
    };
    const complete: Run = {...record, ...summary, experiment:entry.experiment};
    await output(resolve(dataDir, 'runs', `${record.id}.json`), complete);
    const bytes = Buffer.byteLength(JSON.stringify(complete));
    if (bytes>worst.bytes) worst={id:record.id,bytes};
    runSummaries.push(summary);
    experimentCounts[record.outcome]++;
    totals[record.outcome]++;
    manifest[record.id]=record.transcript_hash;
  }
  const round = entry.round_id ? Number(entry.round_id.match(/round(\d+)/)?.[1] ?? 0) : 0;
  const group = entry.arm?.group ?? null;
  const label = entry.pair_label ?? (group?.match(/^H\d+$/) ? group : entry.display_name ?? 'R1 baseline');
  const experiment: Experiment = {
    id:entry.experiment, label, group, round, sign:entry.arm?.sign??null,
    title:entry.title, score:entry.arm?.score??null, point:entry.arm?.point??null,
    runs:runSummaries, requested:entry.requested, counts:experimentCounts,
    attempts:entry.arm?.attempt_count??records.length,
  };
  if (entry.experiment === 'r1-baseline') {
    // Use the source report's unrounded, retry-inclusive interval.
    const $stats=load(entry.pages.statistics??'');
    const style=$stats('.axis[aria-label="Latest attempt per slot, point estimate and 95 percent Wilson interval"] .interval').attr('style')??'';
    const lower=Number(style.match(/left:([\d.]+)%/)?.[1])/100;
    const width=Number(style.match(/width:([\d.]+)%/)?.[1])/100;
    const upper=lower+width;
    if(!Number.isFinite(lower)||!Number.isFinite(upper)||lower<0||upper>1||lower>upper)throw new Error('Missing or invalid reported baseline confidence interval');
    experiment.interval95={method:'Wilson',lower,upper};
  }
  const $input=load(entry.pages.inputs??'');
  const inputs=$input('main section').toArray().map(section=>{
    const $section=$input(section).clone();
    const title=$section.find('h2').first().text();
    $section.find('h2').first().remove();
    $section.find('script,style,iframe').remove();
    return {title,html:$section.html()??''};
  });
  await output(resolve(dataDir,'experiments',`${experiment.id}.json`), {...experiment,inputs});
  // Keep original per-experiment pages as evidence downloads, without browser scripts.
  for (const tab of ['summary','inputs','statistics','accounting']) {
    const original=entry.pages[tab];
    if (!original) continue;
    const $=load(original);$('script,nav.view-tabs').remove();
    $('a').each((_,a)=>{const href=$(a).attr('href');if(href&&!/^https?:/.test(href))$(a).removeAttr('href');});
    await writeFile(resolve(downloads,`${entry.experiment}-${tab}.html`),$.html());
  }
  experiments.push(experiment);
  if (group) {
    const previous=groups.get(group);
    if(previous) previous.arms.push(experiment.id);
    else groups.set(group,{id:group,label,title:entry.title,round,score:entry.arm?.score??null,arms:[experiment.id]});
  }
}
const reportFiles = [
  ['hypotheses','Hypotheses & original screens','hypotheses.md'],
  ['round1','Round 1 · Pairs','r1-paired-round1-results.md'],
  ['round2','Round 2 · Triples','r1-combined-round2-results.md'],
  ['round3','Round 3 · Four hypotheses','r1-combined-round3-results.md'],
  ['round4','Round 4 · Five hypotheses','r1-combined-round4-results.md'],
] as const;
const publicReports=[];
for(const [id,title,filename] of reportFiles){
  const location=id==='hypotheses'?resolve(root,filename):resolve(reports,filename);
  publicReports.push({id,title,content:await readFile(location,'utf8')});
}
await copyFile(resolve(reports,'viewer-laptop.zip'),resolve(downloads,'viewer-laptop.zip'));
let sourceCommit='unknown';
try {sourceCommit=execFileSync('git',['log','-1','--format=%h','--','studies/main/reports/viewer.html'],{cwd:root,encoding:'utf8'}).trim();}catch{}
const version=createHash('sha256').update(html).digest('hex').slice(0,16);
const dataset: Dataset={
  version,sourceCommit,sourceRepository:'https://github.com/jabezhu0617/Model-Forensics-Project',
  repository:'https://github.com/vncntt/Model-Forensics-Project',totalRuns:Object.keys(manifest).length,
  totalExperiments:experiments.length,counts:totals,experiments,
  hypotheses:[...groups.values()].sort((a,b)=>a.round-b.round||(b.score??0)-(a.score??0)||a.label.localeCompare(b.label)),
  reports:publicReports,
};
await output(resolve(dataDir,'index.json'),dataset);
await output(resolve(dataDir,'manifest.json'),{version,runs:manifest,worstRun:worst});
await exportTemporary(dataDir, downloads);
console.log(`Exported ${dataset.totalExperiments} experiments, ${dataset.hypotheses.length} hypotheses, ${dataset.totalRuns} complete transcripts. Largest run: ${worst.id} (${worst.bytes} bytes).`);
