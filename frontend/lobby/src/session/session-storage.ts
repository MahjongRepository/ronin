/** Store the game session the game client joins with; the key and shape are the handoff contract. */
export function storeGameSession(gameId: string, wsUrl: string, gameTicket: string): void {
    sessionStorage.setItem(`game_session:${gameId}`, JSON.stringify({ gameTicket, wsUrl }));
}
