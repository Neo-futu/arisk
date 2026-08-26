"""最小 Lambda handler：hello / health 两个路由。

设计为既能被 Function URL / API Gateway (payload v2.0) 触发，也能被直接 invoke。
仅用标准库，无第三方依赖，便于直接 zip 打包与本地测试。
"""

import json
import os
from datetime import datetime, timezone


def _route(event):
    """从多种事件结构里取出请求路径，取不到则默认 '/'。"""
    if not isinstance(event, dict):
        return "/"
    # API Gateway / Function URL payload v2.0
    ctx = event.get("requestContext", {})
    http = ctx.get("http", {}) if isinstance(ctx, dict) else {}
    if http.get("path"):
        return http["path"]
    # API Gateway REST (v1.0) / 直接 invoke 传 path
    return event.get("path") or event.get("rawPath") or "/"


def _response(status, body):
    """返回 API Gateway / Function URL 兼容的代理响应。"""
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event, context=None):
    # 在调用时读环境变量（而非模块导入时），便于测试覆写与函数配置热更。
    app_name = os.environ.get("APP_NAME", "app-template")
    env = os.environ.get("ENV", "dev")

    path = _route(event)
    now = datetime.now(timezone.utc).isoformat()

    if path.rstrip("/").endswith("/health") or path == "/health":
        return _response(200, {"status": "ok", "app": app_name, "env": env, "time": now})

    return _response(
        200,
        {
            "message": f"hello from {app_name}",
            "env": env,
            "path": path,
            "time": now,
        },
    )
