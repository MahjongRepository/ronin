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
});
const STORYBOOK_PAGES = Object.values(STORYBOOK_PAGE);

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

export function storybookPath(page) {
    return page === STORYBOOK_PAGE.INDEX ? "/play/storybook" : `/play/storybook/${page}`;
}
