"""
自我叙事模块 - 公共工具函数
"""
import json
import re


def parse_json(raw: str):
    """从 LLM 响应中提取 JSON，支持 code block 包裹

    统一的 JSON 解析工具，供 narrative_store / reflection / pipeline_steps 共用。
    """
    if not raw:
        return None
    raw = raw.strip()
    # 直接解析
    try:
        return json.loads(raw)
    except Exception:
        pass
    # 尝试提取 ```json ... ```
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    # 尝试提取第一个 {...} 或 [...]
    for pattern in (r'\{[\s\S]*\}', r'\[[\s\S]*\]'):
        m = re.search(pattern, raw)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None
