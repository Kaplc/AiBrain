"""日志配置"""
import os
import sys
import logging
import glob
import shutil
import time as _time


def setup_logger(project_root):
    """初始化日志系统，返回 logger 实例"""
    log_dir = os.path.join(project_root, 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # 先归档旧日志，再创建新的
    _roll_logs(log_dir)

    # 确保归档完成后再创建新日志文件
    log_file = os.path.join(log_dir, f'app_{_time.strftime("%Y%m%d_%H%M%S")}.log')
    print(f"[logger] Creating new log file: {os.path.basename(log_file)}")
    sys.stdout.flush()

    handler = logging.FileHandler(log_file, encoding='utf-8')
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)

    log = logging.getLogger('memory')
    log.setLevel(logging.INFO)
    log.addHandler(handler)
    # 静默 werkzeug 日志
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    return log


def _roll_logs(log_dir):
    """日志文件归档：启动时将现有的所有日志文件归档，归档目录最多保留6个文件"""
    archive_dir = os.path.join(log_dir, 'archive')
    os.makedirs(archive_dir, exist_ok=True)

    # 查找所有日志文件（不包括归档目录中的）
    pattern = os.path.join(log_dir, 'app_*.log')
    files = glob.glob(pattern)

    print(f"[logger] Found {len(files)} log files to archive: {[os.path.basename(f) for f in files]}")
    sys.stdout.flush()

    # 启动时立即将所有现有日志文件归档
    for f in files:
        try:
            filename = os.path.basename(f)
            archive_path = os.path.join(archive_dir, filename)
            print(f"[logger] Archiving: {filename}")
            sys.stdout.flush()

            # 如果归档已存在，先删除旧的
            if os.path.exists(archive_path):
                print(f"[logger] Removing existing archive: {os.path.basename(archive_path)}")
                sys.stdout.flush()
                try:
                    os.remove(archive_path)
                except Exception as e:
                    print(f"[logger] Failed to remove existing archive: {e}")
                    sys.stdout.flush()
                    continue

            # 尝试移动文件，如果失败则尝试复制后删除
            try:
                shutil.move(f, archive_path)
                print(f"[logger] Successfully moved: {filename}")
                sys.stdout.flush()
            except Exception as move_err:
                print(f"[logger] Move failed, trying copy: {move_err}")
                sys.stdout.flush()
                try:
                    shutil.copy2(f, archive_path)
                    os.remove(f)
                    print(f"[logger] Successfully copied and removed: {filename}")
                    sys.stdout.flush()
                except Exception as copy_err:
                    print(f"[logger] Copy also failed: {copy_err}")
                    sys.stdout.flush()
                    continue
        except Exception as e:
            print(f"[logger] Archive failed for {f}: {e}")

    # 清理归档目录，最多保留3个归档文件（删除最旧的）
    archive_files = sorted(glob.glob(os.path.join(archive_dir, 'app_*.log')),
                           key=os.path.getmtime, reverse=True)
    print(f"[logger] Archive directory has {len(archive_files)} files, keeping newest 3")
    sys.stdout.flush()

    for f in archive_files[3:]:
        try:
            os.remove(f)
            print(f"[logger] Removed old archive: {os.path.basename(f)}")
            sys.stdout.flush()
        except Exception as e:
            print(f"[logger] Archive cleanup failed: {e}")
            sys.stdout.flush()

    print("[logger] Log archiving completed")
    sys.stdout.flush()
