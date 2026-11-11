/**
 * Throwaway: `?zones=1` paints the space the board reserves for each zone, whatever tiles are on the table. Seats are
 * numbered 0 bottom, 1 right, 2 top, 3 left. `window.RONIN_ZONES` holds the same rects.
 */
const COLORS = {
    board: "#ff2d95",
    centre: "#ffffff",
    dora: "#bf5af2",
    hand: "#00c8ff",
    melds: "#ff3b30",
    name: "#ff9500",
    river: "#ffd60a",
} as const;

type ZoneKind = keyof typeof COLORS;

interface Zone {
    readonly kind: ZoneKind;
    readonly label: string;
    readonly x: number;
    readonly y: number;
    readonly w: number;
    readonly h: number;
}

const SEATS = ["bottom", "right", "top", "left"] as const;
const MELDS = 4;
const OWN_FULL_HAND = 14.6;
const OWN_TWO_TILE_HAND = 2.6;
const TILE_ASPECT = 4 / 3;

function fromRect(kind: ZoneKind, label: string, element: Element | null): Zone[] {
    if (element === null) {
        return [];
    }
    const { x, y, width, height } = element.getBoundingClientRect();
    return [{ h: height, kind, label, w: width, x, y }];
}

/** Four pons (2 upright + 1 sideways) at `tile` with their gaps, or the room a two-tile hand leaves when shorter. */
function meldsAlong(tile: number, gap: number, room: number): number {
    return Math.min(MELDS * (2 + TILE_ASPECT) * tile + (MELDS - 1) * gap, room);
}

function boardZones(board: HTMLElement): Zone[] {
    const style = board.style;
    const px = (name: string): number => Number.parseFloat(style.getPropertyValue(name)) || 0;
    const box = board.getBoundingClientRect();
    const strip = (seat: string): DOMRect | null =>
        board.querySelector(`.board-strip--${seat}`)?.getBoundingClientRect() ?? null;
    const rw = px("--geo-rw");
    const rh = px("--geo-rh");
    const reach = px("--geo-full-reach");
    const gap = px("--zone-meld-gap");
    const deep = 2 * rw;
    const zones: Zone[] = [
        ...fromRect("board", "board", board),
        ...SEATS.flatMap((seat, index) => fromRect("name", `name ${index}`, board.querySelector(`.nameplate--${seat}`))),
        ...fromRect("centre", "centre", board.querySelector('[data-area="center"]')),
        ...fromRect("dora", "dora", board.querySelector(".board-dora")),
        ...SEATS.flatMap((seat, index) =>
            fromRect("river", `river ${index}`, board.querySelector(`[data-area="${seat}-discards"]`)),
        ),
    ];

    const ow = px("--geo-ow");
    const oh = px("--geo-oh");
    const ownTile = px("--geo-own-meld-tile");
    const ownLeft = box.x + px("--geo-own-start");
    const ownTop = box.y + px("--geo-hand-top");
    const ownRow = px("--geo-own-row-w");
    const ownMelds = meldsAlong(ownTile, px("--geo-g"), ownRow - OWN_TWO_TILE_HAND * ow);
    zones.push(
        { h: 2 * ownTile, kind: "melds", label: "melds 0", w: ownMelds, x: ownLeft + ownRow - ownMelds, y: ownTop + oh - 2 * ownTile },
        { h: oh, kind: "hand", label: "hand 0", w: OWN_FULL_HAND * ow, x: ownLeft, y: ownTop },
    );

    const right = strip("right");
    if (right !== null) {
        const line = px("--zone-right-line");
        const along = meldsAlong(rw, gap, line - px("--zone-side-hand2"));
        zones.push(
            { h: along, kind: "melds", label: "melds 1", w: deep, x: right.right - deep, y: right.bottom - line },
            { h: reach, kind: "hand", label: "hand 1", w: rh, x: right.right - rh, y: right.bottom - reach },
        );
    }
    const top = strip("top");
    if (top !== null) {
        const line = px("--zone-top-line");
        const along = meldsAlong(rw, gap, line - px("--zone-top-hand2"));
        zones.push(
            { h: deep, kind: "melds", label: "melds 2", w: along, x: top.right - line, y: top.top },
            { h: rh, kind: "hand", label: "hand 2", w: reach, x: top.right - reach, y: top.top },
        );
    }
    const left = strip("left");
    if (left !== null) {
        const line = px("--zone-left-line");
        const along = meldsAlong(rw, gap, line - px("--zone-side-hand2"));
        zones.push(
            { h: along, kind: "melds", label: "melds 3", w: deep, x: left.left, y: left.top + line - along },
            { h: reach, kind: "hand", label: "hand 3", w: rh, x: left.left, y: left.top },
        );
    }
    return zones;
}

function paint(layer: HTMLElement, zones: readonly Zone[]): void {
    layer.replaceChildren(
        ...zones.map((zone) => {
            const color = COLORS[zone.kind];
            const box = document.createElement("div");
            box.style.cssText = `position:absolute;box-sizing:border-box;left:${zone.x}px;top:${zone.y}px;width:${zone.w}px;height:${zone.h}px;background:${color}${zone.kind === "board" ? "00" : "55"};border:2px solid ${color}`;
            const label = document.createElement("span");
            label.textContent = `${zone.label} ${Math.round(zone.w)}x${Math.round(zone.h)}`;
            label.style.cssText = `position:absolute;left:0;top:0;padding:1px 3px;background:#000c;color:${color};font:bold 11px/12px sans-serif;white-space:nowrap`;
            box.append(label);
            return box;
        }),
    );
}

function startZones(): void {
    const layer = document.createElement("div");
    layer.style.cssText = "position:fixed;inset:0;z-index:2147483647;pointer-events:none";
    let drawn = "";
    setInterval(() => {
        const board = document.querySelector<HTMLElement>(".game-board[data-board-family]");
        const zones = board === null ? [] : boardZones(board);
        const next = JSON.stringify(zones);
        if (next === drawn) {
            return;
        }
        drawn = next;
        if (!layer.isConnected) {
            document.body.append(layer);
        }
        paint(layer, zones);
        Object.assign(window, { RONIN_ZONES: zones });
    }, 250);
}

if (new URLSearchParams(location.search).has("zones")) {
    startZones();
}
