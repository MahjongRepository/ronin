from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute

from game.logic.mock import MockGameService
from game.messaging.router import MessageRouter
from game.server.types import CreateRoomRequest
from game.session.manager import SessionManager

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.websockets import WebSocket


def create_app(
    game_service: MockGameService | None = None,
    session_manager: SessionManager | None = None,
    message_router: MessageRouter | None = None,
) -> Starlette:
    if game_service is None:
        game_service = MockGameService()

    if session_manager is None:
        session_manager = SessionManager(game_service)

    if message_router is None:
        message_router = MessageRouter(session_manager)

    async def ws_endpoint(websocket: WebSocket) -> None:
        from game.server.websocket import websocket_endpoint

        await websocket_endpoint(websocket, message_router)

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def status(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "active_rooms": session_manager.room_count,
                "max_rooms": 100,
            }
        )

    async def create_room(request: Request) -> JSONResponse:
        try:
            body = await request.json()
            room_request = CreateRoomRequest(**body)

            # Check if room already exists
            if session_manager.get_room(room_request.room_id):
                return JSONResponse(
                    {"error": "Room already exists"},
                    status_code=409,
                )

            # Pre-create the room
            session_manager.create_room(room_request.room_id)

            return JSONResponse(
                {
                    "room_id": room_request.room_id,
                    "status": "created",
                },
                status_code=201,
            )
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/status", status, methods=["GET"]),
        Route("/rooms", create_room, methods=["POST"]),
        WebSocketRoute("/ws/{room_id}", ws_endpoint),
    ]

    app = Starlette(routes=routes)
    app.state.session_manager = session_manager

    return app


app = create_app()
