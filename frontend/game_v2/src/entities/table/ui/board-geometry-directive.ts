import { nothing } from "lit-html";
import { AsyncDirective } from "lit-html/async-directive.js";
import { type ElementPart, type PartInfo, PartType, directive } from "lit-html/directive.js";

import {
    type BoardBox,
    type BoardGeometry,
    type BoardInput,
    type BoardSlots,
    type PlaneGeometry,
    type PlaneZone,
    boardGeometry,
    planeGeometry,
    planeZone,
} from "@/entities/table/lib/board-geometry";
import {
    type MeldShape,
    type StripContent,
    type StripSeat,
    handLength,
    ownMeldTile,
    stripLengths,
} from "@/entities/table/lib/strip-layout";

/** What the opponents' strips hold, by seat, and the own row's melds. */
interface StripContents extends Readonly<Record<StripSeat, StripContent>> {
    readonly own: readonly MeldShape[];
}

const NO_EDGES = { bottom: 0, left: 0, right: 0, top: 0 };

/** What the page holds around the board: its raw safe-area insets, the padding it applies and its gutter. */
interface PageEdges extends Pick<BoardInput, "appliedEdges" | "safeInsets"> {
    readonly gutter: number;
}

/** The page's edges around the board, or null without a page. */
function pageEdges(board: HTMLElement): PageEdges | null {
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
        appliedEdges: {
            bottom: px("padding-bottom"),
            left: px("padding-left"),
            right: px("padding-right"),
            top: px("padding-top"),
        },
        gutter: px("--page-gutter"),
        safeInsets: {
            bottom: px("--ronin-safe-bottom"),
            left: px("--ronin-safe-left"),
            right: px("--ronin-safe-right"),
            top: px("--ronin-safe-top"),
        },
    };
}

/** Throwaway (zones overlay): the opponents' strip lines and the hand a four-meld seat keeps, for `zones-overlay.ts`. */
function zoneLengths({ strips }: BoardGeometry): (readonly [string, string])[] {
    if (strips === null) {
        return [];
    }
    const { rw } = strips;
    const lengths = {
        "left-line": strips.left.line,
        "meld-gap": strips.gap,
        "right-line": strips.right.line,
        "side-hand2": handLength({ drawn: true, rw, seat: "left", tiles: 2 }),
        "top-hand2": handLength({ drawn: true, rw, seat: "top", tiles: 2 }),
        "top-line": strips.top.anchor - strips.top.start,
    };
    return Object.entries(lengths).map(
        ([name, length]) => [`--zone-${name}`, `${length}px`] as const,
    );
}

/** Write each of the board's data attributes that changed. */
function writeData(board: HTMLElement, data: Readonly<Record<string, string>>): void {
    for (const [name, value] of Object.entries(data)) {
        if (board.dataset[name] !== value) {
            board.dataset[name] = value;
        }
    }
}

/**
 * Size the board from its own box and the slots its page fills (`boardGeometry`): its family, chrome and play switches'
 * form as `data-board-family` / `data-board-chrome` / `data-board-switches` and its sizes as
 * `--geo-<name>` on the board, measured once its first render is in the document and again as its box or its slots change, until it leaves; and
 * lay out the opponents' strips in the rooms it leaves them (`stripLayout`) as `--<seat>-meld-<n>-*` lengths and the
 * own melds in their row (`ownMeldTile`) as `--own-meld-w`, again as what they hold changes. An empty box (a hidden board) changes nothing and the board stays watched.
 */
class SizeBoard extends AsyncDirective {
    private board: HTMLElement | null = null;
    private observer: ResizeObserver | null = null;
    private frame: number | null = null;
    private slots: BoardSlots | null = null;
    private strips: StripContents | null = null;
    private geometry: BoardGeometry | null = null;
    private plane: PlaneGeometry | null = null;
    private readonly written = new Map<string, string>();
    private readonly writtenOnPlane = new Map<string, string>();

    constructor(partInfo: PartInfo) {
        super(partInfo);
        if (partInfo.type !== PartType.ELEMENT) {
            throw new Error("sizeBoard belongs on an element");
        }
    }

    render(_slots: BoardSlots, _strips: StripContents): typeof nothing {
        return nothing;
    }

    override update(
        part: ElementPart,
        [slots, strips]: [BoardSlots, StripContents],
    ): typeof nothing {
        if (part.element instanceof HTMLElement) {
            this.board = part.element;
        }
        const moved = this.slots?.band !== slots.band;
        const changed = JSON.stringify(this.strips) !== JSON.stringify(strips);
        this.slots = slots;
        this.strips = strips;
        this.schedule(moved, changed);
        return nothing;
    }

    private schedule(moved: boolean, changed: boolean): void {
        if (this.observer === null) {
            queueMicrotask(() => this.observe());
        } else if (moved) {
            queueMicrotask(() => this.resize());
        } else if (changed) {
            queueMicrotask(() => this.relayout());
        }
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

    private relayout(): void {
        const { board, geometry, plane } = this;
        if (this.observer !== null && board !== null && geometry !== null && plane !== null) {
            this.write(board, geometry, plane);
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
        const { geometry, plane } = solveBoard({
            appliedEdges: edges?.appliedEdges ?? NO_EDGES,
            box: { height, width },
            safeInsets: edges?.safeInsets ?? NO_EDGES,
            slots,
        });
        if (delivering && edges !== null && geometry.gutter !== edges.gutter) {
            this.frame = requestAnimationFrame(() => {
                this.frame = null;
                this.write(board, geometry, plane);
            });
            return;
        }
        this.write(board, geometry, plane);
    }

    private cancelFrame(): void {
        if (this.frame !== null) {
            cancelAnimationFrame(this.frame);
            this.frame = null;
        }
    }

    private write(board: HTMLElement, geometry: BoardGeometry, plane: PlaneGeometry): void {
        const { chrome, family, lengths, strips, switches, tracks } = geometry;
        this.geometry = geometry;
        this.plane = plane;
        const laid =
            strips === null || this.strips === null ? {} : stripLengths(strips, this.strips);
        const ownTile = ownMeldTile(
            {
                cap: lengths["own-meld-tile"] ?? 0,
                gap: lengths["g"] ?? 0,
                ow: lengths["ow"] ?? 0,
                width: lengths["own-row-w"] ?? 0,
            },
            this.strips?.own ?? [],
        );
        writeData(board, {
            boardChrome: chrome,
            boardFamily: family,
            boardSwitches: switches,
        });
        writeValues(
            board,
            new Map([
                ...Object.entries(lengths).map(
                    ([name, length]) => [`--geo-${name}`, `${length}px`] as const,
                ),
                ["--geo-shell-columns", tracks.columns],
                ["--geo-shell-rows", tracks.rows],
                ["--own-meld-w", `${ownTile}px`],
                ...zoneLengths(geometry),
                ...Object.entries(laid).map(
                    ([name, length]) => [`--${name}`, `${length}px`] as const,
                ),
            ]),
            this.written,
        );
        this.writePlane(board, geometry, plane);
    }

    private writePlane(board: HTMLElement, geometry: BoardGeometry, plane: PlaneGeometry): void {
        const surface = board.querySelector<HTMLElement>(":scope .board-surface");
        if (surface !== null) {
            const zone = planeZone(plane, geometry, pageEdges(board)?.appliedEdges ?? NO_EDGES);
            writeValues(surface, planeValues(plane, zone, this.strips), this.writtenOnPlane);
        }
    }
}

function solveBoard(input: BoardInput): { geometry: BoardGeometry; plane: PlaneGeometry } {
    const geometry = boardGeometry(input);
    return { geometry, plane: planeGeometry(input, geometry) };
}

function writeValues(
    element: HTMLElement,
    values: ReadonlyMap<string, string>,
    written: Map<string, string>,
): void {
    for (const name of written.keys()) {
        if (!values.has(name)) {
            element.style.removeProperty(name);
            written.delete(name);
        }
    }
    for (const [name, value] of values) {
        if (written.get(name) !== value) {
            element.style.setProperty(name, value);
            written.set(name, value);
        }
    }
}

const SCREEN_ONLY = new Set(["table-h", "table-top"]);

function planeValues(
    { camera, geometry, height, left, top }: PlaneGeometry,
    zone: PlaneZone,
    contents: StripContents | null,
): ReadonlyMap<string, string> {
    const { lengths, strips, tracks } = geometry;
    const laid = strips === null || contents === null ? {} : stripLengths(strips, contents);
    return new Map([
        ...Object.entries(lengths)
            .filter(([name]) => !SCREEN_ONLY.has(name))
            .map(([name, length]) => [`--geo-${name}`, `${length}px`] as const),
        ["--geo-shell-columns", tracks.columns],
        ["--geo-shell-rows", tracks.rows],
        ["--geo-plane-top", `${top}px`],
        ["--geo-plane-left", `${left}px`],
        ["--geo-plane-w", `${geometry.box.width}px`],
        ["--geo-plane-h", `${height}px`],
        ["--geo-plane-camera", `${camera.distance}px`],
        ["--geo-plane-tilt", `${camera.tilt}deg`],
        ["--geo-plane-zone-top", `${zone.top}px`],
        ["--geo-plane-zone-side", `${zone.side}px`],
        ["--geo-plane-zone-bottom", `${zone.bottom}px`],
        ["--geo-plane-zone-floor", `${zone.floorHalf}px`],
        ...zoneLengths(geometry),
        ...Object.entries(laid).map(([name, length]) => [`--${name}`, `${length}px`] as const),
    ]);
}

export const sizeBoard = directive(SizeBoard);
export type { StripContents };
