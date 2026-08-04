"""WebSocket 连接管理器 — 线程安全广播"""

import asyncio
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """WebSocket 连接管理, 支持线程安全的广播"""

    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)

    async def broadcast(self, data: dict[str, Any]) -> None:
        """向所有连接广播消息（线程安全）"""
        async with self._lock:
            dead: list[WebSocket] = []
            for conn in self._connections:
                try:
                    await conn.send_json(data)
                except Exception:
                    dead.append(conn)
            for conn in dead:
                self._connections.remove(conn)

    @property
    def active_count(self) -> int:
        return len(self._connections)

    async def send_to(self, ws: WebSocket, data: dict[str, Any]) -> None:
        """向单个连接发送消息"""
        try:
            await ws.send_json(data)
        except Exception:
            await self.disconnect(ws)
