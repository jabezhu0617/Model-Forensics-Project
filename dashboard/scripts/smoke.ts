import { chromium } from 'playwright-core';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import type { Annotation, Dataset } from '../src/types';
const base=process.argv[2]??'http://127.0.0.1:8788';
const out=resolve(import.meta.dir,'../screenshots');await mkdir(out,{recursive:true});
const manifest=JSON.parse(await readFile(resolve(import.meta.dir,'../public/data/manifest.json'),'utf8')) as {worstRun:{id:string;bytes:number}};
const d=JSON.parse(await readFile(resolve(import.meta.dir,'../public/data/index.json'),'utf8')) as Dataset;
const browser=process.env.CHROME_CDP_URL
  ?await chromium.connectOverCDP(process.env.CHROME_CDP_URL)
  :await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
const errors:string[]=[];const capture=(p:typeof page)=>{p.on('console',m=>{if(m.type()==='error')errors.push(m.text());});p.on('pageerror',e=>errors.push(e.message));};capture(page);
async function visit(path:string,name:string){const start=Date.now();await page.goto(base+path,{waitUntil:'networkidle'});await page.locator('.page-heading h1').waitFor();await page.screenshot({path:resolve(out,`${name}.png`)});console.log(`${name}: ${Date.now()-start}ms`);}
function assert(condition:unknown,message:string):asserts condition{if(!condition)throw new Error(message);}
try{
  await visit('/#/','overview');assert(await page.locator('.comparisons tbody tr').count()===31,'Expected 31 hypotheses');
  await page.getByRole('button',{name:'Round 4',exact:true}).click();assert(await page.locator('.comparisons tbody tr').count()===1,'Round filtering failed');
  await visit('/#/hypothesis/r1-combined-round4-pair1','hypothesis');assert(await page.locator('.arm-card').count()===2,'Missing paired arms');
  await page.getByRole('link',{name:'Prompt comparison',exact:true}).click();assert(await page.locator('.input-column').count()===2,'Missing paired prompt inputs');await page.screenshot({path:resolve(out,'inputs.png')});
  await visit('/#/experiment/r1-baseline','baseline');assert(await page.locator('.run-table tbody tr').count()===60,'Missing baseline runs');
  await visit('/#/methods','methods');
  await visit(`/#/run/${manifest.worstRun.id}`,'largest-transcript');
  const expand=page.getByRole('button',{name:/Show full text/});if(await expand.count())await expand.first().click();
  await page.getByRole('searchbox',{name:'Find in transcript'}).fill('questions');assert((await page.locator('.message-card.matched').count())>0,'Transcript search failed');
  await page.screenshot({path:resolve(out,'transcript-search.png')});
  await visit('/#/run/r1-baseline-0001','review');
  await page.evaluate(()=>{const el=document.querySelector('.message-text');if(!el)throw Error('No transcript text');const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let node=walker.nextNode();while(node&&(node.textContent?.length??0)<15)node=walker.nextNode();if(!node)throw Error('No transcript text');const range=document.createRange();range.setStart(node,0);range.setEnd(node,15);const s=window.getSelection();s?.removeAllRanges();s?.addRange(range);el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));});
  assert(await page.locator('.selected-quote').count()===1,'Evidence selection failed');
  await page.getByLabel('Your note',{exact:true}).fill('Browser sync check');await page.getByLabel('Display name',{exact:false}).fill('Browser smoke');await page.getByRole('button',{name:'Share note',exact:true}).click();await page.locator('.shared-note').filter({hasText:'Browser sync check'}).waitFor();
  const other=await browser.newContext({viewport:{width:1200,height:900}}),second=await other.newPage();capture(second);
  await second.goto(base+'/#/run/r1-baseline-0001',{waitUntil:'networkidle'});await second.locator('.shared-note').filter({hasText:'Browser sync check'}).waitFor();
  await second.locator('.shared-note').filter({hasText:'Browser sync check'}).getByRole('button',{name:'Edit',exact:true}).click();await second.getByLabel('Your note',{exact:true}).fill('Edited from second browser');await second.getByRole('button',{name:'Save changes',exact:true}).click();await second.locator('.shared-note').filter({hasText:'Edited from second browser'}).waitFor();
  await page.getByRole('button',{name:'Refresh shared notes'}).click();await page.locator('.shared-note').filter({hasText:'Edited from second browser'}).waitFor();await page.screenshot({path:resolve(out,'shared-review.png')});
  const response=await context.request.get(base+'/api/annotations?run=r1-baseline-0001');const notes=(await response.json()) as {annotations:Annotation[]};const created=notes.annotations.find(n=>n.reviewer==='Browser smoke');if(created)await context.request.delete(base+`/api/annotations/${created.id}`,{data:{revision:created.revision}});
  await other.close();
  await page.setViewportSize({width:390,height:844});await visit('/#/','mobile-overview');await visit('/#/run/r1-baseline-0001','mobile-review');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Mobile page overflows horizontally');
  assert(!errors.length,`Browser errors: ${errors.join('\n')}`);
  console.log(`PASS: ${d.totalRuns} runs; page types, search, evidence selection, two-browser annotation sync, and mobile. Largest transcript: ${manifest.worstRun.bytes} bytes.`);
}finally{await browser.close();}
