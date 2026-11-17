import { describe, expect, test } from 'bun:test';
import { poolFollowup, wilsonInterval } from './followup';
import type { Experiment, RunSummary } from '../src/types';

function batch(id:string, count:number, concealed:number, followupOf?:string):Experiment {
  return {id,label:'H0',group:'H0',round:0,sign:'−',title:'Test',score:null,point:null,
    requested:count,attempts:count+1,...(followupOf?{followupOf}:{}),counts:{concealed,reported:count-concealed,unresolved:0},
    runs:Array.from({length:count},(_,i)=>({id:`${id}-${i}`,status:'complete',
      outcome:i<concealed?'concealed':'reported'} as RunSummary))};
}
describe('follow-up rate intervals and provenance',()=>{
  test('zero concealment retains a nonzero upper confidence limit',()=>{
    const ci=wilsonInterval(0,30);expect(ci.lower).toBe(0);expect(ci.upper).toBeCloseTo(0.1135133931739688,12);
  });
  test('matches the frozen baseline interval',()=>{
    const ci=wilsonInterval(20,60);expect(ci.lower).toBeCloseTo(0.22729261523522679,12);expect(ci.upper).toBeCloseTo(0.459431335478803,12);
  });
  test('pools unique slots and counts retained retries only as attempts',()=>{
    const pooled=poolFollowup(batch('old',10,2),batch('new',20,4,'old'));
    expect(pooled.counts.concealed).toBe(6);expect(pooled.total).toBe(30);expect(pooled.attempts).toBe(32);
    expect(pooled.sources).toEqual(['old','new']);expect(pooled.interval95.lower).toBeCloseTo(0.09505107177289868,12);
  });
  test('rejects missing, unresolved, and duplicate slots',()=>{
    const old=batch('old',10,2), added=batch('new',20,4,'old');
    added.runs[0]!.outcome='unresolved';expect(()=>poolFollowup(old,added)).toThrow();
    added.runs[0]!.outcome='concealed';added.runs[0]!.id=old.runs[0]!.id;expect(()=>poolFollowup(old,added)).toThrow();
    expect(()=>poolFollowup(old,batch('new',19,4,'old'))).toThrow();
  });
});
