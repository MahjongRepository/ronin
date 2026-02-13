const LOBBY_URL: string =
    ((window as unknown as Record<string, unknown>).__LOBBY_URL__ as string | undefined) ??
    "http://localhost:8000";

export interface RoomInfo {
    room_id: string;
    human_player_count: number;
    humans_needed: number;
    total_seats: number;
    num_bots: number;
    players: string[];
    server_name: string;
    server_url: string;
}

interface ListRoomsResponse {
    rooms: RoomInfo[];
}

interface CreateRoomResponse {
    room_id: string;
    websocket_url: string;
    server_name: string;
}

export async function listRooms(): Promise<RoomInfo[]> {
    const res = await fetch(`${LOBBY_URL}/rooms`);
    if (!res.ok) {
        throw new Error(`Failed to list rooms: ${res.status}`);
    }
    const data: ListRoomsResponse = await res.json();
    return data.rooms;
}

export async function createRoom(numBots?: number): Promise<CreateRoomResponse> {
    const body = numBots !== undefined ? JSON.stringify({ num_bots: numBots }) : undefined;
    const headers: Record<string, string> = {};
    if (body) {
        headers["Content-Type"] = "application/json";
    }
    const res = await fetch(`${LOBBY_URL}/rooms`, {
        body,
        headers,
        method: "POST",
    });
    if (!res.ok) {
        throw new Error(`Failed to create room: ${res.status}`);
    }
    return await res.json();
}
