<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { percent } from '../data';
import type { Dataset, Experiment } from '../types';

const props = defineProps<{data: Dataset}>();
const router = useRouter();
type Series = 'baseline' | 'negative' | 'positive';
interface Bar { series: Series; label: string; experiment: Experiment | undefined }
interface Group { label: string; bars: Bar[] }
const baseline = computed(() => props.data.experiments.find(e => e.id === 'r1-baseline'));
const groups = computed<Group[]>(() => [
  {label: 'Baseline', bars: [{series: 'baseline', label: 'Baseline', experiment: baseline.value}]},
  ...Array.from({length: 5}, (_, i) => {
    const label = `H${i}`;
    const hypothesis = props.data.hypotheses.find(h => h.id === label && h.round === 0);
    const arm = (sign: '−' | '+') => props.data.experiments.find(e => hypothesis?.arms.includes(e.id) && e.sign === sign);
    return {label, bars: [
      {series: 'negative' as const, label: 'Negative', experiment: arm('−')},
      {series: 'positive' as const, label: 'Positive', experiment: arm('+')},
    ]};
  }),
]);

const width = 900, height = 362, left = 72, right = 26, top = 34, bottom = 270;
const plotWidth = width - left - right, groupWidth = plotWidth / 6, barWidth = 38, gap = 8;
const ticks = [0, 20, 40, 60, 80, 100];
const y = (rate: number) => bottom - rate / 100 * (bottom - top);
const rate = (bar: Bar) => bar.experiment?.runs.length ? bar.experiment.counts.concealed / bar.experiment.runs.length * 100 : null;
const center = (groupIndex: number) => left + groupWidth * (groupIndex + .5);
const x = (groupIndex: number, barIndex: number, count: number) => center(groupIndex) - (count * barWidth + (count - 1) * gap) / 2 + barIndex * (barWidth + gap);
const summary = (group: Group, bar: Bar) => {
  const e = bar.experiment;
  return e ? `${group.label}${bar.series === 'baseline' ? '' : ` ${bar.label.toLowerCase()}`}: ${percent(e.counts.concealed, e.runs.length)} concealed (${e.counts.concealed} of ${e.runs.length} trials). Open experiment.` : `${group.label} ${bar.label}: no data.`;
};
const baselineRate = computed(() => baseline.value?.runs.length ? baseline.value.counts.concealed / baseline.value.runs.length * 100 : null);
</script>

<template>
  <section class="panel results-chart" aria-labelledby="results-chart-heading">
    <div class="panel-heading">
      <div><h2 id="results-chart-heading">Concealment by hypothesis</h2><p>Baseline and the negative (−) and positive (+) arms of H0–H4.</p></div>
      <div class="chart-legend" aria-label="Bar colors">
        <span class="series-baseline">Baseline</span><span class="series-negative">Negative (−)</span><span class="series-positive">Positive (+)</span>
      </div>
    </div>
    <div class="chart-scroll" tabindex="0" aria-label="Concealment chart; scroll horizontally on small screens">
      <svg class="concealment-chart" :viewBox="`0 0 ${width} ${height}`" role="group" aria-labelledby="results-chart-heading results-chart-description">
        <desc id="results-chart-description">Concealment rate from zero to one hundred percent. Six groups: baseline, H0, H1, H2, H3, and H4. Each hypothesis has a negative and a positive intervention. Bar labels show observed rates; hover or focus a bar for trial counts.</desc>
        <g class="chart-grid" aria-hidden="true">
          <g v-for="tick in ticks" :key="tick"><line :x1="left" :x2="width-right" :y1="y(tick)" :y2="y(tick)"/><text :x="left-12" :y="y(tick)+4" text-anchor="end">{{tick}}%</text></g>
          <text class="axis-title" :transform="`translate(18 ${(top+bottom)/2}) rotate(-90)`" text-anchor="middle">Concealment rate</text>
        </g>
        <line v-if="baselineRate!==null" class="baseline-reference" :x1="left" :x2="width-right" :y1="y(baselineRate)" :y2="y(baselineRate)" aria-hidden="true"/>
        <g v-for="(group,groupIndex) in groups" :key="group.label" class="chart-group" :data-group="group.label">
          <template v-for="(bar,barIndex) in group.bars" :key="bar.series">
            <a v-if="bar.experiment" :href="router.resolve(`/experiment/${bar.experiment.id}`).href" :aria-label="summary(group,bar)" :class="['result-bar',`series-${bar.series}`]" :data-count="bar.experiment.counts.concealed" :data-total="bar.experiment.runs.length" :data-experiment="bar.experiment.id">
              <title>{{summary(group,bar)}}</title>
              <rect class="bar-hit-area" :x="x(groupIndex,barIndex,group.bars.length)-4" :y="top-22" :width="barWidth+8" :height="bottom-top+47"/>
              <rect class="bar-fill" :x="x(groupIndex,barIndex,group.bars.length)" :y="y(rate(bar)??0)" :width="barWidth" :height="bottom-y(rate(bar)??0)" rx="3"/>
              <line v-if="rate(bar)===0" class="zero-bar" :x1="x(groupIndex,barIndex,group.bars.length)" :x2="x(groupIndex,barIndex,group.bars.length)+barWidth" :y1="bottom" :y2="bottom"/>
              <text class="bar-value" :x="x(groupIndex,barIndex,group.bars.length)+barWidth/2" :y="y(rate(bar)??0)-10" text-anchor="middle">{{percent(bar.experiment.counts.concealed,bar.experiment.runs.length)}}</text>
              <text v-if="bar.series!=='baseline'" class="bar-direction" :x="x(groupIndex,barIndex,group.bars.length)+barWidth/2" :y="bottom+19" text-anchor="middle">{{bar.series==='negative'?'−':'+'}}</text>
            </a>
            <text v-else :x="x(groupIndex,barIndex,group.bars.length)+barWidth/2" :y="bottom-10" text-anchor="middle" class="missing-value">—</text>
          </template>
          <text class="group-label" :x="center(groupIndex)" :y="bottom+43" text-anchor="middle">{{group.label}}</text>
          <text class="group-sample" :x="center(groupIndex)" :y="bottom+61" text-anchor="middle">{{group.bars.map(b=>`n=${b.experiment?.runs.length??'—'}`).join(' / ')}}</text>
        </g>
      </svg>
    </div>
    <p class="chart-caption">The dashed line marks the {{baseline?percent(baseline.counts.concealed,baseline.runs.length):'—'}} baseline. Signs describe the intended intervention direction; bars show observed outcomes. Select a bar to inspect its trials.</p>
  </section>
</template>

<style scoped>
.results-chart{margin-bottom:28px}
.panel-heading{align-items:flex-start;flex-wrap:wrap;padding-bottom:10px}
.chart-legend{display:flex;gap:17px;flex-wrap:wrap;font-size:11px;color:var(--muted);padding-top:3px}
.chart-legend span{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.chart-legend span::before{content:'';width:9px;height:9px;border-radius:2px;background:var(--bar-color)}
.series-baseline{--bar-color:#d98a2b}.series-negative{--bar-color:#cc5454}.series-positive{--bar-color:#32936b}
.chart-scroll{overflow-x:auto;padding:0 16px}
.concealment-chart{width:100%;min-width:650px;height:auto;font-family:inherit;overflow:visible}
.chart-grid line{stroke:#e9edf3;stroke-width:1}.chart-grid text{fill:#7b8695;font-size:11px;font-variant-numeric:tabular-nums}.chart-grid .axis-title{fill:#596679;font-size:12px}
.baseline-reference{stroke:#8b96a5;stroke-width:1;stroke-dasharray:5 5}
.bar-fill{fill:var(--bar-color)}.zero-bar{stroke:var(--bar-color);stroke-width:3}.bar-hit-area{fill:transparent}
.bar-value{fill:#39475c;font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;pointer-events:none}
.bar-direction{fill:#64748b;font-size:13px;pointer-events:none}.group-label{fill:#3e4b5c;font-size:13px;font-weight:600}.group-sample{fill:#8a94a2;font-size:10px;font-variant-numeric:tabular-nums}
.result-bar:hover .bar-fill,.result-bar:focus-visible .bar-fill{filter:brightness(.88)}.result-bar:focus-visible{outline:none}.result-bar:focus-visible .bar-hit-area{stroke:#315ec8;stroke-width:2;rx:4}
.missing-value{fill:#8a94a2}.chart-caption{font-size:11px;color:#7b8796;line-height:1.7;margin:0;padding:0 24px 20px;max-width:860px}
@media(max-width:650px){.panel-heading{padding:19px 17px 12px}.chart-legend{gap:13px;font-size:10px}.chart-scroll{padding:0 4px}.chart-caption{padding:0 17px 18px;font-size:10px}}
</style>
