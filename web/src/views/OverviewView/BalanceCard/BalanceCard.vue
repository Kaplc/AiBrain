<script setup lang="ts">
import { overviewViewModel } from '../index'

const card = overviewViewModel.balanceCard
</script>

<template>
  <div class="status-card">
    <div class="sc-label-row">
      <div class="sc-label">DeepSeek 余额</div>
      <span
        v-if="card.loading.value"
        class="badge-loading"
      >加载中</span>
      <span
        v-else-if="card.error.value"
        class="badge-err"
        :title="card.error.value"
      >不可用</span>
      <span
        v-else-if="card.available.value"
        class="badge-ok"
      >可用</span>
      <span
        v-else
        class="badge-err"
      >不可用</span>
      <button class="btn-refresh" @click="card.poll()" title="手动刷新">↻</button>
    </div>

    <!-- 加载中 -->
    <template v-if="card.loading.value">
      <div class="balance-value">--</div>
    </template>

    <!-- 错误状态 -->
    <template v-else-if="card.error.value">
      <div class="balance-value err">--</div>
      <div class="sc-sub" v-if="card.error.value.includes('API key')">请配置 Chat API Key</div>
    </template>

    <!-- 余额数据 -->
    <template v-else>
      <div class="balance-value">
        ¥ {{ card.formatBalance(card.balanceList.value[0]?.total_balance || '0') }}
      </div>
      <div class="balance-detail" v-if="card.balanceList.value.length > 0">
        <span>赠金: ¥{{ card.formatBalance(card.balanceList.value[0]?.granted_balance || '0') }}</span>
        <span>充值: ¥{{ card.formatBalance(card.balanceList.value[0]?.topped_up_balance || '0') }}</span>
      </div>
      <div class="today-cost" v-if="card.todayCost.value">
        <span class="tc-label">今日消耗</span>
        <span class="tc-value">¥{{ card.todayCost.value.total_cost.toFixed(2) }}</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.status-card {
  flex: 1;
  min-width: 280px;
  background: #1a1d27;
  border: 1px solid #2d3149;
  border-radius: 10px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
  text-align: left;
}
.sc-label-row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
}
.sc-label {
  font-size: 11px;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: .06em;
  font-weight: 600;
}
.sc-sub {
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}

/* 余额数值 */
.balance-value {
  font-size: 22px;
  font-weight: 700;
  color: #a78bfa;
}
.balance-value.err {
  color: #64748b;
}

/* 余额明细 */
.balance-detail {
  display: flex;
  gap: 16px;
  font-size: 10px;
  color: #64748b;
}

/* 今日消耗 */
.today-cost {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  padding-top: 8px;
  border-top: 1px solid #2d3149;
  width: 100%;
  font-size: 11px;
}
.tc-label {
  color: #64748b;
}
.tc-value {
  color: #f59e0b;
  font-weight: 700;
}
.tc-tokens {
  color: #64748b;
  font-size: 10px;
  margin-left: auto;
}

/* 徽章 */
.badge-ok {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: #22c55e22;
  color: #86efac;
  border: 1px solid #22c55e44;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
}
.badge-err {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: #ef444422;
  color: #fca5a5;
  border: 1px solid #ef444444;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
}
.badge-loading {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: #eab30822;
  color: #fde68a;
  border: 1px solid #eab30844;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
}

/* 刷新按钮 */
.btn-refresh {
  background: none;
  border: 1px solid #2d3149;
  color: #64748b;
  cursor: pointer;
  font-size: 11px;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  margin-left: 4px;
  flex-shrink: 0;
}
.btn-refresh:hover {
  color: #cbd5e1;
  border-color: #475569;
  background: #1e293b;
}
</style>
