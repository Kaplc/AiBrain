# Routes package - 按前端视图拆分的 API 路由

from .overview_routes import register as reg_overview
from .memory_routes import register as reg_memory
from .stream_routes import register as reg_stream
from .statusbar_routes import register as reg_statusbar
from .logs_routes import register as reg_logs
from .settings_routes import register as reg_settings
from .wiki_routes import register as reg_wiki
from .stats_routes import register as reg_stats