"""日志配置"""
import os
import sys
import logging
import glob
import shutil
import time as _time


class LoggerManager:
    _instance = None
    _logger = None

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def setup_logger(self, project_root, role='app'):
        """初始化日志系统，返回 logger 实例"""
        log_dir = os.path.join(project_root, 'logs')
        os.makedirs(log_dir, exist_ok=True)

        prefix = 'flask' if role == 'flask' else ('ui' if role == 'ui' else 'app')
        self._roll_logs(log_dir, prefix=prefix)
        log_file = os.path.join(log_dir, f'{prefix}_{_time.strftime("%Y%m%d_%H%M%S")}.log')
        print(f"[logger] Creating new log file ({role}): {os.path.basename(log_file)}")
        sys.stdout.flush()

        handler = logging.FileHandler(log_file, encoding='utf-8')
        formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        handler.setFormatter(formatter)

        root_log = logging.getLogger()
        root_log.setLevel(logging.INFO)
        root_log.addHandler(handler)

        log = logging.getLogger('memory')
        log.setLevel(logging.INFO)
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        logging.getLogger('asyncio').setLevel(logging.CRITICAL)

        LoggerManager._logger = log
        return log

    def _roll_logs(self, log_dir, prefix='app'):
        """日志文件归档"""
        archive_dir = os.path.join(log_dir, 'archive')
        os.makedirs(archive_dir, exist_ok=True)

        pattern = os.path.join(log_dir, f'{prefix}_*.log')
        files = glob.glob(pattern)

        print(f"[logger] Found {len(files)} log files to archive")
        sys.stdout.flush()

        for f in files:
            try:
                filename = os.path.basename(f)
                archive_path = os.path.join(archive_dir, filename)
                print(f"[logger] Archiving: {filename}")
                sys.stdout.flush()

                if os.path.exists(archive_path):
                    print(f"[logger] Removing existing archive")
                    sys.stdout.flush()
                    try:
                        os.remove(archive_path)
                    except Exception as e:
                        print(f"[logger] Failed to remove: {e}")
                        sys.stdout.flush()
                        continue

                try:
                    shutil.move(f, archive_path)
                    print(f"[logger] Moved: {filename}")
                    sys.stdout.flush()
                except Exception as move_err:
                    print(f"[logger] Move failed, trying copy: {move_err}")
                    sys.stdout.flush()
                    try:
                        shutil.copy2(f, archive_path)
                        os.remove(f)
                        print(f"[logger] Copied and removed: {filename}")
                        sys.stdout.flush()
                    except Exception as copy_err:
                        if 'being used' in str(copy_err) or 'in use' in str(copy_err).lower():
                            print(f"[logger] File in use, skipping: {filename}")
                            sys.stdout.flush()
                        else:
                            print(f"[logger] Copy failed: {copy_err}")
                            sys.stdout.flush()
                        continue
            except Exception as e:
                print(f"[logger] Archive failed for {f}: {e}")
                sys.stdout.flush()

        archive_files = sorted(glob.glob(os.path.join(archive_dir, f'{prefix}_*.log')),
                               key=os.path.getmtime, reverse=True)
        print(f"[logger] Keeping newest 3 of {len(archive_files)} archives")
        sys.stdout.flush()

        for f in archive_files[3:]:
            try:
                os.remove(f)
                print(f"[logger] Removed old archive: {os.path.basename(f)}")
                sys.stdout.flush()
            except Exception as e:
                print(f"[logger] Cleanup failed: {e}")
                sys.stdout.flush()

        print("[logger] Log archiving completed")
        sys.stdout.flush()


# 保持向后兼容：模块级函数调用单例
def setup_logger(project_root, role='app'):
    return LoggerManager.get_instance().setup_logger(project_root, role)


def archive_logs(log_dir: str, prefix: str = "flask", keep: int = 3):
    """归档指定前缀的日志文件，保留最新的 keep 份

    供 mem0_server/embed_server 等独立服务进程启动时调用。

    Args:
        log_dir: 日志目录（如 project_root/logs）
        prefix: 日志前缀（mem0 / embed / flask）
        keep: 保留最新文件数（默认 3）
    """
    import glob, os, shutil

    archive_dir = os.path.join(log_dir, 'archive')
    os.makedirs(archive_dir, exist_ok=True)

    pattern = os.path.join(log_dir, f'{prefix}_*.log')
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    # 当前要写的文件保留不动，其他的移入 archive
    for f in files:
        try:
            filename = os.path.basename(f)
            archive_path = os.path.join(archive_dir, filename)
            if os.path.exists(archive_path):
                os.remove(archive_path)
            shutil.move(f, archive_path)
            print(f"[archive] {filename} → archive/")
        except Exception as e:
            print(f"[archive] {filename} failed: {e}")

    # 只保留 keep 份
    archived = sorted(
        glob.glob(os.path.join(archive_dir, f'{prefix}_*.log')),
        key=os.path.getmtime, reverse=True
    )
    for f in archived[keep:]:
        try:
            os.remove(f)
            print(f"[archive] removed old: {os.path.basename(f)}")
        except Exception as e:
            print(f"[archive] cleanup failed: {e}")
