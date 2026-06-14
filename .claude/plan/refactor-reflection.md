# 反思引擎重构 — 从叙事文本到认知状态

## 改动清单

### 1. 反思 prompt 输出格式
**旧**: `narrative_updates { chapter, milestone, lessons }`
**新**: `cognitive_updates { beliefs, interests, goals, open_questions, recent_realizations }`

### 2. 自传数据结构
**旧**: `identity + relationship + life_story(chapters) + current_state + milestones`
**新**: `identity + relationship + current_state + beliefs + interests + goals + open_questions + recent_realizations`

### 3. PromptPipeline 注入
**旧**: 心情 + 里程碑 + 章节
**新**: 心情 + beliefs + interests + goals + open_questions + recent_realizations

### 4. 搜索集成（核心价值）
搜索结果中，如果记忆的 typed nodes 命中当前 goals/interests/beliefs → score += 0.15
