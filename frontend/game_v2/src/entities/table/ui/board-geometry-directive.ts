import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import { type ElementPart, type PartInfo, PartType, directive } from "lit-html/directive.js";

import {
    type BoardBox,
    type BoardGeometry,
    type BoardInput,
    type BoardLengths,
    type BoardSlots,
    boardGeometry,
} from "@/entities/table/lib/board-geometry";

const NO_PAGE = { gutter: 0, safeInsets: { bottom: 0, left: 0, right: 0, top: 0 } };

/** The page's raw safe-area insets and applied gutter around the board, or null without a page. */
function pageEdges(board: HTMLElement): Pick<BoardInput, "gutter" | "safeInsets"> | null {
    const page = board.closest(".board-page");
    if (page === null) {
        return null;
    }
    const style = getComputedStyle(page);
    function px(name: string): number {
        const length = Number.parseFloat(style.getPropertyValue(name));
        return Number.isFinite(length) ? length : 0;
    }
    return {
        gutter: px("--page-gutter"),
        safeInsets: {
            bottom: px("--ronin-safe-bottom"),
            left: px("--ronin-safe-left"),
            right: px("--ronin-safe-right"),
            top: px("--ronin-safe-top"),
        },
    };
}

/**
 * Size the board from its own box and the slots its page fills (`boardGeometry`): its family and chrome as
 * `data-board-family` / `data-board-chrome` and its sizes as `--geo-<name>` on the board, measured once its first
 * render is in the document and again as its box or its slots change, until it leaves. An empty box (a hidden board)
 * changes nothing and the board stays watched.
 */
class SizeBoard extends AsyncDirective {
    private board: HTMLElement | null = null;
    private observer: ResizeObserver | null = null;
    private frame: number | null = null;
    private slots: BoardSlots | null = null;
    private readonly written = new Map<string, string>();

    constructor(partInfo: PartInfo) {
        super(partInfo);
        if (partInfo.type !== PartType.ELEMENT) {
            throw new Error("sizeBoard belongs on an element");
        }
    }

    render(_slots: BoardSlots): typeof nothing {
        return nothing;
    }

    override update(part: ElementPart, [slots]: [BoardSlots]): typeof nothing {
        if (part.element instanceof HTMLElement) {
            this.board = part.element;
        }
        const moved = this.slots?.corner !== slots.corner || this.slots.band !== slots.band;
        this.slots = slots;
        if (this.observer === null) {
            queueMicrotask(() => this.observe());
        } else if (moved) {
            queueMicrotask(() => this.resize());
        }
        return nothing;
    }

    protected override disconnected(): void {
        this.observer?.disconnect();
        this.observer = null;
        this.cancelFrame();
    }

    protected override reconnected(): void {
        this.observe();
    }

    private resize(): void {
        const { board } = this;
        if (this.observer !== null && board !== null) {
            this.size(board, board.getBoundingClientRect(), false);
        }
    }

    private observe(): void {
        const { board } = this;
        const watching = this.observer !== null || typeof ResizeObserver === "undefined";
        if (!this.isConnected || board?.isConnected !== true || watching) {
            return;
        }
        this.observer = new ResizeObserver((entries) => {
            const entry = entries.at(-1);
            if (entry !== undefined) {
                this.size(board, entry.contentRect, true);
            }
        });
        this.observer.observe(board);
        this.size(board, board.getBoundingClientRect(), false);
    }

    /** A gutter change resizes the observed board, so one found while the observer delivers waits for the next frame. */
    private size(board: HTMLElement, { width, height }: BoardBox, delivering: boolean): void {
        const { slots } = this;
        if (width <= 0 || height <= 0 || slots === null) {
            return;
        }
        this.cancelFrame();
        const edges = pageEdges(board);
        const geometry = boardGeometry({ box: { height, width }, slots, ...(edges ?? NO_PAGE) });
        if (delivering && edges !== null && geometry.gutter !== edges.gutter) {
            this.frame = requestAnimationFrame(() => {
                this.frame = null;
                this.write(board, geometry);
            });
            return;
        }
        this.write(board, geometry);
    }

    private cancelFrame(): void {
        if (this.frame !== null) {
            cancelAnimationFrame(this.frame);
            this.frame = null;
        }
    }

    private write(board: HTMLElement, { chrome, family, lengths }: BoardGeometry): void {
        if (board.dataset.boardFamily !== family) {
            board.dataset.boardFamily = family;
        }
        if (board.dataset.boardChrome !== chrome) {
            board.dataset.boardChrome = chrome;
        }
        this.writeLengths(board, lengths);
    }

    private writeLengths(board: HTMLElement, lengths: BoardLengths): void {
        const values = new Map(
            Object.entries(lengths).map(([name, length]) => [`--geo-${name}`, `${length}px`]),
        );
        for (const name of this.written.keys()) {
            if (!values.has(name)) {
                board.style.removeProperty(name);
                this.written.delete(name);
            }
        }
        for (const [name, value] of values) {
            if (this.written.get(name) !== value) {
                board.style.setProperty(name, value);
                this.written.set(name, value);
            }
        }
    }
}

export const sizeBoard = directive(SizeBoard);
