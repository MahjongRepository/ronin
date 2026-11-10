/** The board's root as `GameBoard` renders it, which holds its keys, so a page can give it a focus it lost. */
export const BOARD_SELECTOR = ".game-board";

/** What the panel over the board renders (`GameBoard`'s overlay), so a page can tell whether a result scrolls in it. */
export const BOARD_PANEL_SELECTOR = "[data-board-panel]";

/** The notices' place as `BoardNotices` renders it, which keeps the wheel turned over it for itself. */
export const BOARD_NOTICES_SELECTOR = "[data-board-notices]";
