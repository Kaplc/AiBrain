#!/usr/bin/env python
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
os.environ['MODELSCOPE_CACHE'] = 'E:/Project/Memory/hf_cache'

from modelscope import snapshot_download
from modelscope.utils.progress_bar import progress_bar

print('开始下载 BAAI/bge-m3 模型...')
print('缓存目录: E:/Project/Memory/hf_cache')
print()

# Download with progress tracking
model_dir = snapshot_download('BAAI/bge-m3', force=True)

print()
print(f'下载完成: {model_dir}')

# List downloaded files
print()
print('下载的文件:')
for root, dirs, files in os.walk(model_dir):
    for f in files:
        path = os.path.join(root, f)
        size = os.path.getsize(path)
        print(f'  {os.path.relpath(path, model_dir)} ({size/1024/1024:.1f} MB)')