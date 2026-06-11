"""K8s 探针 HTTP 服务（liveness / readiness）。

不依赖 Nacos 注册（按文档约束 4）：
- /health  → liveness：进程是否存活
- /ready   → readiness：依赖（RabbitMQ + Milvus + Redis）是否就绪

K8s 配置示例::

    livenessProbe:
      httpGet: { path: /health, port: 8080 }
      initialDelaySeconds: 10
      periodSeconds: 30
    readinessProbe:
      httpGet: { path: /ready, port: 8080 }
      initialDelaySeconds: 5
      periodSeconds: 10
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

import structlog
from aiohttp import web

logger = structlog.get_logger(__name__)


class HealthServer:
    """轻量 HTTP 探针服务。"""

    def __init__(
        self,
        consumer: Optional[Any] = None,
        milvus: Optional[Any] = None,
        guard: Optional[Any] = None,
    ) -> None:
        # duck-typed：注入任意提供 is_connected()/ping() 的对象
        self._consumer = consumer
        self._milvus = milvus
        self._guard = guard
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    async def start(self, port: int) -> None:
        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_get("/ready", self._ready)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", port)
        await self._site.start()
        logger.info("health_server_started", port=port)

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
            self._site = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        logger.info("health_server_stopped")

    # ---- 端点 ----
    async def _health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "alive"})

    async def _ready(self, _request: web.Request) -> web.Response:
        deps = {
            "rabbitmq": bool(self._consumer and self._consumer.is_connected()),
            "milvus": bool(self._milvus and self._milvus.ping()),
            "redis": bool(self._guard and await self._guard.ping()),
        }
        all_ok = all(deps.values())
        return web.json_response(
            {"status": "ready" if all_ok else "not_ready", "deps": deps},
            status=200 if all_ok else 503,
        )
