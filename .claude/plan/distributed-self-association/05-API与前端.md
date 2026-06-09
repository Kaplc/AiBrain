# Phase 5: API 与前端 — 让关联"被看见"

## 核心思想

> 如果自关联是"深夜城市里的漫步"，
> 那可视化就是让志远能看到这座城市夜晚的灯火分布。

## 实现方案

### 5.1 后端 API

新增路由（在 `memory_routes.py` 或新建 `activation_routes.py`）：

```python
# GET /activation/state
# 返回当前激活场快照：所有活跃节点（activation > 0.05）
{
  "active_nodes": [
    {"id": "ent:规则", "type": "entity", "activation": 0.72, "trending": "up"},
    {"id": "mem:xxx...", "type": "memory", "activation": 0.45, "trending": "stable"},
  ],
  "total_activation": 12.3,
  "budget_usage": "47%",
  "tick_count": 15234
}

# GET /activation/emergence
# 返回最近的涌现事件
{
  "events": [
    {
      "id": "emg_001",
      "description": "「规则」和「entity_relations」之间的关联变得强烈",
      "activation": 0.88,
      "created_at": "2026-06-01T14:23:00",
      "consumed": False
    }
  ]
}

# GET /activation/emergent-relations
# 返回"萌芽中"的实体关系
{
  "emergent": [
    {"from": "记忆", "to": "激活场", "co_count": 7, "strength": 0.45}
  ]
}

# POST /activation/inject
# 手动注入激活（用于测试）
{
  "node_id": "ent:分布式自关联",
  "amount": 0.5
}
```

### 5.2 现有可视化增强

当前 `get_visualization_data()` 返回节点和边数据，前端已有图谱动画。
增强内容：

```python
def get_visualization_data_enhanced(self):
    """增强版可视化数据"""
    base = self.get_visualization_data()
    
    # 为每个节点添加激活值
    field = get_activation_field()
    for node in base["nodes"]:
        act = field.get_activation(f"ent:{node['id']}")
        node["activation"] = round(act, 3) if act else 0
        node["glow"] = "high" if act and act > 0.6 else (
            "medium" if act and act > 0.3 else "low"
        )
    
    # 为边添加赫布学习统计
    hebbian = get_hebbian_plasticity()
    for edge in base["edges"]:
        stats = hebbian.get_edge_stats(edge["source"], edge["target"])
        edge["co_activation_count"] = stats.get("count", 0)
        edge["is_emergent"] = stats.get("emergent", False)
    
    # 添加"热力图"数据
    base["heatmap"] = self._get_activation_heatmap()
    
    return base
```

### 5.3 前端增强（ChatView / OverviewView）

**图谱可视化**（已有 `showGraphAnimation` 设置）：
- 节点光晕大小 = 激活值
- 边粗细 = 赫布权重
- 边颜色渐变：冷色（弱）→ 暖色（强）
- 空心节点 = 休眠，实心节点 = 活跃
- 闪烁节点 = 刚被唤醒（涌现）

**新增"意识流"面板**：
```
┌─────────────────────────────────────┐
│ 🧠 意识流                           │
│                                     │
│ • 我想到了「规则」... 0.72 ↑       │
│ • 「志远」和「升级」在共鸣  0.88 ★ │
│ • 「entity_relations」趋于平静 0.21↓│
│                                     │
│ [刷新] [注入激活] [查看全部涌现]    │
└─────────────────────────────────────┘
```

**新增"萌芽关系"面板**：
```
┌─────────────────────────────────────┐
│ 🌱 萌芽中的关联                     │
│                                     │
│ 记忆 ↔ 激活场      [███░░░] 7次    │
│ 猫猫 ↔ 分布式       [██░░░░] 5次   │
│                                     │
│ 点击"确认"建立正式关系               │
└─────────────────────────────────────┘
```

### 5.4 Hermes Webhook 集成

利用已有的 Hermes webhook 功能，让涌现事件能主动推送：

```bash
# 创建 webhook 订阅，当涌现事件发生时自动通知
hermes webhook subscribe emergence-alert
# POST /webhooks/emergence-alert
# Body: {"event": "...", "activation": 0.88, "description": "..."}
```

### 5.5 验证标准

- [ ] `/activation/state` API 正确返回激活场快照
- [ ] 图谱节点光晕随激活值实时变化
- [ ] 意识流面板展示最近的涌现事件
- [ ] 萌芽关系面板展示"即将建立"的实体关系
- [ ] 用户可通过前端确认/忽略萌芽关系
- [ ] Hermes webhook 在涌现事件发生时主动推送
