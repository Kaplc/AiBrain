<script setup lang="ts">
import { onMounted, onUnmounted, ref, nextTick } from 'vue'
import { overviewViewModel } from './index'
import ModelCard from './ModelCard/ModelCard.vue'
import QdrantCard from './QdrantCard/QdrantCard.vue'
import FlaskCard from './FlaskCard/FlaskCard.vue'
import DeviceCard from './DeviceCard/DeviceCard.vue'
import BalanceCard from './BalanceCard/BalanceCard.vue'
import TokenCard from './TokenCard/TokenCard.vue'

onMounted(async () => {
  await nextTick()
  overviewViewModel.onMounted()
})
onUnmounted(() => overviewViewModel.onUnmounted())
</script>

<template>
  <div class="overview-wrap">
    <div class="overview-row">
      <ModelCard />
      <QdrantCard />
      <FlaskCard />
      <DeviceCard />
    </div>
    <div class="overview-row">
      <TokenCard />
    </div>
    <div class="overview-row">
      <BalanceCard />
    </div>
  </div>
</template>

<style scoped>
.overview-wrap { padding: 24px; flex: 1; display: flex; flex-direction: column; min-height: 0; overflow-y: auto; gap: 20px; box-sizing: border-box; }
.overview-row { display: flex; gap: 12px; flex-wrap: wrap; }
</style>
