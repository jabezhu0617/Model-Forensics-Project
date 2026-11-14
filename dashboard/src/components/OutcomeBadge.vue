<script setup lang="ts">defineProps<{outcome:string}>();</script>
<template><span :class="['outcome',outcome]">{{outcome}}</span></template>
