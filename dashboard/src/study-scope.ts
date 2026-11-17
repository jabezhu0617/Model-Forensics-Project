import focus from '../../research-focus.json';
import type { Counts, Dataset, Experiment } from './types';

export function studyScope(data: Dataset) {
  const hypotheses=data.hypotheses.filter(h=>focus.hypotheses.includes(h.id));
  const combinations=data.hypotheses.filter(h=>h.round>0);
  const activeIds=new Set(hypotheses.flatMap(h=>h.arms));
  const archivedIds=new Set(combinations.flatMap(h=>h.arms));
  const experiments=data.experiments.filter(e=>e.id===focus.baseline||activeIds.has(e.id)||!!e.followupOf&&activeIds.has(e.followupOf));
  const archivedExperiments=data.experiments.filter(e=>archivedIds.has(e.id));
  const summarize=(items:Experiment[])=>{
    const counts:Counts={concealed:0,reported:0,unresolved:0};
    const ids=new Set<string>();
    for(const e of items)for(const r of e.runs){
      if(ids.has(r.id))throw new Error(`Duplicate source slot in study scope: ${r.id}`);
      ids.add(r.id);counts[r.outcome]++;
    }
    return {counts,totalRuns:ids.size};
  };
  return {
    focus:{hypotheses,experiments,promptArms:activeIds.size+1,...summarize(experiments)},
    archive:{hypotheses:combinations,experiments:archivedExperiments,promptArms:archivedIds.size,...summarize(archivedExperiments)},
  };
}
