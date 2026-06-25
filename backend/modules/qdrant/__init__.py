"""Qdrant 底层接口模块

提供 Qdrant 直连存储与搜索的底层功能：
  - get_qdrant_client(), embed_texts(), store_vector()
  - search_new_collection(), search_legacy_collection()
  - NEW_COLLECTION, LEGACY_COLLECTION, DEFAULT_USER_ID 等常量
"""
from .store import (
    get_qdrant_client, embed_texts, store_vector,
    ensure_collection, collection_exists,
    dedup_node_name,
    NEW_COLLECTION, LEGACY_COLLECTION, DEFAULT_USER_ID,
    NODE_COLLECTION,
)
from .search import (
    search_new_collection, search_legacy_collection,
    SOURCE_SEMANTIC,
)

__all__ = [
    "get_qdrant_client", "embed_texts", "store_vector",
    "ensure_collection", "collection_exists",
    "dedup_node_name",
    "search_new_collection", "search_legacy_collection",
    "SOURCE_SEMANTIC",
    "NEW_COLLECTION", "LEGACY_COLLECTION", "DEFAULT_USER_ID",
    "NODE_COLLECTION",
]
