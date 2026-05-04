/* Model tab - 设备/模型设置 */
import { ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { registerTab } from '../TabRegistry'
import ModelTabVue from '../ModelTab/ModelTab.vue'

export class ModelTab {
  readonly desc = ref('')
  readonly gpuInfoHtml = ref('检测中...')
  readonly gpuInfoClass = ref<'ok' | 'warn' | 'err'>('ok')
  readonly saving = ref(false)
  readonly pendingDevice = ref<string>('cpu')

  private _configStore = useConfigStore()
  private _api = useApi()
  private _toast = useToast()

  async loadFromConfig(cfg: any, st: any): Promise<void> {
    const device = cfg.device ?? 'cpu'
    this.pendingDevice.value = device

    const modelName = st.embedding_model || 'BAAI/bge-m3'
    const dim = st.embedding_dim || 1024
    this.desc.value = `${modelName} · 向量维度 ${dim}`

    if (st.cuda_available) {
      this.gpuInfoHtml.value = `✅ 检测到 GPU：<strong>${st.gpu_name}</strong>`
      this.gpuInfoClass.value = 'ok'
    } else if (st.gpu_hardware) {
      this.gpuInfoHtml.value =
        `⚠️ 检测到 NVIDIA GPU，但安装的是 CPU 版 PyTorch。<br>` +
        `<small>运行以下命令安装 GPU 版：</small><br>` +
        `<code>pip uninstall torch -y && pip install torch --index-url https://download.pytorch.org/whl/cu124</code>`
      this.gpuInfoClass.value = 'warn'
    } else {
      this.gpuInfoHtml.value = '未检测到 NVIDIA GPU，GPU 选项不可用'
      this.gpuInfoClass.value = 'err'
    }
  }

  async apply(): Promise<void> {
    if (this.pendingDevice.value === this._configStore.savedDevice) {
      this._toast.show('设置未变更', 'info')
      return
    }
    this.saving.value = true
    try {
      await this._api.postJson('/settings/reload-model', { device: this.pendingDevice.value })
      this._configStore.savedDevice = this.pendingDevice.value as any
      this._configStore.device = this.pendingDevice.value as any
      this._toast.show(`✅ 已保存并重载模型（${this.pendingDevice.value}）`, 'success')
    } catch (e: any) {
      this._toast.show('保存失败: ' + e, 'error')
    }
    this.saving.value = false
  }

  reset(): void {
    this.pendingDevice.value = this._configStore.savedDevice
    this._toast.show('已重置', 'info')
  }
}

// 主动注册
const _modelTab = new ModelTab()
registerTab({
  name: 'model',
  title: '模型',
  component: ModelTabVue,
  tabClass: _modelTab,
})
