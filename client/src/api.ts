const LOBBY_URL = "http://localhost:8000";

interface GameInfo {
    game_id: string;
    player_count: number;
    max_players: number;
    server_name: string;
    server_url: string;
}

interface ListGamesResponse {
    games: GameInfo[];
}

interface CreateGameResponse {
    game_id: string;
    websocket_url: string;
}

export async function listGames(): Promise<GameInfo[]> {
    const res = await fetch(`${LOBBY_URL}/games`);
    if (!res.ok) {
        throw new Error(`Failed to list games: ${res.status}`);
    }
    const data: ListGamesResponse = await res.json();
    return data.games;
}

export async function createGame(): Promise<CreateGameResponse> {
    const res = await fetch(`${LOBBY_URL}/games`, {
        method: "POST",
    });
    if (!res.ok) {
        throw new Error(`Failed to create game: ${res.status}`);
    }
    return await res.json();
}
