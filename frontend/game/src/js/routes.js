export const LOBBY_URL = "/";
export const HISTORY_URL = "/history";

export const ROUTE = Object.freeze({
    GAME: "game",
    REPLAY: "replay",
    STORYBOOK: "storybook",
});

export const STORYBOOK_PAGE = Object.freeze({
    INDEX: "index",
    BOARD: "board",
    DISCARDS: "discards",
    HAND: "hand",
    MELDS: "melds",
    DECISIONS: "decisions",
    TABLE: "table",
    WIN: "win",
    DRAW: "draw",
    STANDINGS: "standings",
    LOADING: "loading",
});
const STORYBOOK_PAGES = Object.values(STORYBOOK_PAGE);

/** Every page of the game client is under this path; the lobby serves the rest. */
const GAME_CLIENT_PREFIX = "/play/";

const REPLAY_PATH = /^\/play\/history\/(?<gameId>[^/]+)$/;
const STORYBOOK_PATH = /^\/play\/storybook(?:\/(?<page>[^/]+))?$/;
const GAME_PATH = /^\/play\/(?<gameId>[^/]+)$/;

export function matchRoute(pathname) {
    const replay = pathname.match(REPLAY_PATH);
    if (replay) {
        return { name: ROUTE.REPLAY, gameId: replay.groups.gameId };
    }

    const storybook = pathname.match(STORYBOOK_PATH);
    if (storybook) {
        const page = storybook.groups.page ?? STORYBOOK_PAGE.INDEX;
        return STORYBOOK_PAGES.includes(page) ? { name: ROUTE.STORYBOOK, page } : null;
    }

    const game = pathname.match(GAME_PATH);
    if (game) {
        return { name: ROUTE.GAME, gameId: game.groups.gameId };
    }

    return null;
}

/** Whether a path is one of the game client's, a route of it or not. */
export function isGameClientPath(pathname) {
    return pathname.startsWith(GAME_CLIENT_PREFIX);
}

/** The query parameters of a replay page: the seat it is viewed from and the position it shows. */
export const POSITION_PARAM = Object.freeze({ SEAT: "seat", ROUND: "round", STEP: "step" });

/** The replay page of a game, shown from `seat`. */
export function replayPath(gameId, seat) {
    const params = new URLSearchParams({ [POSITION_PARAM.SEAT]: String(seat) });
    return `/play/history/${encodeURIComponent(gameId)}?${params}`;
}

export function storybookPath(page) {
    return page === STORYBOOK_PAGE.INDEX ? "/play/storybook" : `/play/storybook/${page}`;
}
