import { type Page } from "playwright";

import {
    type Box,
    type GroupedBox,
    type GroupedQuad,
    type Point,
    type Size,
    describeSize,
} from "./boxes.ts";

/**
 * A play switch: its box, the state it announces, and how it shows it apart from colour (its lamp a bar, wider than
 * tall, only while on) and by its fill (the lamp's background not transparent).
 */
export interface SwitchMeasure {
    readonly box: Box;
    readonly checked: boolean;
    readonly bar: boolean;
    readonly filled: boolean;
}

export interface BoardMeasure {
    readonly board: Box;
    readonly chrome: string | null;
    readonly boardScroll: Size;
    readonly boardClient: Size;
    readonly aside: {
        readonly box: Box;
        readonly scroll: Size;
        readonly overflowY: string;
        /** A storybook's switches, which lie below the board, the page scrolling to them. */
        readonly story: boolean;
    } | null;
    readonly overlay: {
        readonly box: Box;
        readonly scroll: Size;
        readonly client: Size;
        /** The panel's shown controls, which nothing may cover though a notice may stand over the panel. */
        readonly controls: readonly Box[];
    } | null;
    readonly tiles: readonly Box[];
    readonly hiddenTiles: number;
    /** The board's parts that never overlap, by group; not the cog, which reserves no room and stands over them. */
    readonly grouped: readonly GroupedBox[];
    readonly localTiles: readonly Box[];
    /**
     * The local hand tiles' slots (each tile's `.hand-tile`, its tap target), as painted: a held-back face's recess
     * inside its slot does not shrink them, any transform of the slot or above it does; NaN for a tile with no slot.
     */
    readonly localTileSizes: readonly Size[];
    /** Every board tile but the local hand's and the decision buttons': rivers, other seats, melds, dora. */
    readonly otherTiles: readonly Box[];
    readonly actions: readonly Box[];
    /** The decision's band and its buttons, which must sit wholly in its box, never scrolled or clipped. */
    readonly decisionBand: {
        readonly box: Box;
        readonly buttons: readonly Box[];
    } | null;
    /** Text that shows whole or not at all (the status's word, a name's end, a plate's marks), clipped. */
    readonly clippedWords: readonly string[];
    /** The calls shown by their seats. */
    readonly callouts: readonly Box[];
    /** What an open offer refers to: the latest discard, a kan a chankan offer may rob. */
    /** The decision timer's slot. */
    readonly timer: Box | null;
    readonly timerInk: Box | null;
    /** The decision's first toggle (riichi), pressed or not. */
    readonly toggle: Box | null;
    /** The play switches on the band. */
    readonly switches: readonly SwitchMeasure[];
    /** The table's surface and zones, which run on under the page's insets toward the screen's edges. */
    readonly zones: Box | null;
    readonly fonts: readonly { readonly name: string; readonly px: number }[];
    readonly centerTexts: readonly GroupedBox[];
    readonly family: string;
    /** The play switches' form the geometry emitted (`data-board-switches`). */
    readonly switchesForm: string;
    readonly furiten: Box | null;
    readonly noticesField: Box | null;
    readonly reservedToastsPlace: Box | null;
    readonly nameplates: readonly Box[];
    /** Each badge by its seat's position, whose fixed place the decisions stories compare across checkpoints. */
    readonly badges: readonly GroupedBox[];
    /** Each badge's pill, by seat. */
    readonly platePills: readonly GroupedBox[];
    /** Each badge's riichi stick under its pill while one stands, by seat. */
    readonly plateSticks: readonly GroupedBox[];
    /** The rivers' tiles by seat, and every opponent strip's tiles (hand and melds) by seat. */
    readonly riverTiles: readonly GroupedBox[];
    /** The rivers' tiles by seat, less the latest discard, which lies apart from its slot toward its seat. */
    readonly settledRiverTiles: readonly GroupedBox[];
    /** The rivers' tiles by seat, each its corners as the table's camera shows them, clockwise from its top left. */
    readonly riverQuads: readonly GroupedQuad[];
    readonly stripTiles: readonly GroupedBox[];
    /** The whole names of the badges that shorten theirs, their head cut by its ellipsis. */
    readonly cutNames: readonly string[];
    /** Each side strip's full hand (fourteen tiles, the drawn one apart) as its place reserves it, by seat. */
    readonly handReach: readonly GroupedBox[];
    /**
     * The laid widths, before the frames turn them, of a river tile, of every opponent's concealed hand tile and of the
     * widest own hand tile, unrounded (a held-back tile's recess never counts).
     */
    readonly tileScale: {
        readonly river: number | null;
        /** The river tile as the camera shows it across the core's middle: the laid tile times the centre's shown share. */
        readonly shownRiver: number | null;
        readonly hands: readonly number[];
        readonly own: number | null;
    };
    readonly center: Box | null;
    /** The centre's corners as the table's camera shows them, clockwise from its top left. */
    readonly centerQuad: readonly Point[] | null;
    readonly opponentFaces: readonly Box[];
    /** The table's pieces as laid, before the camera tilts them: the spec's proportions and floors hold here. */
    readonly plane: PlaneMeasure;
    /** The share of a lying tile's width its edge reaches below its face, as the board's geometry writes it. */
    readonly edgeShare: number;
    /** The page's corner on the board: the settings cog, which a panel over the board may cover. */
    readonly menu: readonly Box[];
}

export interface PlaneMeasure {
    readonly center: Box | null;
    readonly riverTiles: readonly GroupedBox[];
    readonly settledRiverTiles: readonly GroupedBox[];
    readonly opponentFaces: readonly Box[];
}

export function measureBoard(page: Page): Promise<BoardMeasure> {
    return page.evaluate(({ centerTextSelectors, fontSelectors }) => {
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function box(element: Element): Box {
            const rect = element.getBoundingClientRect();
            return {
                height: rect.height,
                left: rect.left + window.scrollX,
                top: rect.top + window.scrollY,
                width: rect.width,
            };
        }
        /**
         * The board's content size, without the zones: the surface and its zones run on under a page's safe-area
         * insets past the board's box by design (the spec's Surface), decoration that takes no input.
         */
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function contentScroll(element: Element): Size {
            const zones = element.querySelector(".board-zones");
            if (!(zones instanceof HTMLElement)) {
                return { height: element.scrollHeight, width: element.scrollWidth };
            }
            zones.style.display = "none";
            const size = { height: element.scrollHeight, width: element.scrollWidth };
            zones.style.removeProperty("display");
            return size;
        }
        const board = document.querySelector(".game-board");
        if (board === null) {
            throw new Error("no .game-board");
        }
        const tableTiles = [...board.querySelectorAll(".tile")].filter(
            (tile) =>
                tile.closest(".board-overlay") === null &&
                tile.closest(".decision-controls__tiles") === null,
        );
        const grouped: GroupedBox[] = [];
        for (const tile of tableTiles) {
            const area = tile.closest("[data-area], .board-dora");
            grouped.push({
                box: box(tile),
                group: area?.getAttribute("data-area") ?? "dora",
            });
        }
        for (const center of board.querySelectorAll(".board-center")) {
            grouped.push({ box: box(center), group: "center" });
        }
        for (const dora of board.querySelectorAll(".board-dora")) {
            grouped.push({ box: box(dora), group: "dora" });
        }
        const nameplates = [...board.querySelectorAll(".nameplate")]
            .filter((plate) => plate.checkVisibility())
            .map((plate) => ({
                box: box(plate),
                group: plate.className.split(" ")[1] ?? "nameplate",
            }));
        const onPhone = board.getAttribute("data-board-family") === "phone";
        const onePillBadges = new Set(["nameplate--top", "nameplate--bottom"]);
        grouped.push(
            ...nameplates.map((plate) => {
                const pill =
                    (onPhone && onePillBadges.has(plate.group)) ||
                    plate.group === "nameplate--bottom"
                        ? board.querySelector(`.${plate.group} .nameplate__pill`)
                        : null;
                return pill === null ? plate : { ...plate, box: box(pill) };
            }),
        );
        const furitenMark = board.querySelector(".board-furiten");
        if (furitenMark !== null) {
            grouped.push({ box: box(furitenMark), group: "furiten" });
        }
        const noticesField = board.querySelector(".board-notices");
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function seatOf(element: Element, frame: string): string {
            return (
                /--(?<seat>bottom|right|top|left)\b/u.exec(element.closest(frame)?.className ?? "")
                    ?.groups?.seat ?? ""
            );
        }
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function bySeat(within: Element, selector: string, frame: string): GroupedBox[] {
            return [...within.querySelectorAll(selector)].map((element) => ({
                box: box(element),
                group: seatOf(element, frame),
            }));
        }
        const centerElement = board.querySelector(".board-center");
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function cornersOf(element: Element): Point[] {
            return [
                ["0", "0"],
                ["100%", "0"],
                ["100%", "100%"],
                ["0", "100%"],
            ].map(([left, top]) => {
                const probe = document.createElement("span");
                probe.style.cssText = `position:absolute;left:${left};top:${top};width:0;height:0`;
                element.append(probe);
                const rect = probe.getBoundingClientRect();
                probe.remove();
                return { left: rect.left + window.scrollX, top: rect.top + window.scrollY };
            });
        }
        function shownRiverTile(tile: HTMLElement | null, center: Element | null): number | null {
            if (tile === null || !(center instanceof HTMLElement) || center.offsetWidth === 0) {
                return null;
            }
            const [topLeft, topRight, bottomRight, bottomLeft] = cornersOf(center);
            if (
                topLeft === undefined ||
                topRight === undefined ||
                bottomRight === undefined ||
                bottomLeft === undefined
            ) {
                return null;
            }
            const middle = (topRight.left - topLeft.left + bottomRight.left - bottomLeft.left) / 2;
            return (tile.offsetWidth * middle) / center.offsetWidth;
        }
        function measurePlane(within: Element): PlaneMeasure {
            const flat = document.createElement("style");
            flat.textContent =
                ".board-surface > *, .board-surface > :is(.board-rivers, .board-strips) > * { transform: none !important; }";
            document.head.append(flat);
            const center = within.querySelector(".board-center");
            const plane = {
                center: center === null ? null : box(center),
                opponentFaces: [
                    ...within.querySelectorAll(".board-strip .tile:not(.tile-back)"),
                ].map(box),
                riverTiles: bySeat(within, ".board-river .tile", ".board-river"),
                settledRiverTiles: bySeat(
                    within,
                    ".board-river :not(.discard-tile--last) > .tile",
                    ".board-river",
                ),
            };
            flat.remove();
            return plane;
        }
        const decisionActions = [
            ...board.querySelectorAll(".board-actions .decision-controls__action"),
        ].map(box);
        for (const action of decisionActions) {
            grouped.push({ box: action, group: "actions" });
        }
        const switchElements = [...board.querySelectorAll(".play-switch")];
        for (const element of switchElements) {
            grouped.push({ box: box(element), group: "switches" });
        }
        const switches = switchElements.map((element) => {
            const lamp = element.querySelector(".play-switch__lamp");
            const lampBox = lamp?.getBoundingClientRect();
            const fill = lamp === null ? "" : getComputedStyle(lamp).backgroundColor;
            return {
                bar: lampBox !== undefined && lampBox.width > 1.5 * lampBox.height,
                box: box(element),
                checked: element.getAttribute("aria-checked") === "true",
                filled: fill !== "" && fill !== "transparent" && fill !== "rgba(0, 0, 0, 0)",
            };
        });
        const zones = board.querySelector(".board-zones");
        const layoutBox = box(board.querySelector(".board-layout") ?? board);
        const boardStyle = getComputedStyle(board);
        const [toastsLeft, toastsTop, toastsWidth, toastsHeight] = [
            "--geo-toasts-left",
            "--geo-toasts-top",
            "--geo-toasts-w",
            "--geo-toasts-height",
        ].map((name) => Number.parseFloat(boardStyle.getPropertyValue(name)));
        const resultActions = [
            ...board.querySelectorAll(
                ".board-overlay .round-end-result__confirm:not(.round-end-result__ghost)",
            ),
        ].map(box);
        const actions = [...decisionActions, ...resultActions];
        const band = board.querySelector(".board-actions");
        const timer = board.querySelector(".board-actions .decision-timer");
        const timerWords: DOMRect[] = [];
        const timerText =
            timer === null ? null : document.createTreeWalker(timer, NodeFilter.SHOW_TEXT);
        for (
            let node = timerText?.nextNode() ?? null;
            node !== null;
            node = timerText?.nextNode() ?? null
        ) {
            const range = document.createRange();
            range.selectNodeContents(node);
            const rect = range.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                timerWords.push(rect);
            }
        }
        const inkLeft = Math.min(...timerWords.map((rect) => rect.left));
        const inkTop = Math.min(...timerWords.map((rect) => rect.top));
        const timerInk =
            timerWords.length === 0
                ? null
                : {
                      height: Math.max(...timerWords.map((rect) => rect.bottom)) - inkTop,
                      left: inkLeft + window.scrollX,
                      top: inkTop + window.scrollY,
                      width: Math.max(...timerWords.map((rect) => rect.right)) - inkLeft,
                  };
        const toggle = board.querySelector(
            ".board-actions .decision-controls__action[aria-pressed]",
        );
        const wholeWords = [".nameplate .player-name__tail"].join(", ");
        const clippedWords = [...board.querySelectorAll(wholeWords)]
            .filter((word) => {
                const shown = word.getBoundingClientRect();
                if (shown.width === 0) {
                    return false;
                }
                const clips = [".nameplate__name", ".nameplate"].flatMap(
                    (selector) => word.parentElement?.closest(selector) ?? [],
                );
                if (clips.some((clip) => clip.getBoundingClientRect().width <= 1)) {
                    return false;
                }
                const inside = clips.every((clip) => {
                    const outer = clip.getBoundingClientRect();
                    return (
                        shown.left >= outer.left - 1 &&
                        shown.right <= outer.right + 1 &&
                        shown.top >= outer.top - 1 &&
                        shown.bottom <= outer.bottom + 1
                    );
                });
                return !inside || word.scrollWidth > word.clientWidth + 1;
            })
            .map((word) => `${word.className.split(" ")[0]} "${word.textContent.trim()}"`);
        const aside = document.querySelector(".board-page__aside");
        const overlay = board.querySelector(".board-overlay__panel");
        const handReach = ["left", "right"].flatMap((seat) => {
            const strip = board.querySelector(`.board-strip--${seat} > .board-strip__frame`);
            if (strip === null) {
                return [];
            }
            const origin = box(strip);
            const style = getComputedStyle(strip);
            const reach = Number.parseFloat(style.getPropertyValue("--geo-full-reach"));
            const depth = Number.parseFloat(style.getPropertyValue("--bh"));
            const left = seat === "left" ? origin.left : origin.left - depth;
            const top = seat === "left" ? origin.top : origin.top - reach;
            return [{ box: { height: reach, left, top, width: depth }, group: seat }];
        });
        const riverTile = board.querySelector<HTMLElement>(
            ".board-river .tile:not(.discard-tile-riichi .tile)",
        );
        const ownWidths = [
            ...board.querySelectorAll<HTMLElement>(".board-local .board-area--bottom-hand .tile"),
        ].map((tile) => Number.parseFloat(getComputedStyle(tile).width));
        const tileScale = {
            hands: [
                ...board.querySelectorAll<HTMLElement>(".board-strip [data-area$='-hand'] .tile"),
            ].map((tile) => tile.offsetWidth),
            own: ownWidths.length === 0 ? null : Math.max(...ownWidths),
            river: riverTile?.offsetWidth ?? null,
            shownRiver: shownRiverTile(riverTile, centerElement),
        };
        const cutNames = [...board.querySelectorAll(".nameplate .player-name")]
            .filter((name) => {
                const head = name.querySelector(".player-name__head");
                return head !== null && head.scrollWidth > head.getBoundingClientRect().width + 1;
            })
            .map((name) => name.getAttribute("title") ?? "");
        const localTileElements = [
            ...board.querySelectorAll(".board-local .board-area--bottom-hand .tile"),
        ];
        const menu = [...board.querySelectorAll(".game-menu__toggle")].map(box);
        const centerTexts = [...board.querySelectorAll(centerTextSelectors)].map(
            (element, index) => ({
                box: box(element),
                group: `${element.className.split(" ")[0]}#${index}`,
            }),
        );
        const fonts = [...board.querySelectorAll(fontSelectors)].map((element) => ({
            name: element.className.split(" ")[0],
            px: Number.parseFloat(getComputedStyle(element).fontSize),
        }));
        return {
            actions,
            aside:
                aside === null
                    ? null
                    : {
                          box: box(aside),
                          overflowY: getComputedStyle(aside).overflowY,
                          scroll: { height: aside.scrollHeight, width: aside.scrollWidth },
                          story: aside.closest(".board-storybook, .decisions-storybook") !== null,
                      },
            badges: bySeat(board, ".nameplate", ".nameplate"),
            board: box(board),
            boardClient: { height: board.clientHeight, width: board.clientWidth },
            boardScroll: contentScroll(board),
            callouts: [...board.querySelectorAll(".board-callout")].map(box),
            center: centerElement === null ? null : box(centerElement),
            centerQuad: centerElement === null ? null : cornersOf(centerElement),
            centerTexts,
            chrome: board.getAttribute("data-board-chrome"),
            clippedWords,
            cutNames,
            decisionBand: band === null ? null : { box: box(band), buttons: decisionActions },
            edgeShare: Number.parseFloat(
                getComputedStyle(board).getPropertyValue("--tile-edge-share"),
            ),
            family: board.getAttribute("data-board-family") ?? "",
            fonts,
            furiten: furitenMark === null ? null : box(furitenMark),
            grouped,
            handReach,
            hiddenTiles: tableTiles.filter(
                (tile) =>
                    !tile.checkVisibility({
                        opacityProperty: true,
                        visibilityProperty: true,
                    }),
            ).length,
            localTileSizes: localTileElements.map((tile) => {
                const slot = tile.closest(".hand-tile");
                return slot === null ? { height: Number.NaN, width: Number.NaN } : box(slot);
            }),
            localTiles: localTileElements.map(box),
            menu,
            nameplates: nameplates.map((plate) => plate.box),
            noticesField: noticesField === null ? null : box(noticesField),
            opponentFaces: [...board.querySelectorAll(".board-strip .tile:not(.tile-back)")].map(
                box,
            ),
            otherTiles: tableTiles
                .filter((tile) => tile.closest(".board-area--bottom-hand, .board-actions") === null)
                .map(box),
            overlay:
                overlay === null
                    ? null
                    : {
                          box: box(overlay),
                          client: {
                              height: overlay.clientHeight,
                              width: overlay.clientWidth,
                          },
                          controls: [...overlay.querySelectorAll("button, a[href]")]
                              .filter((control) => control.getClientRects().length > 0)
                              .map(box),
                          scroll: {
                              height: overlay.scrollHeight,
                              width: overlay.scrollWidth,
                          },
                      },
            plane: measurePlane(board),
            platePills: bySeat(board, ".nameplate__pill", ".nameplate").filter(
                ({ box: part }) => part.width > 0 && part.height > 0,
            ),
            plateSticks: bySeat(board, ".nameplate__stick", ".nameplate").filter(
                ({ box: part }) => part.width > 0 && part.height > 0,
            ),
            reservedToastsPlace: [toastsLeft, toastsTop, toastsWidth, toastsHeight].every(
                Number.isFinite,
            )
                ? {
                      height: toastsHeight ?? 0,
                      left: layoutBox.left + (toastsLeft ?? 0),
                      top: layoutBox.top + (toastsTop ?? 0),
                      width: toastsWidth ?? 0,
                  }
                : null,
            riverQuads: [...board.querySelectorAll(".board-river .tile")].map((tile) => ({
                group: seatOf(tile, ".board-river"),
                quad: cornersOf(tile),
            })),
            riverTiles: bySeat(board, ".board-river .tile", ".board-river"),
            settledRiverTiles: bySeat(
                board,
                ".board-river :not(.discard-tile--last) > .tile",
                ".board-river",
            ),
            stripTiles: bySeat(board, ".board-strip .tile", ".board-strip"),
            switches,
            switchesForm: board.getAttribute("data-board-switches") ?? "",
            tileScale,
            tiles: tableTiles.map(box),
            timer: timer === null ? null : box(timer),
            timerInk,
            toggle: toggle === null ? null : box(toggle),
            zones: zones === null ? null : box(zones),
        };
    }, BOARD_TEXT);
}

/**
 * The text whose size has a floor, and the centre's pieces of text, which must not overlap one another. A nameplate
 * is table furniture: it keeps clear of the other plates and the centre, and anything else may stand over it.
 */
const BOARD_TEXT = {
    centerTextSelectors: [
        ".board-center__round",
        ".board-center__counts",
        ".board-center__riichi:not(.board-center__riichi--none)",
        ".board-center__score-line",
    ].join(", "),
    fontSelectors: [
        ".board-center__round",
        ".board-center__counts",
        ".board-center__score-line",
        ".board-center__hundreds",
        ".nameplate__name",
        ".board-callout",
    ].join(", "),
} as const;

function describeLocalTile(tiles: readonly Size[]): string {
    const [tile] = tiles;
    return tile ? `${tile.width.toFixed(1)}x${tile.height.toFixed(1)}` : "none";
}

/**
 * A plate is table furniture: anything may stand over it, so a plate counts against only the fixed places it is laid
 * out beside, the other plates and the centre.
 */
const PLATE_GROUP_PREFIX = "nameplate";
const PLATE_KEPT_CLEAR_OF: ReadonlySet<string> = new Set(["center"]);

export function isFurnitureOverlap(pair: string): boolean {
    const others = pair.split(" x ").filter((group) => !group.startsWith(PLATE_GROUP_PREFIX));
    return others.length === 1 && others.every((group) => !PLATE_KEPT_CLEAR_OF.has(group));
}

/** The own river's tiles, which the decision controls stand over: no decision's source lies in them. */
export function ownRiverUnderDecisions(board: BoardMeasure): readonly Box[] {
    return board.riverTiles.filter((tile) => tile.group === "bottom").map((tile) => tile.box);
}

/** The board's line in the page's summary: its box and content, the own tile, the decision's buttons, the least text. */
export function describeBoard(board: BoardMeasure): string {
    const fonts = Math.min(...board.fonts.map((font) => font.px));
    const scroll = `scroll ${describeSize(board.boardScroll)}`;
    const actions = board.actions.length === 0 ? "" : `, ${board.actions.length} button(s)`;
    return `board ${describeSize(board.boardClient)} ${scroll}, local tile ${describeLocalTile(board.localTileSizes)}${actions}, min text ${fonts}px`;
}

/** The boxes, in page coordinates, of the elements `selector` matches on the board, in document order. */
export function measureBoxes(page: Page, selector: string): Promise<readonly Box[]> {
    return page.evaluate((query) => {
        const board = document.querySelector(".game-board");
        return [...(board?.querySelectorAll(query) ?? [])].map((element) => {
            const rect = element.getBoundingClientRect();
            return {
                height: rect.height,
                left: rect.left + window.scrollX,
                top: rect.top + window.scrollY,
                width: rect.width,
            };
        });
    }, selector);
}
