/**
 * Throwaway: `?zones=1` paints the space the board reserves for each zone, whatever tiles are on the table. Seats are
 * numbered 0 bottom, 1 right, 2 top, 3 left. `window.RONIN_ZONES` holds the same rects.
 */
const COLORS = {
    bar: "#8e8e93",
    board: "#ff2d95",
    centre: "#ffffff",
    column: "#a2845e",
    corner: "#5e5ce6",
    decisions: "#34c759",
    dora: "#bf5af2",
    hand: "#00c8ff",
    melds: "#ff3b30",
    name: "#ff9500",
    river: "#ffd60a",
} as const;

type ZoneKind = keyof typeof COLORS;

const OUTLINED: ReadonlySet<ZoneKind> = new Set(["bar", "board", "column"]);

interface Zone {
    readonly kind: ZoneKind;
    readonly label: string;
    readonly rect: DOMRectReadOnly;
}

interface Edges {
    readonly left: number;
    readonly top: number;
    readonly right: number;
    readonly bottom: number;
}

interface BoardReader {
    readonly board: HTMLElement;
    readonly box: DOMRect;
    readonly px: (name: string) => number;
    readonly rectOf: (selector: string) => DOMRect | null;
}

const SEATS = ["bottom", "right", "top", "left"] as const;
const MELDS = 4;
const OWN_FULL_HAND = 14.6;
const OWN_TWO_TILE_HAND = 2.6;
const TILE_ASPECT = 4 / 3;

function zone(kind: ZoneKind, label: string, edges: Edges): Zone {
    const { bottom, left, right, top } = edges;
    return { kind, label, rect: new DOMRectReadOnly(left, top, right - left, bottom - top) };
}

function sized(kind: ZoneKind, label: string, rect: DOMRectReadOnly): Zone {
    return { kind, label, rect };
}

function fromRect(kind: ZoneKind, label: string, rect: DOMRect | null): Zone[] {
    return rect === null ? [] : [{ kind, label, rect }];
}

function readBoard(board: HTMLElement): BoardReader {
    const { style } = board;
    return {
        board,
        box: (board.querySelector(".board-layout") ?? board).getBoundingClientRect(),
        px: (name) => Number.parseFloat(style.getPropertyValue(name)) || 0,
        rectOf: (selector) => board.querySelector(selector)?.getBoundingClientRect() ?? null,
    };
}

/** Four pons (2 upright + 1 sideways) at `tile` with their gaps, or the room a two-tile hand leaves when shorter. */
function meldsAlong(tile: number, gap: number, room: number): number {
    return Math.min(MELDS * (2 + TILE_ASPECT) * tile + (MELDS - 1) * gap, room);
}

function drawnZones({ board, rectOf }: BoardReader): Zone[] {
    return [
        ...fromRect("board", "board", board.getBoundingClientRect()),
        ...SEATS.flatMap((seat, index) =>
            fromRect("name", `name ${index}`, rectOf(`.nameplate--${seat}`)),
        ),
        ...fromRect("centre", "centre", rectOf('[data-area="center"]')),
        ...fromRect("dora", "dora", rectOf(".board-dora")),
    ];
}

function columnZones({ board, box, px }: BoardReader): Zone[] {
    if (board.dataset.boardFamily !== "desktop") {
        return [];
    }
    const left = box.left + px("--geo-col-left");
    const right = box.left + px("--geo-col-right");
    const { bottom, top } = box;
    return [
        zone("column", "column", { bottom, left, right, top }),
        zone("bar", "bar 3", { bottom, left: box.left, right: left, top }),
        zone("bar", "bar 1", { bottom, left: right, right: box.right, top }),
    ];
}

/** Each river's reserve: a top or bottom river's third row run on to seven tiles, a side river's fourth row. */
function riverZones({ box, px, rectOf }: BoardReader): Zone[] {
    const [bottom, right, top, left] = SEATS.map((seat) =>
        rectOf(`[data-area="${seat}-discards"]`),
    );
    const drop = px("--geo-latest-drop-gap");
    const sideways = (TILE_ASPECT - 1) * px("--geo-rw") + drop;
    return [
        ...(bottom === null
            ? []
            : [
                  zone("river", "river 0", {
                      ...bottom.toJSON(),
                      bottom: bottom.bottom + drop,
                      right: box.left + px("--geo-reach-bottom-right"),
                  }),
              ]),
        ...(right === null
            ? []
            : [
                  zone("river", "river 1", {
                      ...right.toJSON(),
                      right: box.left + px("--geo-reach-right"),
                      top: right.top - sideways,
                  }),
              ]),
        ...(top === null
            ? []
            : [
                  zone("river", "river 2", {
                      ...top.toJSON(),
                      left: box.left + px("--geo-reach-top-left"),
                      top: top.top - drop,
                  }),
              ]),
        ...(left === null
            ? []
            : [
                  zone("river", "river 3", {
                      ...left.toJSON(),
                      bottom: left.bottom + sideways,
                      left: box.left + px("--geo-reach-left"),
                  }),
              ]),
    ];
}

/**
 * The core's corners: top-left and top-right above the side rivers, and the notices' toasts in the bottom-left one,
 * under the left river and over the own row.
 */
function cornerZones(reader: BoardReader, rivers: readonly Zone[]): Zone[] {
    const { box, px, rectOf } = reader;
    const centre = rectOf('[data-area="center"]');
    const leftLane = rectOf(".board-strip--left");
    const rightLane = rectOf(".board-strip--right");
    const rightRiver = rivers.find(({ label }) => label === "river 1")?.rect;
    if (!centre || !leftLane || !rightLane || !rightRiver) {
        return [];
    }
    const coreTop = box.top + px("--geo-core-top");
    return [
        zone("corner", "corner TL", {
            bottom: centre.top,
            left: leftLane.right,
            right: box.left + px("--geo-reach-top-left"),
            top: coreTop,
        }),
        zone("corner", "corner TR", {
            bottom: rightRiver.top,
            left: centre.right,
            right: rightLane.left,
            top: coreTop,
        }),
        toastsZone(reader),
    ];
}

function toastsZone({ box, px }: BoardReader): Zone {
    const top = box.top + px("--geo-toasts-top");
    const left = box.left + px("--geo-toasts-left");
    return zone("corner", "toasts", {
        bottom: top + px("--geo-toasts-height"),
        left,
        right: left + px("--geo-toasts-w"),
        top,
    });
}

/**
 * A desktop's decisions' corner at the core's bottom-right: past the bottom river's reserve to short of the right lane,
 * under the right river and over the own row's melds' rise.
 */
function decisionZones({ box, px }: BoardReader): Zone[] {
    if (px("--geo-decision-h") === 0) {
        return [];
    }
    return [
        zone("decisions", "decisions", {
            bottom: box.top + px("--geo-decision-bottom"),
            left: box.left + px("--geo-actions-left"),
            right: box.right - px("--geo-actions-right"),
            top: box.top + px("--geo-decision-top"),
        }),
    ];
}

function ownZones({ box, px }: BoardReader): Zone[] {
    const ow = px("--geo-ow");
    const oh = px("--geo-oh");
    const ownTile = px("--geo-own-meld-tile");
    const left = box.left + px("--geo-own-start");
    const top = box.top + px("--geo-hand-top");
    const row = px("--geo-own-row-w");
    const melds = meldsAlong(ownTile, px("--geo-g"), row - OWN_TWO_TILE_HAND * ow);
    return [
        sized(
            "melds",
            "melds 0",
            new DOMRectReadOnly(left + row - melds, top + oh - 2 * ownTile, melds, 2 * ownTile),
        ),
        sized("hand", "hand 0", new DOMRectReadOnly(left, top, OWN_FULL_HAND * ow, oh)),
    ];
}

interface Strip {
    readonly deep: number;
    readonly gap: number;
    readonly reach: number;
    readonly rh: number;
    readonly rw: number;
}

function readStrip({ px }: BoardReader): Strip {
    const rw = px("--geo-rw");
    return {
        deep: 2 * rw,
        gap: px("--zone-meld-gap"),
        reach: px("--geo-full-reach"),
        rh: px("--geo-rh"),
        rw,
    };
}

function rightZones(reader: BoardReader, strip: Strip): Zone[] {
    const right = reader.rectOf(".board-strip--right");
    if (right === null) {
        return [];
    }
    const { deep, gap, reach, rh, rw } = strip;
    const line = reader.px("--zone-right-line");
    const melds = meldsAlong(rw, gap, line - reader.px("--zone-side-hand2"));
    return [
        sized(
            "melds",
            "melds 1",
            new DOMRectReadOnly(right.right - deep, right.bottom - line, deep, melds),
        ),
        sized(
            "hand",
            "hand 1",
            new DOMRectReadOnly(right.right - rh, right.bottom - reach, rh, reach),
        ),
    ];
}

function topZones(reader: BoardReader, strip: Strip): Zone[] {
    const top = reader.rectOf(".board-strip--top");
    if (top === null) {
        return [];
    }
    const { deep, gap, reach, rh, rw } = strip;
    const line = reader.px("--zone-top-line");
    const melds = meldsAlong(rw, gap, line - reader.px("--zone-top-hand2"));
    return [
        sized("melds", "melds 2", new DOMRectReadOnly(top.right - line, top.top, melds, deep)),
        sized("hand", "hand 2", new DOMRectReadOnly(top.right - reach, top.top, reach, rh)),
    ];
}

function leftZones(reader: BoardReader, strip: Strip): Zone[] {
    const left = reader.rectOf(".board-strip--left");
    if (left === null) {
        return [];
    }
    const { deep, gap, reach, rh, rw } = strip;
    const line = reader.px("--zone-left-line");
    const melds = meldsAlong(rw, gap, line - reader.px("--zone-side-hand2"));
    return [
        sized(
            "melds",
            "melds 3",
            new DOMRectReadOnly(left.left, left.top + line - melds, deep, melds),
        ),
        sized("hand", "hand 3", new DOMRectReadOnly(left.left, left.top, rh, reach)),
    ];
}

function sideZones(reader: BoardReader): Zone[] {
    const strip = readStrip(reader);
    return [...rightZones(reader, strip), ...topZones(reader, strip), ...leftZones(reader, strip)];
}

function boardZones(board: HTMLElement): Zone[] {
    const reader = readBoard(board);
    const rivers = riverZones(reader);
    return [
        ...columnZones(reader),
        ...drawnZones(reader),
        ...rivers,
        ...cornerZones(reader, rivers),
        ...decisionZones(reader),
        ...ownZones(reader),
        ...sideZones(reader),
    ];
}

function exported(zones: readonly Zone[]): object[] {
    return zones.map(({ kind, label, rect }) => ({
        ...rect.toJSON(),
        h: rect.height,
        kind,
        label,
        w: rect.width,
    }));
}

function paintZone({ kind, label, rect }: Zone): HTMLElement {
    const color = COLORS[kind];
    const box = document.createElement("div");
    const fill = OUTLINED.has(kind) ? "00" : "55";
    box.style.cssText = `position:absolute;box-sizing:border-box;left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px;background:${color}${fill};border:2px solid ${color}`;
    const caption = document.createElement("span");
    caption.textContent = `${label} ${Math.round(rect.width)}x${Math.round(rect.height)}`;
    caption.style.cssText = `position:absolute;left:0;top:0;padding:1px 3px;background:#000c;color:${color};font:bold 11px/12px sans-serif;white-space:nowrap`;
    box.append(caption);
    return box;
}

function currentZones(): Zone[] {
    const board = document.querySelector<HTMLElement>(".game-board[data-board-family]");
    return board === null ? [] : boardZones(board);
}

function startZones(): void {
    const layer = document.createElement("div");
    layer.style.cssText = "position:fixed;inset:0;z-index:2147483647;pointer-events:none";
    let drawn = "";
    setInterval(() => {
        const zones = currentZones();
        const rects = exported(zones);
        const next = JSON.stringify(rects);
        if (next === drawn) {
            return;
        }
        drawn = next;
        if (!layer.isConnected) {
            document.body.append(layer);
        }
        layer.replaceChildren(...zones.map(paintZone));
        Object.assign(window, { RONIN_ZONES: rects });
    }, 250);
}

if (new URLSearchParams(location.search).has("zones")) {
    startZones();
}
