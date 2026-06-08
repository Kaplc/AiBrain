"""mem0 独立服务 — 与 Flask 主进程解耦

独立 Flask 进程，持有 BGE-M3 语义模型 + mem0 客户端单例，
不随主 Flask 重启。主 Flask 通过 HTTP API 调用本服务。
"""
