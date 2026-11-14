import { chromium } from 'playwright-core';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { Dataset, Run, TemporarySummary } from '../src/types';
const base=process.argv[2]??'http://127.0.0.1:8788';
const out=resolve(import.meta.dir,'../screenshots');await mkdir(out,{recursive:true});
const manifest=JSON.parse(await readFile(resolve(import.meta.dir,'../public/data/manifest.json'),'utf8')) as {worstRun:{id:string;bytes:number}};
const d=JSON.parse(await readFile(resolve(import.meta.dir,'../public/data/index.json'),'utf8')) as Dataset;
const browser=process.env.CHROME_CDP_URL
  ?await chromium.connectOverCDP(process.env.CHROME_CDP_URL)
  :await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
const annotationRequests:string[]=[];page.on('request',request=>{if(request.url().includes('/api/annotations'))annotationRequests.push(request.url());});
const errors:string[]=[];const capture=(p:typeof page)=>{p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});p.on('pageerror',e=>errors.push(e.message));};capture(page);
async function visit(path:string,name:string){const start=Date.now();await page.goto(base+path,{waitUntil:'networkidle'});await page.locator('.page-heading h1').waitFor();await page.screenshot({path:resolve(out,`${name}.png`)});console.log(`${name}: ${Date.now()-start}ms`);}
function assert(condition:unknown,message:string):asserts condition{if(!condition)throw new Error(message);}
async function assertReadOnlyTranscript(){
  assert(await page.locator('.annotation-panel,.selection-note').count()===0,'Note panel still displayed');
  assert(await page.getByRole('button',{name:/Add note|Share note|Annotate selected/}).count()===0,'Note control still displayed');
  const widths=await page.evaluate(()=>({column:document.querySelector('.transcript-column')!.getBoundingClientRect().width,layout:document.querySelector('.transcript-layout')!.getBoundingClientRect().width}));
  assert(Math.abs(widths.column-widths.layout)<1,'Transcript does not use the full available width');
}
try{
  await visit('/#/','overview');assert(await page.locator('.comparisons tbody tr').count()===31,'Expected 31 hypotheses');
  assert(JSON.stringify(await page.locator('.chart-group').evaluateAll(nodes=>nodes.map(n=>(n as HTMLElement).dataset.group)))===JSON.stringify(['Baseline','H0','H1','H2','H3','H4']),'Incorrect chart group order');
  const bars=await page.locator('.result-bar').evaluateAll(nodes=>nodes.map(node=>({id:(node as HTMLElement).dataset.experiment,count:Number((node as HTMLElement).dataset.count),total:Number((node as HTMLElement).dataset.total),height:Number(node.querySelector('.bar-fill')?.getAttribute('height'))})));
  assert(bars.length===11,'Expected one baseline bar and ten intervention bars');
  for(const bar of bars){
    const source=d.experiments.find(e=>e.id===bar.id);
    assert(source&&source.round===0,'Chart included a combined hypothesis or an unknown experiment');
    assert(bar.count===source.counts.concealed&&bar.total===source.runs.length,'Chart count or denominator differs from study data');
    assert(Math.abs(bar.height-source.counts.concealed/source.runs.length*236)<.01,'Bar height differs from its concealment rate');
  }
  await page.locator('.result-bar[data-experiment="r1-h3-prior-self-commitment"]').click();
  await page.waitForURL('**/#/experiment/r1-h3-prior-self-commitment');
  await page.locator('.run-table tbody tr').first().waitFor();
  assert(await page.locator('.run-table tbody tr').count()===10,'Chart link did not open its ten trial records');
  await visit('/#/','overview-chart');
  await page.getByRole('button',{name:'Round 4',exact:true}).click();assert(await page.locator('.comparisons tbody tr').count()===1,'Round filtering failed');
  await visit('/#/hypothesis/r1-combined-round4-pair1','hypothesis');await page.locator('.arm-card').first().waitFor();assert(await page.locator('.arm-card').count()===2,'Missing paired arms');
  await page.getByRole('link',{name:'Prompt comparison',exact:true}).click();assert(await page.locator('.input-column').count()===2,'Missing paired prompt inputs');await page.screenshot({path:resolve(out,'inputs.png')});
  await visit('/#/experiment/r1-baseline','baseline');assert(await page.locator('.run-table tbody tr').count()===60,'Missing baseline runs');
  await visit('/#/methods','methods');
  const examples=JSON.parse(await readFile(resolve(import.meta.dir,'../public/data/temporary/index.json'),'utf8')) as TemporarySummary[];
  await visit('/#/examples','temporary-index');assert(await page.locator('.temporary-card').count()===examples.length,'Temporary transcript index count changed');
  for(const example of examples){
    const raw=await readFile(resolve(import.meta.dir,`../public/data/runs/${example.id}.json`),'utf8');
    const imported=JSON.parse(raw) as Run;
    await visit(`/#/examples/${example.id}`,example.id);
    assert(await page.locator('.message-card').count()===imported.messageCount,'Missing archive blocks');
    assert(await page.locator('.message-card.kind-reasoning').count()===example.reasoningBlocks,'Missing reasoning traces');
    assert(await page.locator('.message-card.kind-tool-call').count()===example.toolCalls,'Missing tool calls');
    await assertReadOnlyTranscript();
    const colors=await page.locator('.transcript-legend .kind-key').evaluateAll(nodes=>nodes.map(node=>getComputedStyle(node).color));
    assert(new Set(colors).size===colors.length,'Message types need distinct colors');
    const firstCall=page.locator('.message-card.kind-tool-call').first();
    assert(await firstCall.locator('.message-text').count()===0,'Tool calls should start collapsed');
    await firstCall.getByRole('button',{name:/Show full text/}).click();
    assert(await firstCall.locator('.message-text').count()===1,'Tool call expansion failed');
    const log=await context.request.get(base+example.downloadUrl);
    assert((await log.text())===imported.text,'Full log download differs from imported source');
    const largest=imported.display_messages.reduce((a,b)=>a.segments[0]!.text.length>b.segments[0]!.text.length?a:b);
    const phrase=largest.segments[0]!.text.split('\n').filter(line=>line.length>35).at(-1)!.slice(0,45);
    await page.getByRole('searchbox',{name:'Find in transcript'}).fill(phrase);
    assert(await page.locator(`#message-${largest.index} .message-text`).count()===1,'Search did not expand the matching long result');
    await page.getByRole('searchbox',{name:'Find in transcript'}).fill('');
    await page.setViewportSize({width:390,height:844});await visit(`/#/examples/${example.id}`,`${example.id}-mobile`);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Temporary mobile page overflows');
    await page.setViewportSize({width:1440,height:1000});
  }
  await visit(`/#/run/${manifest.worstRun.id}`,'largest-transcript');
  const expand=page.getByRole('button',{name:/Show full text/});if(await expand.count())await expand.first().click();
  await page.getByRole('searchbox',{name:'Find in transcript'}).fill('questions');assert((await page.locator('.message-card.matched').count())>0,'Transcript search failed');
  await page.screenshot({path:resolve(out,'transcript-search.png')});
  await visit('/#/run/r1-baseline-0001','review');await assertReadOnlyTranscript();
  await page.setViewportSize({width:390,height:844});await visit('/#/','mobile-overview');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Chart causes mobile page overflow');
  const scrollArea=page.locator('.chart-scroll');await scrollArea.evaluate(el=>el.scrollLeft=el.scrollWidth);await page.screenshot({path:resolve(out,'mobile-chart-scrolled.png')});
  await visit('/#/run/r1-baseline-0001','mobile-review');await assertReadOnlyTranscript();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Mobile page overflows horizontally');
  assert(!annotationRequests.length,'Viewer still requests shared annotations');
  assert(!errors.length,`Browser errors: ${errors.join('\n')}`);
  console.log(`PASS: ${d.totalRuns} study runs, ${examples.length} temporary transcripts; page types, search, full-width read-only transcripts, no annotation requests, and mobile. Largest transcript: ${manifest.worstRun.bytes} bytes.`);
}finally{await browser.close();}
