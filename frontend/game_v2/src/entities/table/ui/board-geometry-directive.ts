import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import { type ElementPart, type PartInfo, PartType, directive } from "lit-html/directive.js";

import {
    type BoardBox,
    type BoardLengths,
    boardGeometry,
} from "@/entities/table/lib/board-geometry";

/**
 * Size the board from its own box (`boardGeometry`): its family and chrome as `data-board-family` / `data-board-chrome`
 * and its sizes as `--geo-<name>` on the board, measured once its first render is in the document and again as its box
 * changes, until it leaves. An empty box (a hidden board) changes nothing and the board stays watched.
 */
class SizeBoard extends AsyncDirective {
    private board: HTMLElement | null = null;
    private observer: ResizeObserver | null = null;
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
                this.size(board, entry.contentRect);
            }
        });
        this.observer.observe(board);
        this.size(board, board.getBoundingClientRect());
    }

    private size(board: HTMLElement, { width, height }: BoardBox): void {
        if (width <= 0 || height <= 0) {
            return;
        }
        const { chrome, family, lengths } = boardGeometry({ height, width });
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
