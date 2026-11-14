import { afterEach, beforeEach, expect, test } from 'bun:test';
import { Database } from 'bun:sqlite';
import { readFileSync } from 'node:fs';
import { handle, type Env } from './annotations';
import type { Annotation } from '../src/types';
let sqlite:Database,env:Env;
const hash='a'.repeat(64),runId='test-run-0001';
const payload={run_id:runId,transcript_hash:hash,quote:'exact evidence',note:'Important observation',reviewer:'Reviewer',outcome:null};
beforeEach(()=>{
  sqlite=new Database(':memory:');sqlite.exec(readFileSync(new URL('../migrations/0001_annotations.sql',import.meta.url),'utf8'));
  function stmt(sql:string,values:unknown[]=[]):D1PreparedStatement {
    return {bind:(...args:unknown[])=>stmt(sql,args),first:async()=>sqlite.query(sql).get(...values as never[]),all:async()=>({results:sqlite.query(sql).all(...values as never[]),success:true}),_sql:sql,_values:values} as unknown as D1PreparedStatement;
  }
  const DB={prepare:stmt,batch:async(statements:(D1PreparedStatement&{_sql:string;_values:unknown[]})[])=>sqlite.transaction(()=>statements.map(s=>({results:sqlite.query(s._sql).all(...s._values as never[]),success:true})))()} as unknown as D1Database;
  const ASSETS={fetch:async(request:Request)=>new URL(request.url).pathname===`/data/runs/${runId}.json`?Response.json({id:runId,transcript_hash:hash,text:'Contains exact evidence in the transcript.'}):new Response('',{status:404})} as Fetcher;
  env={DB,ASSETS};
});
afterEach(()=>sqlite.close());
const request=(path:string,method='GET',body?:unknown)=>new Request(`https://viewer.example/api/${path}`,{method,...(body===undefined?{}:{body:JSON.stringify(body),headers:{'Content-Type':'application/json','Origin':'https://viewer.example'}})});
const result=<T>(response:Response)=>response.json() as Promise<T>;
test('public annotation survives reload, keeps history, prevents stale overwrite, and supports restoration',async()=>{
  const created=await handle(request('annotations','POST',payload),env);expect(created.status).toBe(201);const first=(await result<{annotation:Annotation}>(created)).annotation;
  const listed=await handle(request(`annotations?run=${runId}`),env);expect((await result<{annotations:Annotation[]}>(listed)).annotations).toHaveLength(1);
  const edit=await handle(request(`annotations/${first.id}`,'PATCH',{...payload,note:'Edited by another reader',revision:1}),env);expect(edit.status).toBe(200);
  const stale=await handle(request(`annotations/${first.id}`,'PATCH',{...payload,note:'Stale overwrite',revision:1}),env);expect(stale.status).toBe(409);
  const history=await handle(request(`annotations/${first.id}/history`),env);expect((await result<{history:Annotation[]}>(history)).history.map(r=>r.note)).toEqual(['Edited by another reader','Important observation']);
  expect((await handle(request(`annotations/${first.id}`,'DELETE',{revision:2}),env)).status).toBe(200);
  expect((await result<{annotations:Annotation[]}>(await handle(request(`annotations?run=${runId}`),env))).annotations).toHaveLength(0);
  expect((await result<{annotations:Annotation[]}>(await handle(request(`annotations?run=${runId}&include_deleted=1`),env))).annotations).toHaveLength(1);
  expect((await handle(request(`annotations/${first.id}`,'PATCH',{...payload,revision:3}),env)).status).toBe(200);
});
test('rejects unsupported evidence, changed transcript hashes and cross-origin writes',async()=>{
  expect((await handle(request('annotations','POST',{...payload,quote:'invented evidence'}),env)).status).toBe(400);
  expect((await handle(request('annotations','POST',{...payload,transcript_hash:'b'.repeat(64)}),env)).status).toBe(409);
  expect((await handle(new Request('https://viewer.example/api/annotations',{method:'POST',headers:{'Content-Type':'application/json','Origin':'https://other.example'},body:JSON.stringify(payload)}),env)).status).toBe(403);
});
test('bounds inputs and treats SQL-like note text as data',async()=>{
  expect((await handle(request('annotations','POST',{...payload,note:'x'.repeat(8001)}),env)).status).toBe(400);
  expect((await handle(request('annotations','POST',{...payload,note:"'); DROP TABLE annotations; --"}),env)).status).toBe(201);
  expect((await handle(request('health'),env)).status).toBe(200);
});
