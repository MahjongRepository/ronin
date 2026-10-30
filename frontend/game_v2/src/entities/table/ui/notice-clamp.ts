import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import { type ElementPart, type PartInfo, PartType, directive } from "lit-html/directive.js";

/** A clamped notice's least height: the whole notice is its "Show all" control's tap target. */
export const NOTICE_TAP_MIN = 40;

/** What the clamp reads of one notice: its padding and rim, its text's whole height and line, and whether it may clamp. */
export interface NoticeMeasure {
    readonly chrome: number;
    readonly textHeight: number;
    readonly lineHeight: number;
    readonly clampable: boolean;
}

/** The height the notices' place lets their stack take, and the gap between two notices. */
interface NoticePlace {
    readonly room: number;
    readonly gap: number;
}

/**
 * How a stack shows in its place: the lines each notice shows (null for one shown whole), and how many of the stack,
 * from its first, show at all; the last shown carries "Show all" whenever any after it is left out.
 */
export interface NoticeClampPlan {
    readonly lines: readonly (number | null)[];
    readonly shown: number;
}

/** A notice's height at `lines` of its text with "Show all" on a line of its own under them, or whole at null. */
function shownHeight(notice: NoticeMeasure, lines: number | null): number {
    if (lines === null) {
        return notice.chrome + notice.textHeight;
    }
    return Math.max(NOTICE_TAP_MIN, notice.chrome + (lines + 1) * notice.lineHeight);
}

function fullLines(notice: NoticeMeasure): number {
    return Math.max(1, Math.round(notice.textHeight / notice.lineHeight));
}

function stackHeight(
    place: NoticePlace,
    notices: readonly NoticeMeasure[],
    lines: readonly (number | null)[],
): number {
    const heights = notices.map((notice, index) => shownHeight(notice, lines[index] ?? null));
    return (
        heights.reduce((sum, height) => sum + height, 0) +
        place.gap * Math.max(0, notices.length - 1)
    );
}

/** The most whole lines (at least one, at most `current`) that bring a notice's stack within its room, if fewer help. */
function fittedLines(
    place: NoticePlace,
    notice: NoticeMeasure,
    { current, others }: { readonly current: number | null; readonly others: number },
): number | null {
    const fitting = Math.floor((place.room - others - notice.chrome) / notice.lineHeight) - 1;
    const lines = Math.min(Math.max(1, fitting), current ?? Number.POSITIVE_INFINITY);
    return shownHeight(notice, lines) < shownHeight(notice, current) ? lines : current;
}

/**
 * The lines of each of `notices`, the last clamped (its "Show all" standing for the ones left out) when `forceLast`:
 * the tallest clampable notices clamp, one after another, each to the most whole lines that let the stack fit, until
 * it fits or none is left to clamp.
 */
function fitLines(
    place: NoticePlace,
    notices: readonly NoticeMeasure[],
    forceLast: boolean,
): (number | null)[] {
    const last = notices.length - 1;
    const lines = notices.map((notice, index) =>
        forceLast && notice.clampable && index === last ? fullLines(notice) : null,
    );
    const tallestFirst = notices
        .map((notice, index) => ({
            height: shownHeight(notice, lines[index] ?? null),
            index,
            notice,
        }))
        .filter(({ notice }) => notice.clampable)
        .toSorted((first, second) => second.height - first.height);
    for (const { index, notice } of tallestFirst) {
        const total = stackHeight(place, notices, lines);
        if (total <= place.room) {
            break;
        }
        const current = lines[index] ?? null;
        lines[index] = fittedLines(place, notice, {
            current,
            others: total - shownHeight(notice, current),
        });
    }
    return lines;
}

/**
 * How a stack of notices shows in its place (`room`, the notices `gap` apart): whole while it fits; else clamped,
 * tallest first, to whole lines; and where even that leaves it too tall, without its last notices, one at a time,
 * the last one shown clamped so its "Show all" opens them all. The first notice always shows.
 */
export function planNoticeClamp(
    room: number,
    gap: number,
    notices: readonly NoticeMeasure[],
): NoticeClampPlan {
    const place = { gap, room };
    let shown = Math.min(1, notices.length);
    for (let candidate = notices.length; candidate > 1; candidate -= 1) {
        const lines = fitLines(place, notices.slice(0, candidate), candidate < notices.length);
        if (stackHeight(place, notices.slice(0, candidate), lines) <= room) {
            shown = candidate;
            break;
        }
    }
    const lines = fitLines(place, notices.slice(0, shown), shown < notices.length);
    return { lines: [...lines, ...notices.slice(shown).map(() => null)], shown };
}

function pixels(value: string): number {
    return Number.parseFloat(value) || 0;
}

function measureNotice(notice: HTMLElement): NoticeMeasure | null {
    const text = notice.querySelector(".board-notice__body");
    if (!(text instanceof HTMLElement)) {
        return null;
    }
    const style = getComputedStyle(notice);
    const chrome =
        pixels(style.paddingTop) +
        pixels(style.paddingBottom) +
        pixels(style.borderTopWidth) +
        pixels(style.borderBottomWidth);
    return {
        chrome,
        clampable: notice.querySelector(".board-notice__more") !== null,
        lineHeight: pixels(getComputedStyle(text).lineHeight),
        textHeight: text.scrollHeight,
    };
}

function setAttribute(element: Element, name: string, value: string | null): void {
    if (value === null) {
        element.removeAttribute(name);
    } else if (element.getAttribute(name) !== value) {
        element.setAttribute(name, value);
    }
}

/** One notice as planned: left out, or shown with its lines and, last shown, how many more its "Show all" opens. */
interface NoticeShown {
    readonly lines: number | null;
    readonly left: boolean;
    readonly more: number;
}

function writeClamp(notice: HTMLElement, { left, lines, more }: NoticeShown): void {
    setAttribute(notice, "data-overflow", left ? "" : null);
    setAttribute(notice, "data-clamped", lines === null ? null : "");
    if (lines === null) {
        notice.style.removeProperty("--notice-lines");
    } else {
        notice.style.setProperty("--notice-lines", String(lines));
    }
    const showAll = notice.querySelector(".board-notice__more");
    if (showAll !== null) {
        labelShowAll(showAll, more);
    }
}

/** "Show all" named by its notice's words and, where it stands for notices left out, how many more it opens. */
function labelShowAll(showAll: Element, more: number): void {
    const words = showAll.getAttribute("data-label") ?? "";
    setAttribute(showAll, "data-more", more > 0 ? `+${more}` : null);
    setAttribute(
        showAll,
        "aria-label",
        more > 0 ? `Show all, ${more} more: ${words}` : `Show all: ${words}`,
    );
}

/** Each notice's measure, every one shown again first if it was left out, so it is measured as it would show. */
function measureAll(notices: readonly HTMLElement[]): NoticeMeasure[] {
    for (const notice of notices) {
        notice.removeAttribute("data-overflow");
    }
    return notices.map(measureNotice).filter((measure) => measure !== null);
}

/**
 * The notices of a place, each shown again if it was left out, and their measures with the place's room for them
 * (its height less what else it holds, a replay's status) and their gap; null for a place that sets no height.
 */
function readPlace(place: HTMLElement): {
    readonly notices: HTMLElement[];
    readonly measures: NoticeMeasure[];
    readonly place: NoticePlace;
} | null {
    const list = place.querySelector(".board-notices__list");
    const height = pixels(getComputedStyle(place).maxHeight);
    const notices = [...(list?.children ?? [])].filter((child) => child instanceof HTMLElement);
    if (!(list instanceof HTMLElement) || height === 0 || notices.length === 0) {
        return null;
    }
    const measures = measureAll(notices);
    const room = {
        gap: pixels(getComputedStyle(list).rowGap),
        room: height - (place.scrollHeight - list.offsetHeight),
    };
    return measures.length === notices.length ? { measures, notices, place: room } : null;
}

/**
 * Clamp the notices of a place to whole lines, and leave out the last ones, where the stack is taller than the place
 * lets it be: a text's overflow is the one thing CSS cannot tell, so this alone reads the layout. It reads each text's
 * whole height (a clamped text's scroll height), so it never undoes a clamp to measure; only a notice it left out is
 * shown again for a moment, within the same task, so nothing paints between.
 */
function clampPlace(element: HTMLElement): void {
    const read = readPlace(element);
    if (read === null) {
        return;
    }
    const { measures, notices, place } = read;
    const { lines, shown } = planNoticeClamp(place.room, place.gap, measures);
    notices.forEach((notice, index) => {
        const more = index === shown - 1 ? notices.length - shown : 0;
        writeClamp(notice, { left: index >= shown, lines: lines[index] ?? null, more });
    });
}

/**
 * Keep the notices' place clamped (`clampPlace`): after each render, as the board's box changes and once the face
 * loads, until the place leaves the document. Its first render runs before the place is in the board, so it starts
 * watching the board once the render has put it there.
 */
class ClampNotices extends AsyncDirective {
    private place: HTMLElement | null = null;
    private observer: ResizeObserver | null = null;

    constructor(partInfo: PartInfo) {
        super(partInfo);
        if (partInfo.type !== PartType.ELEMENT) {
            throw new Error("clampNotices belongs on an element");
        }
    }

    render(): typeof nothing {
        return nothing;
    }

    override update(part: ElementPart): typeof nothing {
        if (part.element instanceof HTMLElement) {
            this.place = part.element;
            queueMicrotask(() => {
                this.observe();
                this.clamp();
            });
        }
        return nothing;
    }

    protected override disconnected(): void {
        this.observer?.disconnect();
        this.observer = null;
    }

    protected override reconnected(): void {
        this.observe();
    }

    private observe(): void {
        const { place } = this;
        const watching = this.observer !== null || typeof ResizeObserver === "undefined";
        if (place?.isConnected !== true || watching) {
            return;
        }
        this.observer = new ResizeObserver(() => requestAnimationFrame(() => this.clamp()));
        this.observer.observe(place.closest(".game-board") ?? place);
        if ("fonts" in document) {
            void document.fonts.ready.then(() => this.clamp());
        }
    }

    private clamp(): void {
        if (this.place?.isConnected === true) {
            clampPlace(this.place);
        }
    }
}

export const clampNotices = directive(ClampNotices);
