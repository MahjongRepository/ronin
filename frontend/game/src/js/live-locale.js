import { applyStaticText, locale, setLocale } from "../i18n/index.js";

/**
 * Show the live game in `next` in place, as a locale switch must: only texts and their title, aria-label, alt and lang
 * attributes change, so the socket, the open decision with its buttons, the selectable and selected tiles, the
 * countdowns and the keyboard focus all stay. The board relabels its table and keeps an open dialog's text, tagged with
 * the locale it is in, until it shows again (`Board.relabel`); the rest of the page relabels from its markup.
 */
export function switchLiveLocale(board, next) {
    const previous = locale();
    if (next === previous) {
        return;
    }
    setLocale(next);
    board.relabel(previous);
    applyStaticText(document, { skip: [board.root] });
}
