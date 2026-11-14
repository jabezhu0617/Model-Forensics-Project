<script setup lang="ts">
import chartUrl from '../assets/plots/concealment.svg';
import chartData from '../assets/plots/concealment-data.json';
import { percent } from '../data';
const description = 'Concealment rate. ' + chartData.bars.map(bar => `${bar.group}${bar.series==='baseline'?'':` ${bar.series}`}: ${percent(bar.count,bar.total)} (${bar.count} of ${bar.total} trials)${bar.interval95?`, 95% ${bar.interval95.method} confidence interval ${(bar.interval95.lower*100).toFixed(1)}–${(bar.interval95.upper*100).toFixed(1)}%`:''}`).join('; ') + '. Error bars are shown only where reported in the source.';
</script>

<template>
  <figure class="results-chart" aria-labelledby="results-chart-heading">
    <h2 id="results-chart-heading">Concealment by hypothesis</h2>
    <div class="chart-scroll" tabindex="0" aria-label="Results graph; scroll horizontally on small screens">
      <img class="matplotlib-chart" :src="chartUrl" :alt="description" width="950" height="425">
    </div>
  </figure>
</template>

<style scoped>
.results-chart{margin:32px 0}
.results-chart h2{font-size:16px;margin-bottom:16px}
.chart-scroll{overflow-x:auto}
.matplotlib-chart{display:block;width:100%;min-width:580px;height:auto}
</style>
