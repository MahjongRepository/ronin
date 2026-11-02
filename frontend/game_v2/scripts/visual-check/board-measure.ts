import { type Page } from "playwright";

import { type Box, type GroupedBox, type Size, describeSize } from "./boxes.ts";

/**
 * A play switch: its box, the state it announces, and how it shows it apart from colour (its lamp a bar, wider than
 * tall, not a ring) and by its fill (the lamp's background not transparent).
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
        /** A round result's panel, which may scroll its parts in place (`checkResultPanel`); any other panel fits. */
        readonly result: boolean;
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
    /** The decision's corner and its buttons, which must sit wholly in its box, never scrolled or clipped. */
    readonly decisionCorner: { readonly box: Box; readonly buttons: readonly Box[] } | null;
    /** Text that shows whole or not at all (the status's word, a name's end, a plate's marks), clipped. */
    readonly clippedWords: readonly string[];
    /** The calls shown by their seats. */
    readonly callouts: readonly Box[];
    /** What an open offer refers to: the latest discard, a kan a chankan offer may rob. */
    /** The decision timer's slot. */
    readonly timer: Box | null;
    /** The decision's first toggle (riichi, a call's first step), pressed or not. */
    readonly toggle: Box | null;
    /** The play switches on the band. */
    readonly switches: readonly SwitchMeasure[];
    /** The table's surface and zones, which run on under the page's insets toward the screen's edges. */
    readonly zones: Box | null;
    readonly fonts: readonly { readonly name: string; readonly px: number }[];
    readonly centerTexts: readonly GroupedBox[];
    readonly nameplates: readonly Box[];
    /** Each badge by its seat's position, whose fixed place the decisions stories compare across checkpoints. */
    readonly badges: readonly GroupedBox[];
    /** The rivers' tiles by seat, and every opponent strip's tiles (hand and melds) by seat. */
    readonly riverTiles: readonly GroupedBox[];
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
        readonly hands: readonly number[];
        readonly own: number | null;
    };
    readonly center: Box | null;
    readonly opponentFaces: readonly Box[];
    /** The page's corner on the board: the settings cog, which a panel over the board may cover. */
    readonly menu: readonly Box[];
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
            grouped.push({ box: box(tile), group: area?.getAttribute("data-area") ?? "dora" });
        }
        for (const center of board.querySelectorAll(".board-center")) {
            grouped.push({ box: box(center), group: "center" });
        }
        for (const dora of board.querySelectorAll(".board-dora")) {
            grouped.push({ box: box(dora), group: "dora" });
        }
        const nameplates = [...board.querySelectorAll(".nameplate")].map((plate) => ({
            box: box(plate),
            group: plate.className.split(" ")[1] ?? "nameplate",
        }));
        grouped.push(...nameplates);
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function bySeat(within: Element, selector: string, frame: string): GroupedBox[] {
            return [...within.querySelectorAll(selector)].map((element) => ({
                box: box(element),
                group:
                    /--(?<seat>bottom|right|top|left)\b/u.exec(
                        element.closest(frame)?.className ?? "",
                    )?.groups?.seat ?? "",
            }));
        }
        const centerElement = board.querySelector(".board-center");
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
        const resultActions = [
            ...board.querySelectorAll(".board-overlay .round-end-result__confirm"),
        ].map(box);
        const actions = [...decisionActions, ...resultActions];
        const corner = board.querySelector(".board-actions");
        const timer = board.querySelector(".board-actions .decision-timer");
        const toggle = board.querySelector(
            ".board-actions .decision-controls__action[aria-pressed]",
        );
        const wholeWords = [
            ".nameplate .player-name__tail",
            ".nameplate__ai",
            ".nameplate__riichi",
        ].join(", ");
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
        const riverTile = board.querySelector<HTMLElement>(".board-river .tile");
        const ownWidths = [
            ...board.querySelectorAll<HTMLElement>(".board-local .board-area--bottom-hand .tile"),
        ].map((tile) => Number.parseFloat(getComputedStyle(tile).width));
        const tileScale = {
            hands: [
                ...board.querySelectorAll<HTMLElement>(".board-strip [data-area$='-hand'] .tile"),
            ].map((tile) => tile.offsetWidth),
            own: ownWidths.length === 0 ? null : Math.max(...ownWidths),
            river: riverTile?.offsetWidth ?? null,
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
            centerTexts,
            chrome: board.getAttribute("data-board-chrome"),
            clippedWords,
            cutNames,
            decisionCorner: corner === null ? null : { box: box(corner), buttons: decisionActions },
            fonts,
            grouped,
            handReach,
            hiddenTiles: tableTiles.filter(
                (tile) =>
                    !tile.checkVisibility({ opacityProperty: true, visibilityProperty: true }),
            ).length,
            localTileSizes: localTileElements.map((tile) => {
                const slot = tile.closest(".hand-tile");
                return slot === null ? { height: Number.NaN, width: Number.NaN } : box(slot);
            }),
            localTiles: localTileElements.map(box),
            menu,
            nameplates: nameplates.map((plate) => plate.box),
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
                          client: { height: overlay.clientHeight, width: overlay.clientWidth },
                          result: overlay.querySelector(":scope > .round-end-result") !== null,
                          scroll: { height: overlay.scrollHeight, width: overlay.scrollWidth },
                      },
            riverTiles: bySeat(board, ".board-river .tile", ".board-river"),
            stripTiles: bySeat(board, ".board-strip .tile", ".board-strip"),
            switches,
            tileScale,
            tiles: tableTiles.map(box),
            timer: timer === null ? null : box(timer),
            toggle: toggle === null ? null : box(toggle),
            zones: zones === null ? null : box(zones),
        };
    }, BOARD_TEXT);
}

/**
 * The text whose size has a floor, and the centre's pieces of text, which must not overlap one another. Each
 * nameplate is an area of its own, so it must not overlap a tile, another plate or the centre.
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
        ".nameplate__riichi",
        ".nameplate__ai",
        ".board-callout",
    ].join(", "),
} as const;

function describeLocalTile(tiles: readonly Size[]): string {
    const [tile] = tiles;
    return tile ? `${tile.width.toFixed(1)}x${tile.height.toFixed(1)}` : "none";
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
