# Final Reply Strategy（reactive 最终回复策略说明）

当 BrainJudge 输出 `final_reply` 时，`reply_strategy` 字段携带回复策略，由 Reply Strategy
解读后用于指导最终回复（注入到 prompt 上下文或调整人设语气）。这不是一个会被 LLM 直接消费的
完整 prompt，而是结构化策略：

```json
{
  "tone": "语气倾向，如 轻松/认真/简洁",
  "should_mention_thoughts": false,
  "key_points": ["本次回复应覆盖的要点1", "要点2"],
  "extra_hint": "可选的额外提示，如 隐约想起某件事但不确定"
}
```

说明：
- `should_mention_thoughts`：是否在回复里体现刚才的内部思考/联想（默认 false，避免生硬）。
- `key_points`：指导回复内容覆盖面，不强制逐条照念。
- 策略为空时，回复完全走原有 chat 链路，不受影响（兼容回滚）。
