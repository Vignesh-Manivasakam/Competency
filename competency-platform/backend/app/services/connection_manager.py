# app/services/connection_manager.py
"""WebSocket connection manager — tracks all active learning sessions.

Manages the lifecycle of WebSocket connections:
- Register/unregister connections by session_id
- Send messages to specific sessions
- Broadcast to all connections (admin/system messages)
- Track connection metadata (employee_id, connected_at)
- Enforce one-connection-per-session invariant
"""
import asyncio
import structlog
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field
from fastapi import WebSocket

logger = structlog.get_logger()


@dataclass
class ConnectionInfo:
    """Metadata for an active WebSocket connection."""
    websocket: WebSocket
    session_id: str
    employee_id: str
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    is_paused: bool = False
    interaction_count: int = 0


class ConnectionManager:
    """Manages active WebSocket connections for learning sessions.
    
    Thread-safe via asyncio lock. Enforces one WebSocket connection
    per session_id — reconnection replaces the previous connection.
    """

    def __init__(self):
        self._connections: dict[str, ConnectionInfo] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        session_id: str,
        employee_id: str,
    ) -> ConnectionInfo:
        """Accept and register a WebSocket connection.
        
        If a connection already exists for this session_id,
        close the old one first (handles browser refresh/reconnect).
        """
        await websocket.accept()

        async with self._lock:
            # Close existing connection for this session (reconnect scenario)
            if session_id in self._connections:
                old_conn = self._connections[session_id]
                try:
                    await old_conn.websocket.close(
                        code=4001,
                        reason="Replaced by new connection"
                    )
                except Exception:
                    pass  # Old connection may already be dead
                logger.info(
                    "ws_connection_replaced",
                    session_id=session_id,
                )

            conn_info = ConnectionInfo(
                websocket=websocket,
                session_id=session_id,
                employee_id=employee_id,
            )
            self._connections[session_id] = conn_info

        logger.info(
            "ws_connected",
            session_id=session_id,
            employee_id=employee_id,
            active_connections=len(self._connections),
        )
        return conn_info

    async def disconnect(self, session_id: str):
        """Unregister a WebSocket connection."""
        async with self._lock:
            conn = self._connections.pop(session_id, None)

        if conn:
            logger.info(
                "ws_disconnected",
                session_id=session_id,
                employee_id=conn.employee_id,
                duration_seconds=(
                    datetime.utcnow() - conn.connected_at
                ).total_seconds(),
                interactions=conn.interaction_count,
                active_connections=len(self._connections),
            )

    async def send_message(self, session_id: str, message: dict) -> bool:
        """Send a JSON message to a specific session's WebSocket.
        
        Returns True if sent successfully, False if connection not found
        or send failed.
        """
        conn = self._connections.get(session_id)
        if not conn:
            logger.warning("ws_send_no_connection", session_id=session_id)
            return False

        try:
            await conn.websocket.send_json(message)
            conn.last_activity = datetime.utcnow()
            return True
        except Exception as e:
            logger.error(
                "ws_send_failed",
                session_id=session_id,
                error=str(e),
            )
            await self.disconnect(session_id)
            return False

    async def broadcast(self, message: dict):
        """Send a message to all active connections (admin use)."""
        disconnected = []
        for session_id, conn in self._connections.items():
            try:
                await conn.websocket.send_json(message)
            except Exception:
                disconnected.append(session_id)

        for sid in disconnected:
            await self.disconnect(sid)

    def get_connection(self, session_id: str) -> Optional[ConnectionInfo]:
        """Get connection info for a session."""
        return self._connections.get(session_id)

    def get_active_count(self) -> int:
        """Number of currently active WebSocket connections."""
        return len(self._connections)

    def get_active_sessions(self) -> list[str]:
        """List all session_ids with active connections."""
        return list(self._connections.keys())

    async def mark_paused(self, session_id: str):
        """Mark a session as paused."""
        conn = self._connections.get(session_id)
        if conn:
            conn.is_paused = True

    async def mark_resumed(self, session_id: str):
        """Mark a session as resumed."""
        conn = self._connections.get(session_id)
        if conn:
            conn.is_paused = False

    async def increment_interaction(self, session_id: str):
        """Increment the interaction counter for tracking."""
        conn = self._connections.get(session_id)
        if conn:
            conn.interaction_count += 1
            conn.last_activity = datetime.utcnow()


# Global singleton — imported by WebSocket handler and session routes
connection_manager = ConnectionManager()
