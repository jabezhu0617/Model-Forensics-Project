<script setup lang="ts">
import chartUrl from '../assets/plots/concealment.svg';
import chartData from '../assets/plots/concealment-data.json';
import { percent } from '../data';
defineProps<{replacementCount?:number}>();
const bars=chartData.bars as (typeof chartData.bars[number]&{label?:string|null})[];
const hasVariants=bars.some(bar=>bar.label);
const hasRewrites=bars.some(bar=>bar.label?.endsWith('R'));
const hypotheses=[...new Set(bars.filter(bar=>bar.series!=='baseline').map(bar=>bar.group))];
const description='Concealment rate. '+bars.map(bar=>`${bar.label??(bar.group+(bar.series==='baseline'?'':' original '+bar.series))}: ${percent(bar.count,bar.total)} (${bar.count} of ${bar.total} trials)${bar.interval95?`, 95% ${bar.interval95.method} confidence interval ${(bar.interval95.lower*100).toFixed(1)}–${(bar.interval95.upper*100).toFixed(1)}%`:''}`).join('; ')+'. The dotted horizontal line marks the 33.3% baseline.';
</script>

<template>
  <figure class="results-chart" aria-labelledby="results-chart-heading">
    <h2 id="results-chart-heading">Concealment by hypothesis</h2>
    <div class="chart-scroll" tabindex="0" aria-label="Results graph; scroll horizontally on small screens">
      <img :class="['matplotlib-chart',{'with-variants':hasVariants}]" :src="chartUrl" :alt="description" width="950" height="425">
    </div>
    <figcaption v-if="hasVariants">Bar labels show concealed / completed trials. Striped bars are B variants<template v-if="hasRewrites"> and stippled bars are R rewrites</template>. The dotted line marks the 33.3% baseline. <RouterLink to="/methods?report=b-variants">{{replacementCount?'B first pass':'B results'}}</RouterLink><template v-if="hasRewrites"> · <RouterLink to="/methods?report=r-rewrites">{{replacementCount?'R first pass':'R results'}}</RouterLink></template></figcaption>
    <figcaption v-else-if="bars.some(bar=>bar.total===30)">The dotted line marks the 33.3% baseline. H0–H4 pool the original 10 trials and 20 follow-up trials per direction. <RouterLink to="/methods?report=followup">Read the follow-up results →</RouterLink></figcaption>
    <nav v-if="hasVariants" aria-label="Explore hypothesis results" class="chart-hypothesis-links">
      <span>View prompt results:</span>
      <RouterLink v-for="group in hypotheses" :key="group" :to="'/hypothesis/'+group">{{group}}</RouterLink>
    </nav>
  </figure>
</template>

<style scoped>
.results-chart{margin:32px 0}
.results-chart h2{font-size:16px;margin-bottom:16px}
.chart-scroll{overflow-x:auto}
.matplotlib-chart{display:block;width:100%;min-width:580px;height:auto}
.matplotlib-chart.with-variants{min-width:920px}
.chart-hypothesis-links{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-top:12px;font-size:12px}
.chart-hypothesis-links a{padding:4px 9px;border:1px solid var(--border);border-radius:4px}
</style>
