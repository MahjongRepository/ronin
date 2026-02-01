import { type TemplateResult, html, render } from "lit-html";
import { createGame, listGames } from "../api";
import { navigate } from "../router";

const PLAYER_NAME_SUFFIX_LENGTH = 6;

// generates a random player name
function generatePlayerName(): string {
    const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
    let suffix = "";
    for (let idx = 0; idx < PLAYER_NAME_SUFFIX_LENGTH; idx++) {
        suffix += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return `Player_${suffix}`;
}

const playerName = generatePlayerName();

export function lobbyView(): TemplateResult {
    // trigger async load after render
    setTimeout(() => loadAndRenderGames(), 0);

    return html`
        <div class="lobby">
            <h1>Ronin Mahjong</h1>
            <div class="lobby-controls">
                <button class="btn btn-primary" @click=${handleCreateGame}>Create Game</button>
                <button class="btn btn-secondary" @click=${() => loadAndRenderGames()}>Refresh</button>
            </div>
            <div class="lobby-status" id="lobby-status"></div>
            <div class="games-list" id="games-list">Loading games...</div>
        </div>
    `;
}

async function loadAndRenderGames(): Promise<void> {
    const container = document.getElementById("games-list");
    if (!container) {
        return;
    }

    try {
        const games = await listGames();
        if (games.length === 0) {
            render(
                html`
                    <p class="empty-message">No games available. Create one!</p>
                `,
                container,
            );
        } else {
            render(
                html`
                ${games.map(
                    (game) => html`
                    <div class="game-item">
                        <span class="game-id">${game.game_id}</span>
                        <span class="game-players">${game.player_count}/${game.max_players} players</span>
                        ${
                            game.player_count < game.max_players
                                ? html`<button class="btn btn-small" @click=${() => joinGame(game.game_id, game.server_url)}>Join</button>`
                                : html`
                                      <span class="game-full">Full</span>
                                  `
                        }
                    </div>
                `,
                )}
            `,
                container,
            );
        }
    } catch {
        render(
            html`
                <p class="error-message">Failed to load games</p>
            `,
            container,
        );
    }
}

function showLobbyStatus(content: TemplateResult): void {
    const statusEl = document.getElementById("lobby-status");
    if (statusEl) {
        render(content, statusEl);
    }
}

async function handleCreateGame(): Promise<void> {
    showLobbyStatus(
        html`
            <p>Creating game...</p>
        `,
    );
    try {
        const response = await createGame();
        sessionStorage.setItem("ws_url", response.websocket_url);
        sessionStorage.setItem("player_name", playerName);
        navigate(`/game/${response.game_id}`);
    } catch {
        showLobbyStatus(
            html`
                <p class="error-message">Failed to create game</p>
            `,
        );
    }
}

function parseServerUrl(serverUrl: string, gameId: string): URL | undefined {
    try {
        const url = new URL(serverUrl);
        url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
        url.pathname = `/ws/${gameId}`;
        return url;
    } catch {
        return undefined;
    }
}

function joinGame(gameId: string, serverUrl: string): void {
    const url = parseServerUrl(serverUrl, gameId);
    if (!url) {
        showLobbyStatus(
            html`
                <p class="error-message">Invalid server URL</p>
            `,
        );
        return;
    }
    sessionStorage.setItem("ws_url", url.toString());
    sessionStorage.setItem("player_name", playerName);
    navigate(`/game/${gameId}`);
}
