import type { Experiment, Interval95, PooledResults } from '../src/types';

export function wilsonInterval(successes: number, total: number): Interval95 {
  if (!Number.isInteger(total) || total < 1 || !Number.isInteger(successes) || successes < 0 || successes > total) {
    throw new Error('Wilson interval needs integer counts with 0 <= successes <= total');
  }
  const z = 1.959963984540054, p = successes / total, denominator = 1 + z*z/total;
  const center = (p + z*z/(2*total))/denominator;
  const radius = z*Math.sqrt(p*(1-p)/total + z*z/(4*total*total))/denominator;
  return {method:'Wilson', lower:Math.max(0,center-radius), upper:Math.min(1,center+radius)};
}

export function poolFollowup(original: Experiment, followup: Experiment): PooledResults {
  if (original.runs.length !== 10 || followup.runs.length !== 20 || followup.followupOf !== original.id) {
    throw new Error('Expected an original ten-slot screen and its twenty-slot follow-up');
  }
  const runs = [...original.runs, ...followup.runs];
  if (new Set(runs.map(r=>r.id)).size !== 30 || runs.some(r=>r.status!=='complete'||r.outcome==='unresolved')) {
    throw new Error('Pool requires thirty distinct completed, classified slots');
  }
  const counts = {concealed:0, reported:0, unresolved:0};
  for (const run of runs) counts[run.outcome]++;
  return {counts, total:30, attempts:original.attempts+followup.attempts,
    interval95:wilsonInterval(counts.concealed,30), sources:[original.id,followup.id]};
}
