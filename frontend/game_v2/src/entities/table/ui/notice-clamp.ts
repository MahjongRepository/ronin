import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import { type ElementPart, type PartInfo, PartType, directive } from "lit-html/directive.js";

import { t } from "@/shared/i18n";

/** A clamped notice's "Show all" is at least this tall, over the text above its line; the notice is its target. */
export const NOTICE_TAP_MIN = 40;

/**
 * What the clamp reads of one notice: its padding and rim clamped, what more padding it takes shown whole (a way out's
 * tap target's room), its text's whole height and line, and whether it may clamp.
 */
export interface NoticeMeasure {
    readonly chrome: number;
    readonly wholeExtra: number;
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

/**
 * A notice's height at `lines` of its text with "Show all" on a line of its own under them, its target's height at
 * least, or whole at null.
 */
function shownHeight(notice: NoticeMeasure, lines: number | null): number {
    if (lines === null) {
        return notice.chrome + notice.wholeExtra + notice.textHeight;
    }
    return notice.chrome + Math.max(NOTICE_TAP_MIN, (lines + 1) * notice.lineHeight);
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

/**
 * The most whole lines (at least one, at most `current`, and fewer than the text holds, since a clamp to all of them
 * hides no text, only a way out) that bring a notice's stack within its room, if fewer help.
 */
function fittedLines(
    place: NoticePlace,
    notice: NoticeMeasure,
    { current, others }: { readonly current: number | null; readonly others: number },
): number | null {
    const most = Math.min(current ?? Number.POSITIVE_INFINITY, fullLines(notice) - 1);
    if (most < 1) {
        return current;
    }
    const fitting = Math.floor((place.room - others - notice.chrome) / notice.lineHeight) - 1;
    const lines = Math.min(Math.max(1, fitting), most);
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
    const clamped = notice.hasAttribute("data-clamped");
    const wholeExtra = pixels(style.getPropertyValue("--whole-extra"));
    const chrome =
        pixels(style.paddingTop) +
        pixels(style.paddingBottom) +
        pixels(style.borderTopWidth) +
        pixels(style.borderBottomWidth);
    return {
        chrome,
        clampable: notice.querySelector(".board-notice__more") !== null,
        lineHeight: pixels(getComputedStyle(text).lineHeight),
        textHeight: clamped ? text.scrollHeight : text.clientHeight - wholeExtra,
        wholeExtra,
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
        more > 0
            ? t("game.notice.show_all_more", { count: more, words })
            : t("game.notice.show_all_label", { words }),
    );
}

function readPlace(place: HTMLElement): {
    readonly apart: boolean;
    readonly notices: HTMLElement[];
    readonly place: NoticePlace;
} | null {
    const list = place.querySelector(".board-notices__list");
    const notices = [...(list?.children ?? [])].filter((child) => child instanceof HTMLElement);
    const apart = getComputedStyle(place).display === "contents";
    const room = list instanceof HTMLElement ? placeRoom(place, list, apart) : null;
    if (room === null || notices.length === 0) {
        return null;
    }
    for (const notice of notices) {
        notice.removeAttribute("data-overflow");
    }
    return { apart, notices, place: room };
}

/**
 * The room a place's notices take (its height less what else it holds; the list's own where they stand `apart`) and
 * their gap; null for a place that sets no height.
 */
function placeRoom(place: HTMLElement, list: HTMLElement, apart: boolean): NoticePlace | null {
    const height = pixels(getComputedStyle(apart ? list : place).maxHeight);
    if (height === 0) {
        return null;
    }
    return {
        gap: pixels(getComputedStyle(list).rowGap),
        room: apart ? height : height - (place.scrollHeight - list.offsetHeight),
    };
}

export interface ToastMeasure {
    readonly wholeHeight: number;
    readonly clampedHeight: number;
    readonly cutPastTwoLines: boolean;
    readonly clampable: boolean;
}

export interface ToastStackPlan {
    readonly clamped: readonly boolean[];
    readonly shown: number;
}

export function planToastStack(
    room: number,
    gap: number,
    toasts: readonly ToastMeasure[],
): ToastStackPlan {
    function clampedOf(count: number): boolean[] {
        return toasts
            .slice(0, count)
            .map(
                (toast, index) =>
                    toast.clampable &&
                    (toast.cutPastTwoLines || (index === count - 1 && count < toasts.length)),
            );
    }
    function toastStackHeight(count: number): number {
        const clamped = clampedOf(count);
        const heights = toasts
            .slice(0, count)
            .map((toast, index) =>
                clamped[index] === true
                    ? Math.max(NOTICE_TAP_MIN, toast.clampedHeight)
                    : toast.wholeHeight,
            );
        return heights.reduce((sum, height) => sum + height, 0) + gap * Math.max(0, count - 1);
    }
    let shown = Math.min(1, toasts.length);
    for (let count = toasts.length; count > 1; count -= 1) {
        if (toastStackHeight(count) <= room) {
            shown = count;
            break;
        }
    }
    return {
        clamped: [...clampedOf(shown), ...toasts.slice(shown).map(() => false)],
        shown,
    };
}

function wordLines(words: HTMLElement): number {
    const line = pixels(getComputedStyle(words).lineHeight);
    return line > 0 ? Math.max(1, Math.round(words.clientHeight / line)) : 1;
}

function readAsClamped<Measured>(
    notice: HTMLElement,
    clamped: boolean,
    read: () => Measured,
): Measured {
    const was = notice.hasAttribute("data-clamped");
    setAttribute(notice, "data-clamped", clamped ? "" : null);
    const value = read();
    setAttribute(notice, "data-clamped", was ? "" : null);
    return value;
}

function measureToast(
    notice: HTMLElement,
): (ToastMeasure & { readonly clampedLines: number }) | null {
    const words = notice.querySelector(".board-notice__words");
    if (!(words instanceof HTMLElement)) {
        return null;
    }
    const whole = readAsClamped(notice, false, () => ({
        cutPastTwoLines: words.scrollHeight > words.clientHeight + 1,
        wholeHeight: notice.getBoundingClientRect().height,
    }));
    const clamped = readAsClamped(notice, true, () => ({
        clampedHeight: notice.getBoundingClientRect().height,
        clampedLines: wordLines(words),
    }));
    return {
        ...whole,
        ...clamped,
        clampable: notice.querySelector(".board-notice__more") !== null,
    };
}

function clampToasts(notices: readonly HTMLElement[], place: NoticePlace): void {
    const measures = notices.map(measureToast);
    if (measures.some((measure) => measure === null)) {
        return;
    }
    const toasts = measures.filter((measure) => measure !== null);
    const { clamped, shown } = planToastStack(place.room, place.gap, toasts);
    notices.forEach((notice, index) => {
        writeClamp(notice, {
            left: index >= shown,
            lines: clamped[index] === true ? (toasts[index]?.clampedLines ?? 1) : null,
            more: index === shown - 1 ? notices.length - shown : 0,
        });
    });
}

function clampWrapped(notices: readonly HTMLElement[], place: NoticePlace): void {
    const measures = notices.map(measureNotice).filter((measure) => measure !== null);
    if (measures.length !== notices.length) {
        return;
    }
    const { lines, shown } = planNoticeClamp(place.room, place.gap, measures);
    notices.forEach((notice, index) => {
        writeClamp(notice, {
            left: index >= shown,
            lines: lines[index] ?? null,
            more: index === shown - 1 ? notices.length - shown : 0,
        });
    });
}

/**
 * Clamp the notices of a place to whole lines, and leave out the last ones, where the stack is taller than the place
 * lets it be: a text's overflow is the one thing CSS cannot tell, so this alone reads the layout. It reads each text's
 * whole height (a clamped text's scroll height, so it never undoes a clamp to measure; a whole one's own height less
 * its way out's line); only a notice it left out is shown again for a moment, and a toast read both whole and clamped
 * (`clampToasts`), within the same task, so nothing paints between.
 */
function clampPlace(element: HTMLElement): void {
    const read = readPlace(element);
    if (read === null) {
        return;
    }
    const { apart, notices, place } = read;
    if (apart) {
        clampToasts(notices, place);
    } else {
        clampWrapped(notices, place);
    }
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
