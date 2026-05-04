"""
LightRAG 引擎 - 初始化、Embedding/LLM 适配、查询/插入
LLM 配置优先级：wiki.json 的 llm 字段 > mem0.json（fallback）
支持 OpenAI 兼容接口 / Anthropic 原生接口 / Ollama
"""
import os
import json
import asyncio
import logging
import functools
import re
import threading
import numpy as np

# 强制离线，防止 LightRAG/fastembed 联网检查模型更新
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

logger = logging.getLogger(__name__)

_rag_instance = None
_rag_lock = threading.Lock()  # 全局锁：防止并发查询导致 LightRAG 死锁


def _run_async(coro):
    """在同步上下文中运行异步协程（每次创建新event loop避免锁冲突）"""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=30)


def _run_async_with_timeout(coro, timeout=30):
    """运行异步协程，带超时保护"""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise TimeoutError(f"异步操作超时({timeout}s)")



def _load_llm_config() -> dict:
    """加载 LLM 配置。支持嵌套格式(llm.{})和扁平格式(llm_provider等)，api_key 可从 mem0.json 继承"""
    from .config import load_wiki_config

    wiki_cfg = load_wiki_config()

    # 读取 mem0.json（用于 fallback 或继承 api_key）
    mem0_cfg = {}
    mem0_path = os.path.join(os.path.expanduser("~"), ".aibrain", "config", "mem0.json")
    if os.path.exists(mem0_path):
        with open(mem0_path, "r", encoding="utf-8") as f:
            mem0_cfg = json.load(f)

    # === 兼容嵌套格式: { "llm": { "provider": "...", "api_key": "..." } } ===
    llm_cfg = wiki_cfg.get("llm", {})
    if llm_cfg.get("provider"):
        api_key = llm_cfg.get("api_key") or mem0_cfg.get("api_key", "")
        return {
            "llm_provider": llm_cfg["provider"],
            "llm_model": llm_cfg.get("model", ""),
            "api_key": api_key,
            "base_url": llm_cfg.get("base_url", ""),
        }

    # === 兼容扁平格式: { "llm_provider": "...", "llm_api_key": "..." } ===
    flat_provider = wiki_cfg.get("llm_provider") or wiki_cfg.get("llm_provider")
    if flat_provider:
        api_key = (
            wiki_cfg.get("llm_api_key")
            or wiki_cfg.get("api_key")
            or mem0_cfg.get("api_key", "")
        )
        return {
            "llm_provider": flat_provider,
            "llm_model": wiki_cfg.get("llm_model", ""),
            "api_key": api_key,
            "base_url": wiki_cfg.get("llm_base_url", ""),
        }

    # 完全没配置 wiki llm，fallback 到 mem0.json
    if mem0_cfg:
        return mem0_cfg

    raise RuntimeError(
        "未找到 LLM 配置。请在 ~/.aibrain/config/wiki.json 的 llm 字段中配置，"
        "或在 ~/.aibrain/config/mem0.json 中配置。"
    )


async def _bge_m3_embed(texts: list[str]) -> np.ndarray:
    """异步 Embedding 函数，复用 brain_mcp 的 BGE-M3"""
    from brain_mcp.embedding import encode_texts
    embeddings = encode_texts(texts)
    return np.array(embeddings)


def _strip_think_tags(text: str) -> str:
    """去掉推理模型的 <think>...</think> 前缀"""
    if "<think>" in text:
        return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)
    return text


def _build_llm_func(cfg: dict):
    """根据配置构建 LightRAG 兼容的 LLM 函数

    LightRAG 调用签名: llm_model_func(prompt, system_prompt=..., **kwargs)
    """
    provider = cfg.get("llm_provider", "openai").lower()
    model = cfg.get("llm_model", "gpt-4o-mini")
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", "")

    # === Ollama ===
    if provider == "ollama":
        from lightrag.llm.ollama import ollama_model_complete
        return functools.partial(
            ollama_model_complete,
            model=model,
            host=base_url or "http://localhost:11434",
        )

    # === Anthropic 原生接口 ===
    if provider == "anthropic":
        # 默认模型
        if not model:
            model = "claude-sonnet-4-20250514"

        async def anthropic_wrapper(prompt, system_prompt=None, **kwargs):
            import time as _time
            kwargs.pop("response_format", None)
            kwargs.pop("hashing_kv", None)
            kwargs.pop("keyword_extraction", None)

            t0 = _time.time()
            prompt_len = len(prompt) if prompt else 0
            sys_len = len(system_prompt) if system_prompt else 0
            logger.info(f"[LLM] anthropic 调用开始 model={model} prompt={prompt_len}chars sys_prompt={sys_len}chars")

            try:
                import anthropic
                client = anthropic.AsyncAnthropic(
                    api_key=api_key,
                    **({"base_url": base_url} if base_url else {}),
                )
                messages = [{"role": "user", "content": prompt}]
                params = {
                    "model": model,
                    "max_tokens": kwargs.pop("max_tokens", 4096),
                    "messages": messages,
                }
                if system_prompt:
                    params["system"] = system_prompt

                t1 = _time.time()
                response = await client.messages.create(**params)
                t2 = _time.time()
                result_len = sum(len(b.text) for b in response.content if hasattr(b, "text"))

                # 过滤掉 ThinkingBlock，只取 TextBlock
                texts = []
                for block in response.content:
                    if hasattr(block, "type") and block.type == "text":
                        texts.append(block.text)
                result = "\n".join(texts) or ""

                elapsed_total = t2 - t0
                elapsed_api = t2 - t1
                logger.info(f"[LLM] anthropic 完成 total={elapsed_total:.1f}s api_wait={elapsed_api:.1f}s result={result_len}chars")
                return _strip_think_tags(result)
            except Exception as e:
                logger.error(f"Anthropic API 调用失败: {e}")
                raise

        return anthropic_wrapper

    # === OpenAI 兼容接口（OpenAI / DeepSeek / MiniMax / Groq 等）===
    from lightrag.llm.openai import openai_complete_if_cache

    if not base_url:
        provider_urls = {
            "deepseek": "https://api.deepseek.com/v1",
            "groq": "https://api.groq.com/openai/v1",
            "together": "https://api.together.xyz/v1",
            "xai": "https://api.x.ai/v1",
        }
        base_url = provider_urls.get(provider)

    _model = model
    _api_key = api_key
    _base_url = base_url

    async def openai_wrapper(prompt, system_prompt=None, **kwargs):
        import time as _time
        t0 = _time.time()
        prompt_len = len(prompt) if prompt else 0
        logger.info(f"[LLM] openai 调用开始 model={_model} prompt={prompt_len}chars base_url={_base_url}")

        kw = {"api_key": _api_key}
        if _base_url:
            kw["base_url"] = _base_url
        kwargs.pop("response_format", None)
        kw.update(kwargs)
        result = await openai_complete_if_cache(
            _model, prompt, system_prompt=system_prompt, **kw
        )
        result_len = len(result) if isinstance(result, str) else 0
        logger.info(f"[LLM] openai 完成 total={_time.time()-t0:.1f}s result={result_len}chars")
        return _strip_think_tags(result) if isinstance(result, str) else result

    return openai_wrapper


def _build_embedding_func():
    """构建 LightRAG 的 EmbeddingFunc，复用 BGE-M3"""
    from lightrag.utils import EmbeddingFunc

    return EmbeddingFunc(
        embedding_dim=1024,
        max_token_size=8192,
        func=_bge_m3_embed,
    )


def get_rag():
    """单例获取 LightRAG 实例（懒初始化）"""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = _create_rag()
    return _rag_instance


def _create_rag():
    """创建 LightRAG 实例"""
    import time as _t
    t0 = _t.time()
    logger.info("[TRACE] _create_rag() 开始")

    from lightrag import LightRAG
    from .config import load_wiki_config, get_lightrag_dir

    t1 = _t.time()
    cfg = load_wiki_config()
    logger.info(f"[TRACE] load_wiki_config 耗时 {(_t.time()-t1):.2f}s")

    t2 = _t.time()
    llm_cfg = _load_llm_config()
    logger.info(f"[TRACE] _load_llm_config 耗时 {(_t.time()-t2):.2f} provider={llm_cfg.get('llm_provider')} model={llm_cfg.get('llm_model')}")

    lightrag_dir = get_lightrag_dir()

    os.makedirs(lightrag_dir, exist_ok=True)

    t3 = _t.time()
    rag = LightRAG(
        working_dir=lightrag_dir,
        embedding_func=_build_embedding_func(),
        llm_model_func=_build_llm_func(llm_cfg),
        llm_model_name=llm_cfg.get("llm_model", "gpt-4o-mini"),
        chunk_token_size=cfg.get("chunk_token_size", 1200),
        chunk_overlap_token_size=100,
        default_llm_timeout=120,  # LLM 超时 120 秒（原 360 秒）
        addon_params={
            "language": cfg.get("language", "Chinese"),
        },
        vector_storage="NanoVectorDBStorage",
        graph_storage="NetworkXStorage",
    )
    t_rag_create = _t.time() - t3
    logger.info(f"[TRACE] LightRAG() 构造耗时 {t_rag_create:.2f}s")

    t4 = _t.time()
    try:
        _run_async_with_timeout(rag.initialize_storages(), timeout=30)
    except TimeoutError as e:
        logger.warning(f"[TRACE] initialize_storages 超时: {e}，继续执行")
    t_init = _t.time() - t4
    total = _t.time() - t0
    logger.info(
        f"[TRACE] _create_rag() 完成 | "
        f"config={_t.time()-t1:.2f}s llm={_t.time()-t2:.2f}s "
        f"LightRAG={t_rag_create:.2f}s init_storages={t_init:.2f}s total={total:.2f}s"
    )
    return rag


def insert_document(text: str, file_path: str | None = None) -> str:
    """插入文档到 LightRAG 索引"""
    rag = get_rag()
    kwargs = {"input": text}
    if file_path:
        kwargs["file_paths"] = file_path
    return rag.insert(**kwargs)


def query_wiki_context(question: str, mode: str = "hybrid") -> str:
    """查询 wiki，仅返回检索到的上下文（不经过 LLM 生成）

    每个查询创建独立 RAG 实例，彻底避免 LightRAG 线程安全问题导致卡死
    （LightRAG query() 存在单实例多次调用后永久阻塞的已知问题）
    """
    import time as _t
    t_start = _t.time()
    logger.info(f"[TRACE] query_wiki_context 开始 | question={question[:50]} mode={mode}")

    from lightrag.base import QueryParam

    valid_modes = ("naive", "local", "global", "hybrid", "mix")
    if mode not in valid_modes:
        mode = "hybrid"

    param = QueryParam(mode=mode, only_need_context=True)

    # === 每个查询创建独立 RAG 实例（避免 LightRAG 卡死问题）===
    t0 = _t.time()
    rag = _create_rag()
    t_rag = _t.time() - t0
    logger.info(f"[TRACE] _create_rag() 耗时 {t_rag:.2f}s (独立实例)")

    t1 = _t.time()
    result = rag.query(question, param=param)
    t_query = _t.time() - t1
    total = _t.time() - t_start
    logger.info(
        f"[TRACE] query_wiki_context 完成 | mode={mode} "
        f"rag_init={t_rag:.2f}s query={t_query:.2f}s total={total:.2f}s result_len={len(result) if result else 0}"
    )
    return result


def _verify_vector_inserted(rel_path: str, track_id: str, timeout: int = 30) -> bool:
    """验证文件是否已处理完成（异步轮询直到 status=processed 或超时）

    insert_document() 是异步入队接口，LightRAG 后台线程处理完成后
    会更新 doc_status 存储。本函数通过 aget_docs_by_track_id() 轮询
    文档状态，等待其变为 'processed'。

    Args:
        rel_path: 文件相对路径（如 "project/xxx.md"），用于日志
        track_id: insert_document() 返回的追踪 ID
        timeout: 超时秒数，默认 30 秒

    Returns:
        True: 文档已处理完成，False: 超时或失败
    """
    import time as _time
    rag = get_rag()

    async def _wait_for_processed(tid: str, tout: int) -> bool:
        deadline = _time.time() + tout
        while _time.time() < deadline:
            try:
                result = await rag.aget_docs_by_track_id(tid)
                for doc_id, doc_status in result.items():
                    status = doc_status.status if hasattr(doc_status, 'status') else str(doc_status.status)
                    if status == 'processed':
                        logger.info(f"[verify✓] 文档处理完成 | track_id={tid} doc_id={doc_id}")
                        return True
                    elif status == 'failed':
                        em = getattr(doc_status, 'error_msg', 'unknown')
                        # "Content already exists" 意味着文档之前已成功处理，不算真正失败
                        if 'Content already exists' in em:
                            logger.info(f"[verify✓] 文档已存在（之前已索引）| track_id={tid} doc_id={doc_id}")
                            return True
                        logger.error(f"[verify✗] 文档处理失败 | track_id={tid} error={em}")
                        return False
                    else:
                        logger.info(f"[verify] 等待处理中 | track_id={tid} status={status}")
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"[verify] 轮询异常: {e}，重试")
                await asyncio.sleep(1)
        logger.warning(f"[verify✗] 验证超时 | track_id={tid}")
        return False

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_wait_for_processed(track_id, timeout))
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"[verify] 验证异常: {e}")
        return False


def delete_document(doc_id: str) -> dict:
    """删除文档及其关联的知识图谱数据"""
    rag = get_rag()
    result = rag.delete_by_doc_id(doc_id)
    return {
        "status": result.status,
        "doc_id": result.doc_id,
        "message": result.message,
    }


def reset_rag():
    """重置 RAG 实例（配置变更后调用）"""
    global _rag_instance
    _rag_instance = None
