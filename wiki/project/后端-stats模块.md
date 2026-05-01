# 后端 - Stats 模块（图表统计）

## 概述
`stats.py` 提供记忆数据的统计图表 API，支持按小时/日聚合的时间维度数据。

## 文件位置
```
backend/modules/stats.py
```

## API 接口

### GET `/chart-data`
**查询参数**：`range=today|week|month`

**响应格式**：
```json
{
  "range": "week",
  "data": [
    {
      "date": "2026-04-23",
      "added": 5,
      "updated": 2,
      "total": 123
    }
  ]
}
```

**range 行为**：
| range | 数据范围 | 时间粒度 |
|-------|---------|---------|
| `today` | 最近24小时 | 按整点小时（00:00 - 23:00） |
| `week` | 最近7天 | 按日 |
| `month` | 最近30天 | 按日 |
| 其他 | 全量 | 按日 |

**今日数据**（today）：
- 时间格式：`"HH:00"`（如 `"14:00"`）
- 从 23 小时前整点 → 当前整点，共 24 个数据点

**数据来源**：
- `added`：每日来自 `daily_stats` 表的 added 字段；每小时来自 `stream` 表 action=store
- `updated`：每日/每小时来自 `stream` 表 action=update
- `total`：累计值 = 起始累计 + Σ(added - deleted)

## 内部函数

### `_get_hourly_data(stats_db)`
获取最近24小时按小时聚合数据：
1. 当前整点 - 23小时 = 起始整点
2. 从 `stream` 表查询 24 小时内记录
3. 按 `strftime('%Y-%m-%d %H:00:00', created_at)` 分组
4. 累加 24 小时前累计值 + 每小时 added

### `_get_daily_data(stats_db, start_date, end_date, range_type)`
获取指定日期范围内的每日数据，从 `daily_stats` 表查询。

### `_get_update_counts(stats_db, start_date, end_date)`
从 `stream` 表查询指定日期范围内的 update 操作数。

## 前端集成
- **Overview 前端**：记忆趋势图表，消费 `/chart-data`
- **ECharts**：累计曲线（total 字段）、新增曲线（added 字段）

---
*最后更新: 2026-05-01*
