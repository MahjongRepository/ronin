from pydantic import BaseModel, Field


class CreateRoomRequest(BaseModel):
    num_bots: int = Field(default=3, ge=0, le=3)


class CreateRoomResponse(BaseModel):
    room_id: str
    websocket_url: str
    server_name: str
