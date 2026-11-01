import {
    CENTRE_ASPECT,
    CORE_TILES,
    type ChromeTier,
    DESKTOP_CENTRE_SHARE,
    DESKTOP_CHROME,
    DESKTOP_CORE_CAP,
    DESKTOP_OWN_CAP_HEIGHT,
    DESKTOP_OWN_CAP_WIDTH,
    type DesktopChrome,
    FACE_FLOOR,
    FULL_HAND,
    LARGE_CHROME_HEIGHT,
    LARGE_CHROME_WIDTH,
    OWN_MELD_SCALE,
    PHONE_HEIGHT,
    RIVER_GAP_SHARE,
    SHORT_DESKTOP_HEIGHT,
    SIDE_REACH_TILES,
    SMALL_CHROME_WIDTH,
    TILE_ASPECT,
    TILE_EDGE_SHARE,
} from "./board-constants";

type BoardFamily = "phone" | "desktop" | "short-desktop" | "upright";

interface BoardBox {
    readonly width: number;
    readonly height: number;
}

/** The board's sizes in px, by the stylesheet's length names (`rw` for `--rw`). */
type BoardLengths = Readonly<Record<string, number>>;

interface BoardGeometry {
    readonly family: BoardFamily;
    readonly chrome: ChromeTier;
    readonly box: BoardBox;
    readonly lengths: BoardLengths;
}

/** The band's control row past its control: the room the decisions' row keeps over it (px). */
const BAND_ROW_EXTRA = 20;

/** What the core's room keeps beside it on a desktop's width, past the margins (px). */
const CORE_ROOM_SIDES = 24;

/** The own badge's lane over the hand's tiles (px). */
const OWN_BADGE_LANE = 2;

function classifyFamily({ width, height }: BoardBox): BoardFamily {
    if (width < height) {
        return "upright";
    }
    if (height < PHONE_HEIGHT) {
        return "phone";
    }
    if (height < SHORT_DESKTOP_HEIGHT && width >= SMALL_CHROME_WIDTH) {
        return "short-desktop";
    }
    return "desktop";
}

function classifyChrome({ width, height }: BoardBox): ChromeTier {
    if (width < SMALL_CHROME_WIDTH || height < PHONE_HEIGHT) {
        return "small";
    }
    if (width >= LARGE_CHROME_WIDTH && height >= LARGE_CHROME_HEIGHT) {
        return "large";
    }
    return "regular";
}

/** What the desktop's river tile is solved from: the board's height, its chrome and the rooms already known. */
interface DesktopRooms {
    readonly height: number;
    readonly tier: DesktopChrome;
    readonly ownFit: number;
    readonly coreCap: number;
    readonly coreRoomW: number;
    readonly rowRiseFixed: number;
}

/** The largest river tile each of the desktop's rooms holds (`_grid.scss`'s `--rw-by-*`), the smallest binding. */
function desktopRiverTile({
    coreCap,
    coreRoomW,
    height,
    ownFit,
    rowRiseFixed,
    tier,
}: DesktopRooms): number {
    const { bandGap, controlH, coreGap, m, sep } = tier;
    const spare = 1 - DESKTOP_CENTRE_SHARE;
    const ownRow = TILE_ASPECT * TILE_ASPECT;
    const ownEdge = TILE_EDGE_SHARE * TILE_ASPECT;
    const bandTileShare = Math.max(0, 2 * Math.min(OWN_MELD_SCALE, TILE_ASPECT) - ownRow);
    const heightTiles = CORE_TILES + spare * TILE_ASPECT;
    const widthTiles = CORE_TILES + spare * SIDE_REACH_TILES;
    const rowsAtMargin = heightTiles + spare * ownRow;
    const rowsAtEdge = heightTiles + spare * (ownRow + ownEdge);
    const heightRoom = spare * (height - m - coreGap - sep);
    const bandFixed = sep + bandGap + controlH + BAND_ROW_EXTRA + rowRiseFixed;
    const bandRoom = spare * (height - m - bandFixed);
    const bandRise = spare * bandTileShare;
    return Math.floor(
        Math.min(
            ownFit / TILE_ASPECT,
            (heightRoom - spare * m) / rowsAtMargin,
            heightRoom / rowsAtEdge,
            (bandRoom - spare * m) / (rowsAtMargin + bandRise),
            bandRoom / (rowsAtEdge + bandRise),
            (spare * coreCap) / CORE_TILES,
            (spare * coreRoomW) / widthTiles,
        ),
    );
}

/** The desktop's root sizes and what its root solve reads (`_grid.scss`'s default and chrome blocks), in px. */
function desktopLengths(box: BoardBox, chrome: ChromeTier): BoardLengths {
    const { width, height } = box;
    const tier = DESKTOP_CHROME[chrome];
    const { bandGap, controlH, coreGap, m, ownBadgeH, ownInline, sep, switchGap } = tier;
    const ownCap = Math.min(DESKTOP_OWN_CAP_WIDTH * width, DESKTOP_OWN_CAP_HEIGHT * height);
    const ownFit = Math.min(ownCap, (width - 2 * m - ownInline) / FULL_HAND);
    const coreCap = DESKTOP_CORE_CAP * height;
    const coreRoomW = width - 2 * m - CORE_ROOM_SIDES;
    const rowRiseFixed = chrome === "small" ? ownBadgeH + OWN_BADGE_LANE + switchGap - bandGap : 0;
    const rw = desktopRiverTile({ coreCap, coreRoomW, height, ownFit, rowRiseFixed, tier });
    const rh = rw * TILE_ASPECT;
    const ow = Math.floor(rw * TILE_ASPECT);
    const oh = ow * TILE_ASPECT;

    const handBottom = Math.max(m, ow * TILE_EDGE_SHARE);
    const handTop = height - handBottom - oh;
    const coreRoomH = height - m - handBottom - oh - coreGap - sep;
    const ownMeldTile = Math.max(FACE_FLOOR, Math.min(OWN_MELD_SCALE * rw, ow));
    const ownMeldRise = Math.max(0, 2 * ownMeldTile - oh);
    const bandLift = ownMeldRise;
    const ownRise = ownMeldRise + ownBadgeH + OWN_BADGE_LANE;
    const bandBottom = handTop - bandGap - bandLift;
    const switchesBottom = Math.min(bandBottom, handTop - ownRise - switchGap);
    const rowBottom = chrome === "small" ? switchesBottom : bandBottom;
    const rowRise = bandBottom - rowBottom;
    const bandReserve = bandGap + controlH + BAND_ROW_EXTRA + rowRise + bandLift;
    const coreRoomBand = handTop - bandReserve - m - sep;

    const core = Math.min(
        coreRoomH - rh,
        coreRoomBand - rh,
        coreCap,
        coreRoomW - SIDE_REACH_TILES * rw,
    );
    const centre = core - CORE_TILES * rw;
    const centreWidth = Math.max(
        centre,
        Math.min(centre * CENTRE_ASPECT, coreRoomW - (SIDE_REACH_TILES + CORE_TILES) * rw),
    );
    const coreTopSlot = m + rh + sep;
    const coreTopFree = (coreRoomH - rh - core) / 2;
    const coreTop = Math.min(coreTopSlot + coreTopFree, handTop - bandReserve - core);

    return Object.fromEntries([
        ["band-bottom", bandBottom],
        ["band-gap", bandGap],
        ["band-lift", bandLift],
        ["band-reserve", bandReserve],
        ["c", centre],
        ["control-h", controlH],
        ["core", core],
        ["core-gap", coreGap],
        ["core-room-band", coreRoomBand],
        ["core-room-h", coreRoomH],
        ["core-room-w", coreRoomW],
        ["core-top", coreTop],
        ["cx", width / 2],
        ["cy", coreTop + core / 2],
        ["g", Math.round(RIVER_GAP_SHARE * rw)],
        ["h", centre / 2],
        ["hand-bottom", handBottom],
        ["hand-top", handTop],
        ["hx", centreWidth / 2],
        ["m", m],
        ["oh", oh],
        ["ow", ow],
        ["own-badge-h", ownBadgeH],
        ["own-fit", ownFit],
        ["own-inline", ownInline],
        ["own-meld-rise", ownMeldRise],
        ["own-meld-tile", ownMeldTile],
        ["own-rise", ownRise],
        ["rh", rh],
        ["row-rise", rowRise],
        ["rw", rw],
        ["sep", sep],
        ["switch-gap", switchGap],
        ["switches-bottom", switchesBottom],
        ["w", centreWidth],
    ]);
}

/**
 * The board's geometry from its box: its family and chrome tier, classified as the stylesheet's container queries do,
 * and its sizes in px for the families sized here (the desktop's); an empty or non-finite box has no sizes.
 */
function boardGeometry(box: BoardBox): BoardGeometry {
    const family = classifyFamily(box);
    const chrome = classifyChrome(box);
    const sized =
        Number.isFinite(box.width) &&
        Number.isFinite(box.height) &&
        box.width > 0 &&
        box.height > 0;
    const lengths = sized && family === "desktop" ? desktopLengths(box, chrome) : {};
    return Object.freeze({
        box: Object.freeze({ height: box.height, width: box.width }),
        chrome,
        family,
        lengths: Object.freeze(lengths),
    });
}

export { boardGeometry };
export type { BoardBox, BoardFamily, BoardGeometry, BoardLengths };
