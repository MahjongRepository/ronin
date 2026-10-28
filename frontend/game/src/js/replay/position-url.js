import $ from "jquery";

const POSITION_PARAM = Object.freeze({ SEAT: "seat", ROUND: "round", STEP: "step" });

/**
 * The fewest milliseconds between two writes of the address bar. Safari refuses more than 100 history writes in 30
 * seconds, which autoplay and a held Next would reach; a move within it is written once the interval has passed.
 */
export const URL_WRITE_INTERVAL_MS = 500;

const DIGITS = /^\d+$/;

/** The parameter as an index below `length`, or null when it is missing, repeated, not a whole number or out of range. */
function indexParam(params, name, length) {
    const values = params.getAll(name);
    if (values.length !== 1 || !DIGITS.test(values[0])) {
        return null;
    }
    const index = Number(values[0]);
    return index < length ? index : null;
}

/**
 * The seat and position a query (`?seat=&round=&step=`) asks for, each bad part replaced by its fallback: a bad `seat`
 * by the recorded first dealer's, a bad `round` by the first deal (its `step` ignored), a bad `step` by its round's
 * deal. `round` counts the recorded deals from 0, repeats included; `step` counts the round's positions from 0 at the
 * deal, the final standings being the last round's last step.
 */
export function readPosition(search, replay) {
    const params = new URLSearchParams(search);
    const seat = indexParam(params, POSITION_PARAM.SEAT, replay.players.length) ?? replay.qijia;
    const round = indexParam(params, POSITION_PARAM.ROUND, replay.rounds.length);
    if (round === null) {
        return { seat, round: 0, step: 0 };
    }
    const step = indexParam(params, POSITION_PARAM.STEP, replay.rounds[round].positions.length);
    return { seat, round, step: step ?? 0 };
}

/** The page's own path with the query naming `state`'s seat and position, and nothing else. */
function positionHref({ seat, round, step }) {
    const params = new URLSearchParams({
        [POSITION_PARAM.SEAT]: String(seat),
        [POSITION_PARAM.ROUND]: String(round),
        [POSITION_PARAM.STEP]: String(step),
    });
    return `${window.location.pathname}?${params}${window.location.hash}`;
}

/**
 * Keeps the address bar on the position shown by replacing the page's history entry, so Back leaves the replay rather
 * than stepping through it. Writes come at most once per `URL_WRITE_INTERVAL_MS`, the latest position winning, and one
 * still waiting is written as the page is hidden or left. A double ron's page, the hidden-hands choice and autoplay are
 * not written: a link opens a double ron at its first win, paused, with the viewer's own settings.
 */
export class PositionUrl {
    #pending = null;
    #timer = null;
    #lastWrite = -Infinity;

    constructor() {
        this.bindPageLeave();
    }

    bindPageLeave() {
        $(window)
            .off(".replay-url")
            .on("pagehide.replay-url", () => this.flush());
        $(document)
            .off(".replay-url")
            .on("visibilitychange.replay-url", () => {
                if (document.hidden) {
                    this.flush();
                }
            });
    }

    show(state) {
        const href = positionHref(state);
        if (this.#timer === null && href === currentHref()) {
            return;
        }
        this.#pending = href;
        if (this.#timer !== null) {
            return;
        }
        const wait = this.#lastWrite + URL_WRITE_INTERVAL_MS - performance.now();
        if (wait <= 0) {
            this.flush();
            return;
        }
        this.#timer = setTimeout(() => this.flush(), wait);
    }

    flush() {
        clearTimeout(this.#timer);
        this.#timer = null;
        const href = this.#pending;
        this.#pending = null;
        if (href === null || href === currentHref()) {
            return;
        }
        this.#lastWrite = performance.now();
        try {
            window.history.replaceState(window.history.state, "", href);
        } catch (error) {
            console.warn("[ronin] the address bar keeps an older replay position:", error);
        }
    }
}

function currentHref() {
    return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}
