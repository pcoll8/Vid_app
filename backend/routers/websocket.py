"""
WebSocket Router
Real-time progress updates and log streaming with per-client fanout queues.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, Optional, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import get_settings
from ..utils.logger import get_logger

router = APIRouter()
logger = get_logger()

active_connections: Set[WebSocket] = set()
connection_queues: Dict[WebSocket, asyncio.Queue] = {}

_broadcast_loop: Optional[asyncio.AbstractEventLoop] = None
_MAX_QUEUE_SIZE = 500


def set_broadcast_loop(loop: asyncio.AbstractEventLoop):
    """Set the loop used for thread-safe broadcast operations."""
    global _broadcast_loop
    _broadcast_loop = loop


def _extract_websocket_api_key(websocket: WebSocket) -> str:
    api_key = websocket.headers.get("x-api-key", "").strip()
    if api_key:
        return api_key

    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()

    return websocket.query_params.get("token", "").strip()


def _is_authorized(websocket: WebSocket) -> bool:
    settings = get_settings()
    if not settings.api_key:
        return True
    return _extract_websocket_api_key(websocket) == settings.api_key


def _enqueue_message(queue: asyncio.Queue, payload: Dict[str, Any]):
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        pass


def _broadcast_payload(payload: Dict[str, Any]):
    for queue in list(connection_queues.values()):
        _enqueue_message(queue, payload)


def _dispatch_broadcast(payload: Dict[str, Any]):
    if _broadcast_loop and _broadcast_loop.is_running():
        _broadcast_loop.call_soon_threadsafe(_broadcast_payload, payload)
        return

    try:
        asyncio.get_running_loop()
        _broadcast_payload(payload)
    except RuntimeError:
        logger.debug("Skipping broadcast; no running event loop")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real-time updates."""
    if not _is_authorized(websocket):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
    active_connections.add(websocket)
    connection_queues[websocket] = queue
    logger.info(f"WebSocket connected. Total: {len(active_connections)}")

    try:
        send_task = asyncio.create_task(send_updates(websocket, queue))
        receive_task = asyncio.create_task(receive_messages(websocket))

        done, pending = await asyncio.wait(
            [send_task, receive_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            try:
                await task
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass
            except Exception as exc:
                logger.error(f"WebSocket task error: {exc}")

        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
    finally:
        active_connections.discard(websocket)
        connection_queues.pop(websocket, None)
        logger.info(f"WebSocket removed. Total: {len(active_connections)}")


async def send_updates(websocket: WebSocket, queue: asyncio.Queue):
    """Send queued updates to the WebSocket client."""
    while True:
        try:
            payload = await queue.get()
            await websocket.send_json(payload)
        except WebSocketDisconnect:
            break


async def receive_messages(websocket: WebSocket):
    """Receive messages from WebSocket client."""
    while True:
        try:
            data = await websocket.receive_text()
            message = json.loads(data)
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
        except WebSocketDisconnect:
            break
        except Exception as exc:
            logger.error(f"Error receiving message: {exc}")


def broadcast_progress(job_id: str, progress: float, message: str):
    """Broadcast progress update to all connected clients."""
    _dispatch_broadcast(
        {
            "type": "progress",
            "data": {
                "job_id": job_id,
                "progress": progress,
                "message": message,
            },
        }
    )


def broadcast_log(message: str, level: str = "INFO"):
    """Broadcast log message to all connected clients."""
    _dispatch_broadcast(
        {
            "type": "log",
            "data": {
                "timestamp": datetime.utcnow().isoformat(),
                "level": level,
                "message": message,
            },
        }
    )


async def broadcast_to_all(message: Dict[str, Any]):
    """Broadcast an arbitrary payload to all connected clients."""
    _dispatch_broadcast(message)
