from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.monitoring import asterisk_ami_monitor, gateway_line_monitor

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/gateway-lines")
async def gateway_lines_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await gateway_line_monitor.subscribe()
    try:
        while True:
            snapshot = await queue.get()
            await websocket.send_json(snapshot.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        gateway_line_monitor.unsubscribe(queue)


@router.websocket("/ws/asterisk")
async def asterisk_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = await asterisk_ami_monitor.subscribe()
    try:
        while True:
            snapshot = await queue.get()
            await websocket.send_json(snapshot.model_dump(mode="json"))
    except WebSocketDisconnect:
        pass
    finally:
        asterisk_ami_monitor.unsubscribe(queue)
