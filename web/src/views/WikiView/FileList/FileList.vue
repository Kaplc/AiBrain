<script setup lang="ts">
import { wikiViewModel } from '../WikiViewModel'
</script>

<template>
  <div class="file-section">
    <div class="fs-header">
      <div class="fs-title">文件列表</div>
      <span class="ft-meta">{{ wikiViewModel.rawFiles.value.length }} 个文件</span>
    </div>
    <div class="table-wrap">
      <div v-if="wikiViewModel.loading.value && wikiViewModel.rawFiles.value.length === 0" class="mini-loading"></div>
      <div v-else-if="wikiViewModel.loadError.value" class="empty-state">加载失败，请检查后端连接</div>
      <div v-else-if="wikiViewModel.rawFiles.value.length === 0" class="empty-state">Wiki 目录为空</div>
      <table v-else class="file-table">
        <thead>
          <tr>
            <th style="width:40px"></th>
            <th @click="wikiViewModel.doSort('filename')">文件名{{ wikiViewModel.sortArrow('filename') }}</th>
            <th @click="wikiViewModel.doSort('sizeBytes')">大小{{ wikiViewModel.sortArrow('sizeBytes') }}</th>
            <th @click="wikiViewModel.doSort('modified')">修改时间{{ wikiViewModel.sortArrow('modified') }}</th>
            <th>预览</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="f in wikiViewModel.sortedFiles"
            :key="f.abs_path"
            style="cursor:pointer"
            @click="wikiViewModel.copyPath(f.abs_path || f.filename)"
          >
            <td style="text-align:center">
              <span v-if="f.index_status === 'synced'" style="color:#22c55e" title="已同步">&#10003;</span>
              <span v-else-if="f.index_status === 'out_of_sync'" style="color:#f97316" title="文件已修改，需重建索引">&#9888;</span>
              <span v-else style="color:#94a3b8" title="未索引">&#9675;</span>
            </td>
            <td class="ft-name">{{ f.filename }}</td>
            <td class="ft-meta">{{ wikiViewModel.formatSize(f.size_bytes) }}</td>
            <td class="ft-meta">{{ wikiViewModel.formatDate(f.modified) }}</td>
            <td class="ft-preview" :title="f.preview">{{ f.preview || '' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.file-section {
  background: #1a1d27;
  border: 1px solid #2d3149;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-height: 0;
}
.fs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.fs-title {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
}
.table-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.file-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.file-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #12141c;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
  text-align: left;
  padding: 8px 12px;
  border-bottom: 1px solid #2d3149;
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
}
.file-table th:hover {
  color: #94a3b8;
}
.file-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #1a1d27;
  vertical-align: top;
}
.file-table tbody tr:hover {
  background: #12141c;
}
.ft-name {
  color: #a78bfa;
  font-weight: 500;
  white-space: nowrap;
}
.ft-meta {
  color: #64748b;
  white-space: nowrap;
  font-size: 12px;
}
.ft-preview {
  color: #94a3b8;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.mini-loading {
  display: block;
  width: 24px;
  height: 24px;
  border: 2px solid #eab30844;
  border-top-color: #fde047;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 24px auto;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.empty-state {
  text-align: center;
  color: #64748b;
  padding: 40px 20px;
  font-size: 13px;
}
</style>
