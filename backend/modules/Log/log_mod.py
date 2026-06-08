"""日志文件读取工具（单例） - 供 routes/logs_routes.py 调用"""
import glob
import os


class LogManager:
    _instance = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_latest_log_file(self, project_root: str, prefix: str = "flask") -> tuple[str | None, str | None]:
        """返回最新日志文件路径和文件名

        Args:
            project_root: 项目根目录
            prefix: 日志前缀，如 "flask", "mem0", "embed", "app", "ui", "*" 为所有

        Returns:
            (file_path, file_name) 或 (None, None)
        """
        log_dir = os.path.join(project_root, 'logs')
        if prefix == "*" or prefix == "all":
            patterns = ('app_*.log', 'flask_*.log', 'ui_*.log', 'mem0_*.log', 'embed_*.log')
        else:
            patterns = (f'{prefix}_*.log',)
        files = []
        for pat in patterns:
            files.extend(glob.glob(os.path.join(log_dir, pat)))
        if not files:
            return None, None
        log_file = max(files, key=os.path.getmtime)
        return log_file, os.path.basename(log_file)

    def read_log_tail(self, log_file: str, lines: int = 300) -> dict:
        """读取日志文件最后 N 行"""
        try:
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()
            tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
            return {
                "lines": [l.rstrip() for l in tail],
                "total": len(all_lines),
                "returned": len(tail),
            }
        except Exception as e:
            return {"lines": [], "total": 0, "returned": 0, "error": str(e)}

    def read_log_tail_filtered(self, log_file: str, keywords: list[str], lines: int = 200) -> dict:
        """读取日志文件最后 N 行（过滤关键词）"""
        try:
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()
            relevant = [
                l.strip() for l in all_lines
                if any(kw.lower() in l.strip().lower() for kw in keywords)
            ]
            tail = relevant[-lines:] if len(relevant) > lines else relevant
            return {
                "lines": tail,
                "total_relevant": len(relevant),
                "returned": len(tail),
            }
        except Exception as e:
            return {"lines": [], "total_relevant": 0, "returned": 0, "error": str(e)}