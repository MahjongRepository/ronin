import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import { type ElementPart, type PartInfo, PartType, directive } from "lit-html/directive.js";

import {
    type BoardBox,
    type BoardGeometry,
    type BoardInput,
    type BoardLengths,
    boardGeometry,
} from "@/entities/table/lib/board-geometry";

/** The page's raw safe-area insets and applied gutter around the board, none without a page. */
function pageEdges(board: HTMLElement): Omit<BoardInput, "box"> {
    const page = board.closest(".board-page");
    if (page === null) {
        return { gutter: 0, safeInsets: { bottom: 0, left: 0, right: 0, top: 0 } };
    }
    const style = getComputedStyle(page);
    function px(name: string): number {
        return Number.parseFloat(style.getPropertyValue(name));
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
 * Size the board from its own box (`boardGeometry`): its family and chrome as `data-board-family` / `data-board-chrome`
 * and its sizes as `--geo-<name>` on the board, measured once its first render is in the document and again as its box
 * changes, until it leaves. An empty box (a hidden board) changes nothing and the board stays watched.
 */
class SizeBoard extends AsyncDirective {
    private board: HTMLElement | null = null;
    private observer: ResizeObserver | null = null;
    private frame: number | null = null;
    private readonly written = new Map<string, string>();

    constructor(partInfo: PartInfo) {
        super(partInfo);
        if (partInfo.type !== PartType.ELEMENT) {
            throw new Error("sizeBoard belongs on an element");
        }
    }

    render(): typeof nothing {
        return nothing;
    }

    override update(part: ElementPart): typeof nothing {
        if (part.element instanceof HTMLElement) {
            this.board = part.element;
        }
        if (this.observer === null) {
            queueMicrotask(() => this.observe());
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

    /** A family change moves the page's gutter, so one found while the observer delivers waits for the next frame. */
    private size(board: HTMLElement, { width, height }: BoardBox, delivering: boolean): void {
        if (width <= 0 || height <= 0) {
            return;
        }
        this.cancelFrame();
        const geometry = boardGeometry({ box: { height, width }, ...pageEdges(board) });
        if (delivering && board.dataset.boardFamily !== geometry.family) {
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
