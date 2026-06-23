"""自我叙事模块 - 公共工具函数（已迁至 main_brain/narrative）"""
import json
import re


def parse_json(raw: str):
    """从 LLM 响应中提取 JSON，支持 code block 包裹"""
    if not raw:
        return None
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    for pattern in (r'\{[\s\S]*\}', r'\[[\s\S]*\]'):
        m = re.search(pattern, raw)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None
