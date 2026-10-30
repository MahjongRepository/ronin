import { readFile, readdir, rm } from "node:fs/promises";
import { type IncomingMessage, type Server, type ServerResponse, createServer } from "node:http";
import { extname, join, resolve, sep } from "node:path";
import { parseArgs } from "node:util";

import { encode } from "@msgpack/msgpack";
import {
    type Browser,
    type BrowserContext,
    type BrowserContextOptions,
    type BrowserType,
    type Page,
    chromium,
    devices,
    webkit,
} from "playwright";

/**
 * The v2 client's layout gate. It builds nothing itself: it serves the built `dist/` (the app page for every
 * `/play/` path, as the lobby does), a replay fixture under the replay API and a seat transcript over a mocked
 * game socket, then loads every storybook page, the replay and the live game at each viewport and asserts what a
 * player would see: content visible, nothing overlapping, everything inside the board and the screen, readable
 * text and tappable tiles. Any console error, failed request or missing element fails it. It writes a screenshot
 * of each page for review.
 */

const APP_ROOT = resolve(import.meta.dirname, "..");
const DIST = join(APP_ROOT, "dist");
const DEFAULT_SHOTS = resolve(APP_ROOT, "../../thoughts/screenshots/visual-check");
const ASSET_PREFIX = "/game-assets/v2/";
const REPLAY_FIXTURE = join(APP_ROOT, "src/fixtures/replays/four_kans.txt");
/** The largest engine replay fixture, which the replay load budget reads. */
const BUDGET_REPLAY_FIXTURE = join(APP_ROOT, "src/fixtures/replays/full_game.txt");
const BUDGET_GAME_ID = "load-budget";
const TRANSCRIPT_FIXTURE = join(APP_ROOT, "src/fixtures/seat-scenarios/call_prompt_seat_1.json");
/** The transcript's labels the live game is stopped at: its call prompt's buttons, and its turn after the chi. */
const LIVE_CHECKPOINTS = ["prompt", "turn"] as const;
const GAME_ID = "visual-check";

/** The smallest local hand tile a landscape table may draw on a supported phone, in CSS pixels: a tap target. */
const MIN_TAP: Size = { height: 42, width: 32 };
/** The notch phone's capture model: an iPhone 13's full display in landscape, less the insets the gate emulates. */
const NOTCH_VIEWPORT: Size = { height: 390, width: 844 };
const NOTCH_INSETS: Insets = { bottom: 21, left: 47, right: 47 };
const NOTCH_SAFE_AREA: Box = { height: 369, left: 47, top: 0, width: 750 };
/** The smallest decision button, leave button and play switch, in CSS pixels: a tap target. */
const MIN_ACTION_SIZE = 40;
/** The least room between a decision control and any tile outside the controls, so a tap meant for one never lands on the other. */
const MIN_CONTROL_TILE_GAP = 4;
/**
 * A decision story and the stories of the same decision answered and expired, whose controls and timer must stand
 * where the open one's stand: answering or running out never moves them.
 */
const CONTROL_FAMILIES: readonly string[] = ["decisions-anchor-call"];
/**
 * Pages showing a toggle off and then pressed (riichi in the band; a call's first step, then its choice of tiles, in
 * the column), whose toggle must stand in one place on a phone: pressing it never moves it.
 */
const TOGGLE_FAMILIES: readonly (readonly [string, string])[] = [
    ["decisions-anchor-riichi-off", "decisions-anchor-riichi"],
    ["decisions-kan-offer", "decisions-kan-choice"],
    ["decisions-call-prompt", "decisions-chi-choice"],
];
/** The smallest face-up tile of another seat's hand or melds in landscape, in CSS pixels: readable at a glance. */
const MIN_OPPONENT_FACE: Size = { height: 17, width: 13 };
/** The replay aside's text on a desktop: the least font size in px and the most lines each part may wrap to. */
const REPLAY_TEXT_LIMITS: Readonly<
    Record<string, { readonly px: number; readonly lines: number }>
> = {
    incomplete: { lines: 4, px: 12 },
    narration: { lines: 3, px: 13 },
    round: { lines: 2, px: 13 },
};
/** The least room between two names on a line of a result's scores, so each name and its end read as one. */
const MIN_RESULT_NAME_GAP = 12;

/** The fewest lines of the replay's narration a landscape phone's column shows without scrolling it. */
const MIN_PHONE_NARRATION_LINES = 3;
/** The smallest computed font size of the board's centre text, dora label and nameplates, in CSS pixels. */
const MIN_TEXT_PX = 10;
/** WCAG's floor for text and marks against what they are painted on (the spec's Automated checks). */
const MIN_CONTRAST = 4.5;
/**
 * The viewports the contrast check runs at: the spec's three, and the narrow desktop, whose faces are the smallest at one
 * device pixel to a CSS pixel; the other desktops paint the same colours at sizes in between.
 */
const CONTRAST_VIEWPORTS: ReadonlySet<string> = new Set([
    "phone-se-landscape",
    "phone-notch-landscape",
    "desktop-1440",
    "desktop-narrow",
]);
/**
 * The narrowest face, in device pixels, whose red strokes the contrast check fails: below it the sprite's finest red
 * strokes (a pinzu's ring) are narrower than a pixel, so no pixel shows their colour whatever the palette; they are
 * reported in the page's summary instead (the spec: reported, not redrawn). Every face on a phone is wider.
 */
const MIN_GLYPH_DEVICE_PX = 24;
/** Sub-pixel slack for comparing layout boxes. */
const EPSILON = 1;
/**
 * The least visible gap between two seats' rivers, and between a river and the centre, in CSS pixels: rivers never touch
 * each other or the centre, so each reads as its seat's block (the composition keeps 0.3 of a river tile, 6px on the
 * 667x375 floor).
 */
const MIN_RIVER_GAP = 3;
/** The least gap between an opponent's strip and any river, so neither reads as a row of the other (8px drawn). */
const MIN_STRIP_GAP = 6;
const REPLAY_MAX_STEPS = 300;
const REPLAY_LOCAL_MELDS = 2;
const SETTLE_MS = 150;
const SELECTOR_TIMEOUT_MS = 5000;
/** Pages a browser checks at once, each in its own context. */
const PAGES_AT_ONCE = 6;
/**
 * The replay load budget: reading the largest replay fixture (parse, reduce into the client timeline, steps and
 * navigation index), measured by the replay view's `replay-load` User Timing on Chromium slowed to a low-end phone's
 * CPU, the median of a few loads. Measured 2026-10-29 on a 12-core dev host: 12 ms unthrottled, 40 ms at 4x, 69 ms
 * at 6x; the budget leaves room for a slower host, not for a slower reader.
 */
const LOAD_CPU_SLOWDOWN = 6;
const LOAD_RUNS = 3;
const LOAD_BUDGET_MS = 120;
const LOAD_MEASURE = "replay-load";
/** What reading the whole fixture yields, which every timed load must report before its time counts. */
const LOAD_EXPECTED = {
    complete: true,
    damagedLine: null,
    rounds: 12,
    standings: [
        [3, 25_000],
        [0, 25_000],
        [1, 25_000],
        [2, 25_000],
    ],
    stops: 1693,
};

/** The app's one face, which every page must have loaded before it is checked and shot. */
const FONT_FAMILY = "Inter";
const FONT_EXTENSION = ".woff2";

const CONTENT_TYPES: Readonly<Record<string, string>> = {
    ".css": "text/css",
    ".html": "text/html",
    ".js": "text/javascript",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
};

/** Safe-area insets to emulate, which Playwright reports as zero: set through the theme's `--ronin-safe-*`. */
interface Insets {
    readonly left: number;
    readonly right: number;
    readonly bottom: number;
}

interface Viewport {
    readonly name: string;
    readonly engine: BrowserType;
    readonly context: BrowserContextOptions;
    readonly portrait: boolean;
    /** The live game shows its rotate panel here (an upright phone). */
    readonly rotates: boolean;
    /** A supported device size, where the tap minimum holds. */
    readonly supported: boolean;
    /** The smallest local hand tile it may draw in landscape, on a phone: a tap target. A desktop has none. */
    readonly ownTileFloor?: Size;
    /** A desktop, where the replay aside's text limits hold. */
    readonly desktop: boolean;
    readonly insets?: Insets;
    /** The viewport and safe-area box a capture model must produce, asserted on every page before its checks. */
    readonly captureModel?: { readonly viewport: Size; readonly safeArea: Box };
    /** The only pages checked here, where the viewport guards one path of the layout and the rest would only repeat. */
    readonly onlyPages?: readonly string[];
}

interface Required {
    /** Selectors that must match an element a player can see. */
    readonly visible: readonly string[];
    /** Selectors that must match an element, shown or not (the game's hidden half of its rotate split). */
    readonly attached?: readonly string[];
}

type PageKind =
    | { readonly kind: "document" }
    | {
          readonly kind: "board";
          readonly prepare?: (page: Page) => Promise<void>;
          /** The round result's panel is made shorter than its content, which must then scroll. */
          readonly panelScrolls?: boolean;
      }
    | { readonly kind: "panel"; readonly countdown: boolean }
    | { readonly kind: "game"; readonly checkpoint: (typeof LIVE_CHECKPOINTS)[number] };

type PageCase = PageKind & {
    readonly name: string;
    readonly path: string;
    readonly required: Required;
    /** The face's request is refused, so the page must stay readable in the fallback stack. */
    readonly fontBlocked?: boolean;
    /** The only viewports the page is checked at, by name; every viewport when absent. */
    readonly onlyAt?: readonly string[];
    /** Its texts, marks and faces are measured for contrast, at `CONTRAST_VIEWPORTS` (`checkContrast`). */
    readonly contrast?: boolean;
};

type BoardCase = Extract<PageCase, { readonly kind: "board" }>;

interface Box {
    readonly left: number;
    readonly top: number;
    readonly width: number;
    readonly height: number;
}

interface Size {
    readonly width: number;
    readonly height: number;
}

/** A box on the board and the area it belongs to; boxes of different areas must not intersect. */
interface GroupedBox {
    readonly group: string;
    readonly box: Box;
}

/**
 * A play switch: its box, the state it announces, and how it shows it apart from colour (the knob right of its track's
 * middle) and by its fill (the track's background not transparent).
 */
interface SwitchMeasure {
    readonly box: Box;
    readonly checked: boolean;
    readonly knobRight: boolean;
    readonly filled: boolean;
}

/** A toggle with a lamp (the riichi toggle): the state it announces and whether its lamp shows the check. */
interface LampMeasure {
    readonly pressed: boolean;
    readonly checked: boolean;
}

interface BoardMeasure {
    readonly board: Box;
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
        /** A round result's panel, which may scroll under its foot (`checkResultPanel`); any other panel fits. */
        readonly result: boolean;
    } | null;
    readonly tiles: readonly Box[];
    readonly hiddenTiles: number;
    readonly grouped: readonly GroupedBox[];
    readonly localTiles: readonly Box[];
    /** Every board tile but the local hand's and the decision buttons': rivers, other seats, melds, dora. */
    readonly otherTiles: readonly Box[];
    readonly actions: readonly Box[];
    /** The decision's corner and its buttons, which must sit wholly in its box, never scrolled or clipped. */
    readonly decisionCorner: { readonly box: Box; readonly buttons: readonly Box[] } | null;
    /** The notices over the table. */
    readonly notices: readonly Box[];
    /** The player names of a round result's scores, in the order they show. */
    readonly resultNames: readonly Box[];
    /** Text that shows whole or not at all (the status's word, a name's end, a plate's wind and marks), clipped. */
    readonly clippedWords: readonly string[];
    /** The calls shown by their seats. */
    readonly callouts: readonly Box[];
    /** What an open offer refers to: the latest discard, a kan a chankan offer may rob. */
    readonly actionSources: readonly Box[];
    /** The decision timer's slot. */
    readonly timer: Box | null;
    /** The decision's first toggle (riichi, a call's first step), pressed or not. */
    readonly toggle: Box | null;
    /** The play switches on the band. */
    readonly switches: readonly SwitchMeasure[];
    readonly lamps: readonly LampMeasure[];
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
    readonly center: Box | null;
    readonly opponentFaces: readonly Box[];
    readonly leave: Box | null;
    /** The page's corner on the board: the session's status and the way back, which no panel over the board covers. */
    readonly menu: readonly Box[];
    /** The replay's move and option buttons and round toggle beside the board, and its round list's rows over it. */
    readonly replayControls: readonly Box[];
    readonly roundList: Box | null;
    /** The replay aside's text: each part's font size and the lines it wraps to; empty on any other page. */
    readonly replayText: readonly ReplayText[];
    /** The replay's narration: its box and how many of its lines its box shows at once; null on any other page. */
    readonly narration: NarrationMeasure | null;
    readonly standings: StandingsMeasure | null;
}

/**
 * The final standings over the board: its panel, the sheet its rounds scroll in, the totals that stick to the sheet's
 * foot, its controls (its ways on and the rounds shown whole in the sheet) and its smallest text.
 */
interface StandingsMeasure {
    readonly panel: Box;
    readonly sheet: Box;
    readonly sheetScroll: Size;
    readonly sheetClient: Size;
    readonly sheetOverflowY: string;
    readonly totals: Box | null;
    readonly controls: readonly Box[];
    readonly minFontPx: number;
    /** A positive and a negative round's cell and result, where the ledger has one: the colour each shows and its tone's. */
    readonly tones: readonly ToneColour[];
}

interface ToneColour {
    readonly cell: string;
    readonly shown: string | null;
    readonly tone: string;
}

interface ReplayText {
    readonly part: string;
    readonly px: number;
    readonly lines: number;
}

interface NarrationMeasure {
    readonly box: Box;
    readonly visibleLines: number;
}

interface PageMeasure {
    readonly innerWidth: number;
    readonly innerHeight: number;
    readonly scrollWidth: number;
    readonly scrollHeight: number;
}

/** What one page's checks found: the failures, and how many checks ran so a page that checked nothing fails. */
class PageReport {
    readonly failures: string[] = [];
    checks = 0;
    summary = "";
    /** Each badge's fixed point (its seat's side of its box), where the page measured a board. */
    badgeAnchors: Readonly<Record<string, readonly [number, number]>> | null = null;
    /** The decision controls' boxes and then the timer's, where the page measured a board with a decision. */
    controlPlaces: readonly Box[] | null = null;
    /** The decision's first toggle's box, where it has one. */
    togglePlace: Box | null = null;

    expect(ok: boolean, failure: string): void {
        this.checks += 1;
        if (!ok) {
            this.failures.push(failure);
        }
    }
}

/** One page under check: the viewport it was loaded at, what its document measured, and its report. */
interface PageRun {
    readonly page: Page;
    readonly viewport: Viewport;
    readonly measure: PageMeasure;
    readonly report: PageReport;
}

/** The fixture server's origin and, for each live checkpoint, the socket frames its mocked game server sends. */
interface Fixtures {
    readonly origin: string;
    readonly frames: ReadonlyMap<string, readonly Uint8Array[]>;
}

function deviceOptions(name: string): BrowserContextOptions {
    const { defaultBrowserType: _engine, ...options } = devices[name];
    return options;
}

/**
 * The acceptance viewports: two 16:10 desktops and a 16:9 one, a short laptop's window (1366x768 less its browser's
 * chrome), where the core is bounded by the foreground band rather than its share of the height, and a narrow desktop
 * (800x600, a tablet's or a small window's), where the desktop's geometry takes the phone's chrome, each on the pages
 * that show it, the upright phone that gets the rotate panel, the notched
 * landscape phone (its insets cover the plain one), and the smallest supported landscape, which also keeps the aside's
 * scroll honest. The notched phone is the agreed capture model, not measured Safari chrome: Playwright's "iPhone 13
 * landscape" options with the viewport and screen set to the full 844x390 display after them (the device's own 750x342
 * is Safari's viewport with its chrome), then the insets, so its safe area is 750x369.
 */
const VIEWPORTS: readonly Viewport[] = [
    {
        context: { viewport: { height: 800, width: 1280 } },
        desktop: true,
        engine: chromium,
        name: "desktop",
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: { viewport: { height: 900, width: 1440 } },
        desktop: true,
        engine: chromium,
        name: "desktop-1440",
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: { viewport: { height: 1080, width: 1920 } },
        desktop: true,
        engine: chromium,
        name: "desktop-wide",
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: { viewport: { height: 657, width: 1366 } },
        desktop: true,
        engine: chromium,
        name: "desktop-short",
        onlyPages: [
            "decisions-anchor-turn",
            "decisions-anchor-call",
            "decisions-anchor-riichi",
            "board-worst",
            "board-callouts-adjacent",
            "replay",
            "game-turn",
        ],
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: { viewport: { height: 600, width: 800 } },
        desktop: true,
        engine: chromium,
        name: "desktop-narrow",
        onlyPages: [
            "decisions-anchor-turn",
            "decisions-anchor-call",
            "decisions-anchor-riichi",
            "decisions-call-prompt",
            "decisions-chi-choice",
            "decisions-kan-choice",
            "board-worst",
            "board-worst-offers",
        ],
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: deviceOptions("iPhone 13"),
        desktop: false,
        engine: webkit,
        name: "phone-portrait",
        ownTileFloor: MIN_TAP,
        portrait: true,
        rotates: true,
        supported: true,
    },
    {
        captureModel: { safeArea: NOTCH_SAFE_AREA, viewport: NOTCH_VIEWPORT },
        context: {
            ...deviceOptions("iPhone 13 landscape"),
            screen: NOTCH_VIEWPORT,
            viewport: NOTCH_VIEWPORT,
        },
        desktop: false,
        engine: webkit,
        insets: NOTCH_INSETS,
        name: "phone-notch-landscape",
        ownTileFloor: MIN_TAP,
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: deviceOptions("iPhone SE (3rd gen) landscape"),
        desktop: false,
        engine: webkit,
        name: "phone-se-landscape",
        ownTileFloor: MIN_TAP,
        portrait: false,
        rotates: false,
        supported: true,
    },
];

/** The board's tiles, but a decision control's preview faces, which a paired control may shed (the spec's Decisions). */
const BOARD_VISIBLE = [
    ".game-board .board-table .tile:not(.decision-controls__tiles .tile)",
    ".board-local .board-area--bottom-hand .tile",
    ".board-table .nameplate",
];

function boardCase(name: string, query: string, extra: readonly string[] = []): PageCase {
    return {
        kind: "board",
        name,
        path: `/play/storybook/board${query}`,
        required: { visible: [...BOARD_VISIBLE, ...extra] },
    };
}

/** A round result over the board storybook's board, one of its result stories, at a page of it. */
function resultCase(result: string, query: string, extra: readonly string[]): PageCase {
    return boardCase(
        `board-result-${result.replaceAll("_", "-")}`,
        `?overlay=round_end&result=${result}${query}`,
        [".board-overlay__panel", ...extra],
    );
}

/** A decisions story: the live board at a checkpoint of a generated seat transcript. */
function decisionCase(story: string, extra: readonly string[]): BoardCase {
    return {
        kind: "board",
        name: `decisions-${story.replaceAll("_", "-")}`,
        path: `/play/storybook/decisions?state=${story}`,
        required: { visible: [...BOARD_VISIBLE, ...extra] },
    };
}

/** A decisions story whose result panel is forced shorter than its content: the live confirm must stay in view. */
function scrollingResultCase(story: string, extra: readonly string[]): PageCase {
    return {
        ...decisionCase(story, extra),
        name: `decisions-${story.replaceAll("_", "-")}-scrolling`,
        panelScrolls: true,
        prepare: forceResultPanelShort,
    };
}

/** The forced result panel's height: under every result's content, above its foot of scores and controls. */
const FORCED_PANEL_HEIGHT = "12rem";

async function forceResultPanelShort(page: Page): Promise<void> {
    await page.addStyleTag({
        content: `.board-overlay__panel:has(> .round-end-result) { max-height: ${FORCED_PANEL_HEIGHT} !important; }`,
    });
}

const ACTION = ".board-actions .decision-controls__action";

function documentCase(name: string, path: string, content: string): PageCase {
    return { kind: "document", name, path, required: { visible: [content] } };
}

/** A replay page story: the replay view as on its route, its replay answered from a generated fixture. */
function replayCase(story: string, extra: readonly string[]): PageCase {
    return {
        kind: "board",
        name: `replay-${story.replaceAll("_", "-")}`,
        path: `/play/storybook/replay?state=${story}`,
        required: { visible: [...BOARD_VISIBLE, ".replay-controls__moves", ...extra] },
    };
}

/** A replay page story that shows no board: loading, or why the replay cannot be shown. */
function replayStateCase(story: string, content: string): PageCase {
    return documentCase(
        `replay-${story.replaceAll("_", "-")}`,
        `/play/storybook/replay?state=${story}`,
        content,
    );
}

const PAGES: readonly PageCase[] = [
    documentCase("storybook", "/play/storybook", ".storybook .tile"),
    documentCase("storybook-hand", "/play/storybook/hand", ".storybook .hand .tile"),
    documentCase("storybook-discards", "/play/storybook/discards", ".storybook .discards .tile"),
    documentCase("storybook-melds", "/play/storybook/melds", ".storybook .meld .tile"),
    boardCase("board-full-rivers", "?state=full_rivers"),
    boardCase("board-callouts-riichi", "?state=worst&callout=riichi", [".board-callout"]),
    boardCase("board-callouts-tsumo", "?state=full_rivers&callout=tsumo", [".board-callout"]),
    boardCase("board-callouts-adjacent", "?state=riichi_latest&callout=riichi&offers=five", [
        ".board-callout",
        ".discard-tile--last.discard-tile-riichi",
        ACTION,
    ]),
    {
        ...boardCase("board-worst", "?state=worst&pin=right", [
            ".board-strip .meld",
            ".board-dora .tile",
            ".board-center__seat--left .board-center__diff--right",
            ".nameplate__ai",
        ]),
        contrast: true,
    },
    boardCase("board-worst-offers", "?state=worst&offers=five", [ACTION, ".board-strip .meld"]),
    resultCase("double_ron", "&page=1", [".round-end-result__pager"]),
    { ...resultCase("sanbaiman", "", [".round-end-result__hand .meld"]), contrast: true },
    resultCase("pao", "", [".round-end-result__notes"]),
    resultCase("exhaustive", "", [".round-end-result__tenpai .tile"]),
    boardCase("board-standings", "?overlay=game_end", [
        ".standings__foot-row--leftover",
        ".standings__cell .standings__riichi",
        ".standings__cell .standings__mark--deal-in",
        ".standings__legend",
    ]),
    {
        kind: "board",
        name: "decisions-game-start",
        path: "/play/storybook/decisions?state=game_start",
        required: { visible: [".game-start__seat--viewer", ".game-start__status", ".nameplate"] },
    },
    {
        ...decisionCase("anchor_turn", [".hand-tile--selectable", ".decision-controls__countdown"]),
        contrast: true,
    },
    {
        ...decisionCase("anchor_turn", [".hand-tile--selectable", ".decision-controls__countdown"]),
        fontBlocked: true,
        name: "font-blocked-anchor-turn",
        onlyAt: ["desktop-1440", "phone-se-landscape"],
    },
    { ...decisionCase("anchor_call", [ACTION, ".decision-controls__countdown"]), contrast: true },
    {
        ...decisionCase("anchor_riichi", [
            `${ACTION}[aria-pressed="true"]`,
            ".hand-tile--disabled",
        ]),
        contrast: true,
    },
    { ...decisionCase("anchor_riichi_off", [`${ACTION}[aria-pressed="false"]`]), contrast: true },
    decisionCase("anchor_call_sent", [`${ACTION}--chosen`, ".decision-timer--sent"]),
    decisionCase("anchor_call_expired", [ACTION, ".decision-timer--time-up"]),
    decisionCase("call_prompt", [ACTION, ".decision-controls__countdown"]),
    decisionCase("chi_choice", [`${ACTION}--choice .meld-tile-sideways`, `${ACTION}--pass`]),
    decisionCase("kan_offer", [`${ACTION}[aria-pressed="false"]`, ".decision-controls__countdown"]),
    decisionCase("kan_choice", [`${ACTION}--choice .tile-back`, `${ACTION}--pass`]),
    decisionCase("ron_prompt", [ACTION, ".decision-controls__countdown"]),
    decisionCase("chankan_prompt", [ACTION, ".board-strip .meld--source"]),
    decisionCase("kuikae_turn", [".hand-tile--disabled", ".hand-tile--selectable"]),
    decisionCase("riichi_pick", [`${ACTION}[aria-pressed="true"]`, ".hand-tile--disabled"]),
    decisionCase("riichi_turn", [
        ACTION,
        ".board-furiten__word",
        ".hand-tile--selectable",
        ".decision-controls__bank",
    ]),
    {
        ...decisionCase("switches_furiten", [
            ".play-switch--on .play-switch__knob",
            ".board-furiten__word",
        ]),
        contrast: true,
        onlyAt: [
            "desktop",
            "desktop-1440",
            "desktop-wide",
            "phone-notch-landscape",
            "phone-se-landscape",
        ],
        prepare: checkSwitchKeys,
    },
    decisionCase("turn_in_bank", [".decision-controls__bank--draining", ".decision-timer--bank"]),
    decisionCase("answered", [".hand-tile--selected"]),
    decisionCase("round_end", [".round-end-result__confirm", ".round-end-result__countdown"]),
    scrollingResultCase("round_end", [
        ".round-end-result__confirm",
        ".round-end-result__countdown",
    ]),
    decisionCase("double_ron_first", [".round-end-result__pager", ".round-end-result__confirm"]),
    scrollingResultCase("double_ron_first", [
        ".round-end-result__pager",
        ".round-end-result__confirm",
        ".round-end-result__countdown",
    ]),
    decisionCase("waiting", [".round-end-result__waiting"]),
    decisionCase("reconnect_owed", [".round-end-result__confirm", ".round-end-result__countdown"]),
    decisionCase("last_result", [".round-end-result__confirm"]),
    decisionCase("standings", [
        ".standings__cell--win",
        ".standings__foot-row--result",
        ".standings__actions a[href*='seat=1']",
    ]),
    decisionCase("last_result_reopened", [".round-end-result__confirm"]),
    decisionCase("connection_lost", [
        ".board-notice--warning",
        ".game-menu__status:not(.status-connected)",
    ]),
    decisionCase("move_refused", [".board-notice--warning", ".hand-tile--selectable"]),
    decisionCase("faces_missing", [".board-notice__action", ".hand-tile--selectable"]),
    decisionCase("kicked", [".failure-panel__leave", ".game-menu__status:not(.status-connected)"]),
    decisionCase("leave_confirm", [".leave-confirm__leave", ".leave-confirm__stay"]),
    decisionCase("leave_after_win", [".leave-confirm__stay"]),
    {
        countdown: false,
        kind: "panel",
        name: "rotate-waiting",
        path: "/play/storybook/rotate?state=waiting",
        required: { visible: [".rotate-panel", ".rotate-panel .connection-status"] },
    },
    {
        countdown: false,
        kind: "panel",
        name: "rotate-leave",
        path: "/play/storybook/rotate?state=leave",
        required: { visible: [".rotate-panel", ".rotate-panel .leave-confirm__leave"] },
    },
    {
        countdown: false,
        kind: "panel",
        name: "rotate-ended",
        path: "/play/storybook/rotate?state=ended",
        required: { visible: [".rotate-panel", ".rotate-panel .failure-panel__reload"] },
    },
    {
        countdown: true,
        kind: "panel",
        name: "rotate-countdown",
        path: "/play/storybook/rotate?state=countdown",
        required: { visible: [".rotate-panel", ".rotate-panel__seconds"] },
    },
    replayCase("start", [".replay-controls__narration"]),
    replayCase("autoplay", [".replay-controls__option--play[aria-pressed='true']"]),
    replayCase("viewpoint_hidden", [".replay-controls__option--hands[aria-pressed='true']"]),
    replayCase("round_list", [".round-list__row[aria-current]"]),
    replayCase("incomplete", [".replay-controls__incomplete--end"]),
    replayCase("ends_on_result", [".round-end-result__title", ".replay-controls__incomplete--end"]),
    replayCase("damaged", [".replay-controls__incomplete--end"]),
    replayCase("double_ron", [".round-end-result__pager"]),
    replayCase("result_hidden", [
        ".round-end-result__title",
        ".replay-controls__option--hands[aria-pressed='true']",
    ]),
    replayCase("standings", [".standings__round--jump", ".standings__cell--win"]),
    replayCase("standings_long", [".standings__round--jump", ".standings__foot-row--result"]),
    replayStateCase("loading", ".replay-state"),
    replayStateCase("not_found", ".replay-state__links a"),
    {
        kind: "board",
        name: "replay",
        path: `/play/history/${GAME_ID}`,
        prepare: stepReplayToLocalMelds,
        required: { visible: [...BOARD_VISIBLE, ".board-local .meld", ".replay-controls"] },
    },
    {
        checkpoint: "prompt",
        kind: "game",
        name: "game-prompt",
        path: `/play/${GAME_ID}`,
        required: {
            attached: [
                ".game__rotate .rotate-panel__seconds",
                ".game__play .decision-controls__action",
                ".game__play .decision-controls__countdown",
            ],
            visible: [],
        },
    },
    {
        checkpoint: "turn",
        kind: "game",
        name: "game-turn",
        path: `/play/${GAME_ID}`,
        required: {
            attached: [
                ".game__rotate .rotate-panel__seconds",
                ".game__play .board-local .hand-tile--selectable",
                ".game__play .decision-controls__countdown",
            ],
            visible: [],
        },
    },
];

function contains(outer: Box, inner: Box): boolean {
    return (
        inner.left >= outer.left - EPSILON &&
        inner.top >= outer.top - EPSILON &&
        inner.left + inner.width <= outer.left + outer.width + EPSILON &&
        inner.top + inner.height <= outer.top + outer.height + EPSILON
    );
}

function intersects(first: Box, second: Box): boolean {
    return (
        first.left + EPSILON < second.left + second.width &&
        second.left + EPSILON < first.left + first.width &&
        first.top + EPSILON < second.top + second.height &&
        second.top + EPSILON < first.top + first.height
    );
}

function describeSize(size: Size): string {
    return `${Math.round(size.width)}x${Math.round(size.height)}`;
}

function describeBox(box: Box): string {
    return `${describeSize(box)}@${Math.round(box.left)},${Math.round(box.top)}`;
}

/** The step the replay's controls show within its round, as a number. */
async function replayStep(page: Page): Promise<number> {
    const text = await page.locator(".replay-controls__step").textContent();
    const step = /(?<index>\d+)[/]/u.exec(text ?? "")?.groups?.index;
    if (step === undefined) {
        throw new Error(`the replay shows no step: ${text}`);
    }
    return Number(step);
}

/**
 * Next steps exactly once for each native activation, in the browser's own event order: a click (a press that steps
 * and the click it ends in), and Enter and Space on the focused button, which the page takes as the step.
 */
async function checkStepButton(page: Page): Promise<void> {
    const next = page.locator("[data-step='next']");
    const activations: readonly [string, () => Promise<void>][] = [
        ["a click", () => next.click()],
        ["Enter", () => next.press("Enter")],
        ["Space", () => next.press(" ")],
    ];
    for (const [name, activate] of activations) {
        const before = await replayStep(page);
        await activate();
        const after = await replayStep(page);
        if (after !== before + 1) {
            throw new Error(`${name} on Next stepped from ${before} to ${after}, not once`);
        }
    }
}

async function switchChecked(page: Page, name: string): Promise<boolean> {
    return (await page.getByRole("switch", { name }).getAttribute("aria-checked")) === "true";
}

/**
 * The play switches by keyboard: Shift+Tab from the hand's first tile reaches one within a few presses (no focus moved
 * for the player), and Space and Enter on the focused Auto win each turn it once, sending nothing; it ends on, as the
 * story opened.
 */
async function checkSwitchKeys(page: Page): Promise<void> {
    await page.waitForSelector(".play-switch", { timeout: SELECTOR_TIMEOUT_MS });
    await page.locator(".board-local .hand-tile").first().focus();
    let reached = false;
    for (let press = 0; press < 4 && !reached; press += 1) {
        await page.keyboard.press("Shift+Tab");
        reached = await page.evaluate(
            () => document.activeElement?.classList.contains("play-switch") ?? false,
        );
    }
    if (!reached) {
        throw new Error("Shift+Tab from the hand never reached a play switch");
    }
    const autoWin = page.getByRole("switch", { name: "Auto win" });
    for (const [key, expected] of [
        [" ", false],
        ["Enter", true],
    ] as const) {
        await autoWin.press(key);
        if ((await switchChecked(page, "Auto win")) !== expected) {
            throw new Error(`${key === " " ? "Space" : key} on Auto win did not turn it once`);
        }
    }
    if ((await page.locator(".decisions-storybook__sent").count()) > 0) {
        throw new Error("turning a play switch sent a message");
    }
    await autoWin.blur();
}

async function stepReplayToLocalMelds(page: Page): Promise<void> {
    await page.waitForSelector(".replay-controls", { timeout: SELECTOR_TIMEOUT_MS });
    await checkStepButton(page);
    for (let step = 0; step < REPLAY_MAX_STEPS; step += 1) {
        if ((await page.locator(".board-local .meld").count()) >= REPLAY_LOCAL_MELDS) {
            return;
        }
        await page.keyboard.press("ArrowRight");
    }
    throw new Error(`the replay never showed ${REPLAY_LOCAL_MELDS} local melds`);
}

interface ReceivedEvent {
    readonly kind: "received";
    readonly label?: string;
    readonly payload: Readonly<Record<string, unknown>>;
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isReceivedEvent(event: unknown): event is ReceivedEvent {
    return isRecord(event) && event.kind === "received" && isRecord(event.payload);
}

/**
 * For each live checkpoint, the frames the server sent the transcript's seat up to the message it labels,
 * MessagePack-encoded.
 */
async function transcriptFrames(): Promise<ReadonlyMap<string, readonly Uint8Array[]>> {
    const transcript: unknown = JSON.parse(await readFile(TRANSCRIPT_FIXTURE, "utf8"));
    if (!isRecord(transcript) || !Array.isArray(transcript.events)) {
        throw new Error(`${TRANSCRIPT_FIXTURE} has no event list`);
    }
    const received = transcript.events.filter(isReceivedEvent);
    return new Map(
        LIVE_CHECKPOINTS.map((label) => {
            const last = received.findIndex((event) => event.label === label);
            if (last === -1) {
                throw new Error(`${TRANSCRIPT_FIXTURE} has no message labelled ${label}`);
            }
            return [label, received.slice(0, last + 1).map((event) => encode(event.payload))];
        }),
    );
}

function assetPath(pathname: string): string | null {
    const file = resolve(DIST, `.${pathname.slice(ASSET_PREFIX.length - 1)}`);
    return file.startsWith(DIST + sep) ? file : null;
}

async function respond(request: IncomingMessage, response: ServerResponse): Promise<void> {
    const { pathname } = new URL(request.url ?? "/", "http://visual-check");
    let file: string | null = null;
    if (pathname.startsWith(ASSET_PREFIX)) {
        file = assetPath(pathname);
    } else if (pathname === `/api/replays/${BUDGET_GAME_ID}`) {
        file = BUDGET_REPLAY_FIXTURE;
    } else if (pathname.startsWith("/api/replays/")) {
        file = REPLAY_FIXTURE;
    } else if (pathname.startsWith("/play/")) {
        file = join(DIST, "index.html");
    }
    if (file === null) {
        response.writeHead(404).end();
        return;
    }
    try {
        const body = await readFile(file);
        const type = CONTENT_TYPES[extname(file)] ?? "text/plain";
        response.writeHead(200, { "Content-Type": type }).end(body);
    } catch {
        response.writeHead(404).end();
    }
}

async function startServer(): Promise<{ server: Server; origin: string }> {
    const server = createServer((request, response) => {
        void respond(request, response);
    });
    await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
    const address = server.address();
    if (address === null || typeof address === "string") {
        throw new Error("the fixture server has no TCP port");
    }
    return { origin: `http://127.0.0.1:${address.port}`, server };
}

/**
 * A context that keeps the run offline and deterministic: reduced motion, so a shot shows each animation's resting
 * state, nothing off the origin (the app's own face is served with it), the handoff set, the socket mocked. With
 * `fontBlocked`, the face's request is answered 404.
 */
async function openContext(
    browser: Browser,
    viewport: Viewport,
    {
        fontBlocked = false,
        frames,
        origin,
    }: {
        readonly fontBlocked?: boolean;
        readonly frames: readonly Uint8Array[];
        readonly origin: string;
    },
): Promise<BrowserContext> {
    const context = await browser.newContext({ ...viewport.context, reducedMotion: "reduce" });
    await context.route(
        (url) => url.origin !== origin,
        (route) => route.fulfill({ body: "", contentType: "text/css", status: 200 }),
    );
    if (fontBlocked) {
        await context.route(
            (url) => url.pathname.endsWith(FONT_EXTENSION),
            (route) => route.fulfill({ body: "", status: 404 }),
        );
    }
    const wsUrl = `${origin.replace("http", "ws")}/ws/${GAME_ID}`;
    const handoff = JSON.stringify({ gameTicket: "visual-check", wsUrl });
    await context.addInitScript(([key, value]) => sessionStorage.setItem(key, value), [
        `game_session:${GAME_ID}`,
        handoff,
    ] as const);
    await context.routeWebSocket(wsUrl, (socket) => {
        let joined = false;
        socket.onMessage(() => {
            if (joined) {
                return;
            }
            joined = true;
            for (const frame of frames) {
                socket.send(Buffer.from(frame));
            }
        });
    });
    return context;
}

/** The page sees the capture model's viewport, and the emulated insets leave exactly its safe area. */
async function checkCaptureModel(
    page: Page,
    viewport: Viewport,
    report: PageReport,
): Promise<void> {
    const { captureModel } = viewport;
    if (captureModel === undefined) {
        return;
    }
    const seen = await page.evaluate(() => {
        const probe = document.createElement("div");
        probe.style.cssText =
            "position: fixed; top: var(--ronin-safe-top); right: var(--ronin-safe-right); bottom: var(--ronin-safe-bottom); left: var(--ronin-safe-left); pointer-events: none;";
        document.body.append(probe);
        const { height, left, top, width } = probe.getBoundingClientRect();
        probe.remove();
        return {
            safeArea: { height, left, top, width },
            viewport: { height: window.innerHeight, width: window.innerWidth },
        };
    });
    report.expect(
        seen.viewport.width === captureModel.viewport.width &&
            seen.viewport.height === captureModel.viewport.height,
        `the viewport is ${describeSize(seen.viewport)}, not the capture model's ${describeSize(captureModel.viewport)}`,
    );
    const { safeArea } = captureModel;
    report.expect(
        contains(safeArea, seen.safeArea) && contains(seen.safeArea, safeArea),
        `the safe area is ${describeBox(seen.safeArea)}, not the capture model's ${describeBox(safeArea)}`,
    );
}

async function emulateInsets(page: Page, insets: Insets | undefined): Promise<void> {
    if (insets === undefined) {
        return;
    }
    const { bottom, left, right } = insets;
    await page.addStyleTag({
        content: `:root { --ronin-safe-left: ${left}px; --ronin-safe-right: ${right}px; --ronin-safe-bottom: ${bottom}px; }`,
    });
}

function measurePage(page: Page): Promise<PageMeasure> {
    return page.evaluate(() => ({
        innerHeight: window.innerHeight,
        innerWidth: window.innerWidth,
        scrollHeight: document.documentElement.scrollHeight,
        scrollWidth: document.documentElement.scrollWidth,
    }));
}

/** Every element `selector` matches must be shown (not hidden, transparent or zero-sized), and one must match. */
function countHidden(page: Page, selector: string): Promise<{ matched: number; hidden: number }> {
    return page.evaluate((query) => {
        const elements = [...document.querySelectorAll(query)];
        const hidden = elements.filter((element) => {
            const rect = element.getBoundingClientRect();
            const shown = element.checkVisibility({
                opacityProperty: true,
                visibilityProperty: true,
            });
            return !shown || rect.width === 0 || rect.height === 0;
        });
        return { hidden: hidden.length, matched: elements.length };
    }, selector);
}

async function checkVisible(
    page: Page,
    selectors: readonly string[],
    report: PageReport,
): Promise<void> {
    for (const selector of selectors) {
        const { hidden, matched } = await countHidden(page, selector);
        report.expect(matched > 0, `nothing matches ${selector}`);
        report.expect(hidden === 0, `${hidden} of ${matched} ${selector} hidden or empty`);
    }
}

function measureBoard(page: Page): Promise<BoardMeasure> {
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
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function measureStandings(): StandingsMeasure | null {
            const panel = document.querySelector(".board-overlay__panel:has(> .standings)");
            const sheet = panel?.querySelector(".standings__sheet");
            if (panel === null || panel === undefined || sheet === null || sheet === undefined) {
                return null;
            }
            const shown = sheet.getBoundingClientRect();
            const rounds = [...sheet.querySelectorAll(".standings__round--jump")].filter((row) => {
                const { bottom, top } = row.getBoundingClientRect();
                return top >= shown.top && bottom <= shown.bottom;
            });
            const totals = sheet.querySelector("tfoot");
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function toneOf(token: string, within: Element): string {
                const probe = document.createElement("span");
                probe.style.color = `var(${token})`;
                within.append(probe);
                const { color } = getComputedStyle(probe);
                probe.remove();
                return color;
            }
            const toneCells = [
                ["round +", "tbody .standings__cell--positive", "--ronin-score-positive"],
                ["round −", "tbody .standings__cell--negative", "--ronin-score-negative"],
                [
                    "result +",
                    ".standings__foot-row--result .standings__cell--positive",
                    "--ronin-score-positive",
                ],
                [
                    "result −",
                    ".standings__foot-row--result .standings__cell--negative",
                    "--ronin-score-negative",
                ],
            ] as const;
            const tones = toneCells.map(([cell, selector, token]) => {
                const found = sheet.querySelector(selector);
                return {
                    cell,
                    shown: found === null ? null : getComputedStyle(found).color,
                    tone: toneOf(token, panel),
                };
            });
            const texts = [
                ...panel.querySelectorAll(
                    ".standings th, .standings td, .standings__action, .standings__legend-item",
                ),
            ];
            return {
                controls: [...panel.querySelectorAll(".standings__action"), ...rounds].map(box),
                minFontPx: Math.min(
                    ...texts.map((element) =>
                        Number.parseFloat(getComputedStyle(element).fontSize),
                    ),
                ),
                panel: box(panel),
                sheet: box(sheet),
                sheetClient: { height: sheet.clientHeight, width: sheet.clientWidth },
                sheetOverflowY: getComputedStyle(sheet).overflowY,
                sheetScroll: { height: sheet.scrollHeight, width: sheet.scrollWidth },
                tones,
                totals: totals === null ? null : box(totals),
            };
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
        for (const menu of board.querySelectorAll(".board-menu")) {
            grouped.push({ box: box(menu), group: "menu" });
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
            const track = element.querySelector(".play-switch__track");
            const knob = element.querySelector(".play-switch__knob");
            const trackBox = track?.getBoundingClientRect();
            const knobBox = knob?.getBoundingClientRect();
            const fill = track === null ? "" : getComputedStyle(track).backgroundColor;
            return {
                box: box(element),
                checked: element.getAttribute("aria-checked") === "true",
                filled: fill !== "" && fill !== "transparent" && fill !== "rgba(0, 0, 0, 0)",
                knobRight:
                    trackBox !== undefined &&
                    knobBox !== undefined &&
                    knobBox.left + knobBox.width / 2 > trackBox.left + trackBox.width / 2,
            };
        });
        const zones = board.querySelector(".board-zones");
        const lamps = [...board.querySelectorAll(".decision-controls__lamp")].map((lamp) => {
            const check = getComputedStyle(lamp, "::after");
            return {
                checked:
                    check.content !== "none" &&
                    check.display !== "none" &&
                    Number.parseFloat(check.width) > 0 &&
                    Number.parseFloat(check.height) > 0,
                pressed: lamp.closest("[aria-pressed]")?.getAttribute("aria-pressed") === "true",
            };
        });
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
            ".game-menu__status-word",
            ".nameplate__wind",
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
                const clips = [".nameplate__name", ".nameplate, .game-menu__status"].flatMap(
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
        const leave = board.querySelector(".game-menu__leave");
        const menu = [...board.querySelectorAll(".game-menu__status, .game-menu__leave")].map(box);
        const roundList = document.querySelector(".round-list");
        const roundRows = document.querySelector(".round-list__rows");
        const shownRows =
            roundRows === null
                ? []
                : [...roundRows.querySelectorAll(".round-list__row")].filter((row) => {
                      const shown = roundRows.getBoundingClientRect();
                      const { bottom, top } = row.getBoundingClientRect();
                      return top >= shown.top && bottom <= shown.bottom;
                  });
        const replayTextParts: Readonly<Record<string, string>> = {
            incomplete: ".replay-controls__incomplete",
            narration: ".replay-controls__narration",
            round: ".replay-controls__round",
        };
        const replayText = Object.entries(replayTextParts).flatMap(([part, selector]) => {
            const element = document.querySelector(selector);
            if (element === null || element.textContent.trim() === "") {
                return [];
            }
            const px = Number.parseFloat(getComputedStyle(element).fontSize);
            const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
            const rects: DOMRect[] = [];
            for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
                const range = document.createRange();
                range.selectNodeContents(node);
                rects.push(...[...range.getClientRects()].filter((rect) => rect.height > 0));
            }
            const tops = rects.map((rect) => rect.top).toSorted((first, second) => first - second);
            const lineGap = Math.min(...rects.map((rect) => rect.height)) / 2;
            const lines = tops.filter(
                (top, index) => index === 0 || top - tops[index - 1] > lineGap,
            );
            return [{ lines: lines.length, part, px }];
        });
        const narrationElement = document.querySelector(".replay-controls__narration");
        const narration =
            narrationElement === null
                ? null
                : {
                      box: box(narrationElement),
                      visibleLines: Math.floor(
                          (narrationElement.clientHeight + 1) /
                              Number.parseFloat(getComputedStyle(narrationElement).lineHeight),
                      ),
                  };
        const replayControls = [
            ...document.querySelectorAll(
                ".replay-controls__move, .replay-controls__option, .replay-controls__round, .round-list__close",
            ),
            ...shownRows,
        ].map(box);
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
            actionSources: [...board.querySelectorAll(".discard-tile--last, .meld--source")].map(
                box,
            ),
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
            clippedWords,
            decisionCorner: corner === null ? null : { box: box(corner), buttons: decisionActions },
            fonts,
            grouped,
            hiddenTiles: tableTiles.filter(
                (tile) =>
                    !tile.checkVisibility({ opacityProperty: true, visibilityProperty: true }),
            ).length,
            lamps,
            leave: leave === null ? null : box(leave),
            localTiles: [
                ...board.querySelectorAll(".board-local .board-area--bottom-hand .tile"),
            ].map(box),
            menu,
            nameplates: nameplates.map((plate) => plate.box),
            narration,
            notices: [...board.querySelectorAll(".board-notice")].map(box),
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
            replayControls,
            replayText,
            resultNames: [
                ...board.querySelectorAll(".board-overlay .round-end-result__score-name"),
            ].map(box),
            riverTiles: bySeat(board, ".board-river .tile", ".board-river"),
            roundList: roundList === null ? null : box(roundList),
            standings: measureStandings(),
            stripTiles: bySeat(board, ".board-strip .tile", ".board-strip"),
            switches,
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
        ".board-center__wall",
        ".board-center__riichi:not(.board-center__riichi--none)",
        ".board-center__score-line",
    ].join(", "),
    fontSelectors: [
        ".board-center__round",
        ".board-center__wall",
        ".board-dora__sticks",
        ".board-center__score-line",
        ".nameplate__name",
        ".nameplate__wind",
        ".nameplate__riichi",
        ".nameplate__ai",
        ".board-callout",
    ].join(", "),
} as const;

function viewportBox(page: Page): Promise<Box> {
    return page.evaluate(() => ({
        height: window.innerHeight,
        left: window.scrollX,
        top: window.scrollY,
        width: window.innerWidth,
    }));
}

/** Pairs of boxes from different areas that intersect, named by their areas. */
function findOverlaps(grouped: readonly GroupedBox[]): string[] {
    const overlaps = new Set<string>();
    for (const [index, first] of grouped.entries()) {
        for (const second of grouped.slice(index + 1)) {
            if (first.group !== second.group && intersects(first.box, second.box)) {
                overlaps.add([first.group, second.group].toSorted().join(" x "));
            }
        }
    }
    return [...overlaps];
}

function checkBoardContent(board: BoardMeasure, report: PageReport): void {
    const { boardClient: client, boardScroll: scroll } = board;
    report.expect(
        scroll.width <= client.width + EPSILON && scroll.height <= client.height + EPSILON,
        `board content overflows its box: scroll ${describeSize(scroll)} > client ${describeSize(client)}`,
    );
    report.expect(
        board.tiles.length > 0 && board.hiddenTiles === 0,
        `${board.hiddenTiles} hidden tile(s)`,
    );
    const outside = board.tiles.filter((tile) => !contains(board.board, tile));
    report.expect(outside.length === 0, `${outside.length} tile(s) outside the board`);
    const strayPlates = board.nameplates.filter((plate) => !contains(board.board, plate));
    report.expect(strayPlates.length === 0, `${strayPlates.length} nameplate(s) outside the board`);
    const overlaps = findOverlaps(board.grouped);
    report.expect(overlaps.length === 0, `areas overlap: ${overlaps.join(", ")}`);
    report.expect(
        board.clippedWords.length === 0,
        `text cut short: ${board.clippedWords.join(", ")}`,
    );

    const small = board.fonts.filter((font) => font.px < MIN_TEXT_PX);
    report.expect(board.fonts.length > 0, "no board text measured");
    report.expect(
        small.length === 0,
        `text under ${MIN_TEXT_PX}px: ${small.map((font) => `${font.name} ${font.px}px`).join(", ")}`,
    );
}

function checkAside(board: BoardMeasure, frame: Box, report: PageReport): void {
    const { aside } = board;
    if (aside === null) {
        return;
    }
    report.expect(!intersects(aside.box, board.board), "the aside overlaps the board");
    report.expect(
        contains(frame, aside.box),
        `the aside ${describeBox(aside.box)} leaves the page`,
    );
    const scrolls = aside.scroll.height > aside.box.height + EPSILON;
    report.expect(
        !scrolls || aside.overflowY === "auto" || aside.overflowY === "scroll",
        "the aside's controls overflow it with no way to scroll to them",
    );
}

function checkOverlay(board: BoardMeasure, viewport: Viewport, report: PageReport): void {
    const { overlay } = board;
    if (overlay === null) {
        return;
    }
    report.expect(contains(board.board, overlay.box), "the overlay panel leaves the board");
    const covered = viewport.portrait
        ? []
        : board.menu.filter((control) => intersects(control, overlay.box));
    report.expect(
        covered.length === 0,
        `the overlay panel ${describeBox(overlay.box)} covers the page's corner: ${covered.map(describeBox).join(", ")}`,
    );
    if (viewport.supported) {
        report.expect(
            overlay.scroll.width <= overlay.client.width + EPSILON &&
                (overlay.result || overlay.scroll.height <= overlay.client.height + EPSILON),
            `the overlay panel's content overflows it: ${describeSize(overlay.scroll)} > ${describeSize(overlay.client)}`,
        );
    }
}

/** What a round result's panel shows at one end of its scroll. */
interface ResultPanelView {
    readonly scrollTop: number;
    /** The panel's visible area, inside its border. */
    readonly shown: Box;
    /** The primary button and its countdown, which stay in view at either end. */
    readonly kept: readonly { readonly name: string; readonly box: Box }[];
    readonly pager: readonly Box[];
    readonly foot: Box | null;
    /** The lowest edge of the result's content above its foot. */
    readonly contentBottom: number;
}

/** A round result's panel at the start and the end of its scroll, restored to its start after. */
interface ResultPanelMeasure {
    readonly overflowY: string;
    readonly scroll: Size;
    readonly client: Size;
    readonly start: ResultPanelView;
    readonly end: ResultPanelView;
}

function measureResultPanel(page: Page): Promise<ResultPanelMeasure | null> {
    return page.evaluate(async () => {
        const panel = document.querySelector(".board-overlay__panel:has(> .round-end-result)");
        if (!(panel instanceof HTMLElement)) {
            return null;
        }
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
        function view(shownPanel: HTMLElement): ResultPanelView {
            const outer = box(shownPanel);
            const foot = shownPanel.querySelector(".round-end-result__foot");
            const content = [
                ...shownPanel.querySelectorAll(".round-end-result > :not(.round-end-result__foot)"),
            ].map(box);
            return {
                contentBottom: Math.max(...content.map((part) => part.top + part.height)),
                foot: foot === null ? null : box(foot),
                kept: [
                    ...shownPanel.querySelectorAll(
                        ".round-end-result__confirm, .round-end-result__countdown",
                    ),
                ].map((element) => ({ box: box(element), name: element.className.split(" ")[0] })),
                pager: [...shownPanel.querySelectorAll(".round-end-result__page-btn")].map(box),
                scrollTop: shownPanel.scrollTop,
                shown: {
                    height: shownPanel.clientHeight,
                    left: outer.left + shownPanel.clientLeft,
                    top: outer.top + shownPanel.clientTop,
                    width: shownPanel.clientWidth,
                },
            };
        }
        // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
        function nextFrame(): Promise<void> {
            return new Promise((done) => {
                requestAnimationFrame(() => done());
            });
        }
        panel.scrollTo({ behavior: "instant", top: 0 });
        await nextFrame();
        const start = view(panel);
        panel.scrollTo({ behavior: "instant", top: panel.scrollHeight });
        await nextFrame();
        const end = view(panel);
        panel.scrollTo({ behavior: "instant", top: 0 });
        await nextFrame();
        return {
            client: { height: panel.clientHeight, width: panel.clientWidth },
            end,
            overflowY: getComputedStyle(panel).overflowY,
            scroll: { height: panel.scrollHeight, width: panel.scrollWidth },
            start,
        };
    });
}

/**
 * A round result that does not fit its panel scrolls inside it, never clipped: its content reaches past its foot at the
 * scroll's end, and its primary button and countdown stay wholly in view at both ends, the winner pager at the start.
 * A case that forces the panel short first proves that it overflows.
 */
function checkResultPanel(
    panel: ResultPanelMeasure | null,
    mustScroll: boolean,
    report: PageReport,
): void {
    if (panel === null) {
        report.expect(!mustScroll, "no round result panel to scroll");
        return;
    }
    const overflows = panel.scroll.height > panel.client.height + EPSILON;
    report.expect(
        overflows || !mustScroll,
        `the result panel forced short still fits: ${describeSize(panel.scroll)} in ${describeSize(panel.client)}`,
    );
    const ends = [
        ["start", panel.start],
        ["end", panel.end],
    ] as const;
    for (const [end, view] of ends) {
        const hidden = view.kept.filter(({ box }) => !contains(view.shown, box));
        report.expect(
            hidden.length === 0,
            `at the scroll's ${end}, the result's ${hidden.map(({ name }) => name).join(", ")} leave(s) its panel's view`,
        );
    }
    const hiddenPager = panel.start.pager.filter((button) => !contains(panel.start.shown, button));
    report.expect(
        hiddenPager.length === 0,
        `the winner pager leaves the result panel's view: ${hiddenPager.map(describeBox).join(", ")}`,
    );
    if (!overflows) {
        return;
    }
    report.expect(
        panel.overflowY === "auto" || panel.overflowY === "scroll",
        `the result overflows its panel (${describeSize(panel.scroll)} in ${describeSize(panel.client)}) with overflow-y ${panel.overflowY}`,
    );
    report.expect(
        panel.end.scrollTop > panel.start.scrollTop + EPSILON,
        "the result overflows its panel but does not scroll",
    );
    const { contentBottom, foot, shown } = panel.end;
    const limit = Math.min(shown.top + shown.height, foot?.top ?? Infinity);
    report.expect(
        contentBottom <= limit + EPSILON,
        `at the scroll's end the result's content ends at ${contentBottom.toFixed(0)}px, under its foot or panel at ${limit.toFixed(0)}px`,
    );
}

/** The winner pager of a double ron's result moves one page: on, or back from the last page. */
async function checkWinnerPaging(page: Page, report: PageReport): Promise<void> {
    if ((await page.locator(".board-overlay .round-end-result__page-btn").count()) === 0) {
        return;
    }
    const label = page.locator(".board-overlay .round-end-result__page");
    const before = Number.parseInt((await label.textContent()) ?? "", 10);
    const next = page.locator(".board-overlay [aria-label='Next winner']");
    const forward = await next.isEnabled();
    const step = forward ? 1 : -1;
    await (forward ? next : page.locator(".board-overlay [aria-label='Previous winner']")).click();
    const moved = await page
        .waitForFunction(
            (expected) =>
                Number.parseInt(
                    document.querySelector(".board-overlay .round-end-result__page")?.textContent ??
                        "",
                    10,
                ) === expected,
            before + step,
            { timeout: SELECTOR_TIMEOUT_MS },
        )
        .then(() => true)
        .catch(() => false);
    report.expect(moved, `the winner pager did not move from page ${before} to ${before + step}`);
}

function longSide(box: Box): number {
    return Math.max(box.width, box.height);
}

/**
 * The local hand stays on the screen, at least the viewport's floor where it has one (a phone's tap target), and its
 * tiles are the board's largest: larger than any river, other seat's hand or meld, or dora tile.
 */
function checkLocalHand(
    board: BoardMeasure,
    { floor, screen }: { readonly floor: Size | undefined; readonly screen: Box },
    report: PageReport,
): void {
    const hidden = board.localTiles.filter((tile) => !contains(screen, tile));
    report.expect(hidden.length === 0, `${hidden.length} local hand tile(s) outside the viewport`);
    if (floor !== undefined) {
        const small = board.localTiles.filter(
            (tile) => tile.width < floor.width - EPSILON || tile.height < floor.height - EPSILON,
        );
        report.expect(
            small.length === 0,
            `local hand tiles under ${describeSize(floor)}: ${small.map(describeBox).join(", ")}`,
        );
    }
    const smallestOwn = Math.min(...board.localTiles.map(longSide));
    const largestOther = Math.max(0, ...board.otherTiles.map(longSide));
    report.expect(
        smallestOwn > largestOther + EPSILON,
        `a local hand tile (${smallestOwn.toFixed(1)}px) is no larger than another tile on the board (${largestOther.toFixed(1)}px)`,
    );
}

/** Another seat's face-up tiles stay readable in landscape. */
function checkOpponentFaces(board: BoardMeasure, report: PageReport): void {
    const small = board.opponentFaces.filter(
        (tile) =>
            Math.min(tile.width, tile.height) < MIN_OPPONENT_FACE.width - EPSILON ||
            longSide(tile) < MIN_OPPONENT_FACE.height - EPSILON,
    );
    report.expect(
        small.length === 0,
        `face-up tiles of other seats under ${describeSize(MIN_OPPONENT_FACE)}: ${small.slice(0, 3).map(describeBox).join(", ")}`,
    );
}

/** The page's way back sits on the board and the screen, large enough to tap. */
function checkLeave(board: BoardMeasure, screen: Box, report: PageReport): void {
    const { leave } = board;
    if (leave === null) {
        return;
    }
    report.expect(
        contains(board.board, leave) && contains(screen, leave),
        `the leave button ${describeBox(leave)} is off the board or screen`,
    );
    report.expect(
        leave.width >= MIN_ACTION_SIZE - EPSILON && leave.height >= MIN_ACTION_SIZE - EPSILON,
        `the leave button is under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${describeBox(leave)}`,
    );
}

/** The replay's controls sit on the screen, large enough to tap, and its round list on the board. */
function checkReplayControls(board: BoardMeasure, screen: Box, report: PageReport): void {
    const outside = board.replayControls.filter((control) => !contains(screen, control));
    report.expect(outside.length === 0, `${outside.length} replay control(s) off the screen`);
    const small = board.replayControls.filter(
        (control) =>
            control.width < MIN_ACTION_SIZE - EPSILON || control.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `replay controls under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
    if (board.roundList !== null) {
        report.expect(
            contains(board.board, board.roundList),
            `the round list ${describeBox(board.roundList)} leaves the board`,
        );
    }
}

/**
 * The final standings fit their panel: the rounds scroll inside the sheet rather than past the board, and in landscape
 * never sideways (an upright page may scroll), the totals stay in view at the sheet's foot, no text is under the
 * floor, and on a supported landscape screen every control (its ways on, the rounds shown) is on the screen and large
 * enough to tap.
 */
function checkStandings(
    board: BoardMeasure,
    { screen, viewport }: { readonly screen: Box; readonly viewport: Viewport },
    report: PageReport,
): void {
    const { standings } = board;
    if (standings === null) {
        return;
    }
    const scrolls = standings.sheetScroll.height > standings.sheetClient.height + EPSILON;
    report.expect(
        !scrolls || standings.sheetOverflowY === "auto" || standings.sheetOverflowY === "scroll",
        "the standings' rounds overflow their sheet with no way to scroll to them",
    );
    report.expect(
        viewport.portrait || standings.sheetScroll.width <= standings.sheetClient.width + EPSILON,
        `the standings' sheet scrolls sideways: ${describeSize(standings.sheetScroll)} > ${describeSize(standings.sheetClient)}`,
    );
    report.expect(
        contains(standings.panel, standings.sheet),
        `the standings' sheet ${describeBox(standings.sheet)} leaves its panel`,
    );
    report.expect(
        standings.totals !== null && contains(standings.sheet, standings.totals),
        "the standings' totals are not in view at the sheet's foot",
    );
    const toned = standings.tones.filter(({ shown }) => shown !== null);
    const offTone = toned.filter(({ shown, tone }) => shown !== tone);
    report.expect(
        toned.length > 0 && offTone.length === 0,
        `standings cells not in their tone: ${offTone.map(({ cell, shown, tone }) => `${cell} ${shown} for ${tone}`).join(", ") || "none to check"}`,
    );
    report.expect(
        standings.minFontPx >= MIN_TEXT_PX,
        `standings text at ${standings.minFontPx}px, under ${MIN_TEXT_PX}px`,
    );
    if (!viewport.supported || viewport.portrait) {
        return;
    }
    const outside = standings.controls.filter(
        (control) => !contains(screen, control) || !contains(standings.panel, control),
    );
    report.expect(
        outside.length === 0,
        `${outside.length} standings control(s) off the panel or screen`,
    );
    const small = standings.controls.filter(
        (control) =>
            control.width < MIN_ACTION_SIZE - EPSILON || control.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `standings controls under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
}

/** On a desktop the replay's aside reads at a glance: its narration and round, and its incompleteness label. */
function checkReplayText(board: BoardMeasure, report: PageReport): void {
    for (const { lines, part, px } of board.replayText) {
        const limit = REPLAY_TEXT_LIMITS[part];
        report.expect(
            px >= limit.px && lines <= limit.lines,
            `the replay's ${part} at ${px}px on ${lines} line(s), past ${limit.px}px on ${limit.lines}`,
        );
    }
}

/**
 * On a landscape phone the replay's column keeps room for its narration, at least three lines in view at once
 * whatever else the column holds, and the narration wholly on the screen and inside the column.
 */
function checkPhoneNarration(board: BoardMeasure, screen: Box, report: PageReport): void {
    const { aside, narration } = board;
    if (narration === null || aside === null) {
        return;
    }
    report.expect(
        narration.visibleLines >= MIN_PHONE_NARRATION_LINES,
        `the replay's narration shows ${narration.visibleLines} line(s) at once, under ${MIN_PHONE_NARRATION_LINES}`,
    );
    report.expect(
        contains(screen, narration.box) && contains(aside.box, narration.box),
        `the replay's narration ${describeBox(narration.box)} leaves the screen or its column`,
    );
}

/**
 * A notice over the table never hides a tile, a nameplate, the decision's corner or the panel over the board, however
 * long it stays.
 */
function checkNotices(board: BoardMeasure, report: PageReport): void {
    const covered = [
        ...board.tiles,
        ...board.nameplates,
        ...(board.decisionCorner?.buttons ?? []),
        ...(board.overlay === null ? [] : [board.overlay.box]),
    ];
    const over = board.notices.filter((notice) => covered.some((box) => intersects(notice, box)));
    report.expect(
        over.length === 0,
        `notice(s) over a tile, plate, decision button or panel: ${over.map(describeBox).join(", ")}`,
    );
    const outside = board.notices.filter((notice) => !contains(board.board, notice));
    report.expect(outside.length === 0, `${outside.length} notice(s) off the board`);
}

/** Whether two boxes come within `gap` of each other. */
function near(first: Box, second: Box, gap: number): boolean {
    return (
        first.left < second.left + second.width + gap &&
        second.left < first.left + first.width + gap &&
        first.top < second.top + second.height + gap &&
        second.top < first.top + first.height + gap
    );
}

/**
 * The rivers keep their pinwheel's gaps: no river's tile comes within a few pixels of another seat's river or of the
 * centre, so a dense board still reads as four blocks, never one pile (look spec, Rivers).
 */
function checkRiverGaps(board: BoardMeasure, report: PageReport): void {
    const touching = new Set<string>();
    for (const [index, first] of board.riverTiles.entries()) {
        for (const second of board.riverTiles.slice(index + 1)) {
            if (first.group !== second.group && near(first.box, second.box, MIN_RIVER_GAP)) {
                touching.add([first.group, second.group].toSorted().join(" x "));
            }
        }
        if (board.center !== null && near(first.box, board.center, MIN_RIVER_GAP)) {
            touching.add(`${first.group} x center`);
        }
    }
    report.expect(
        touching.size === 0,
        `rivers within ${MIN_RIVER_GAP}px of each other or the centre: ${[...touching].join(", ")}`,
    );
}

/** An opponent's strip stands apart from the rivers, so its backs or faces never read as a river's row (look spec). */
function checkStripsApart(board: BoardMeasure, report: PageReport): void {
    const adjacent = new Set<string>();
    for (const strip of board.stripTiles) {
        for (const river of board.riverTiles) {
            if (near(strip.box, river.box, MIN_STRIP_GAP)) {
                adjacent.add(`${strip.group} strip x ${river.group} river`);
            }
        }
    }
    report.expect(
        adjacent.size === 0,
        `strips within ${MIN_STRIP_GAP}px of a river: ${[...adjacent].join(", ")}`,
    );
}

/** Each badge's fixed point: the side of its box toward its seat's edge, and its top (the own badge's foot). */
function badgeAnchors(board: BoardMeasure): Readonly<Record<string, readonly [number, number]>> {
    return Object.fromEntries(
        board.badges.map(({ box, group }) => {
            const right = box.left + box.width;
            const bottom = box.top + box.height;
            const point: readonly [number, number] =
                group === "right"
                    ? [right, box.top]
                    : [box.left, group === "bottom" ? bottom : box.top];
            return [group, point];
        }),
    );
}

/** Each name in a result's scores reads as one, standing clear of the next name on its line. */
function checkResultNames(board: BoardMeasure, report: PageReport): void {
    const crowded = board.resultNames.flatMap((name, index) => {
        const next = board.resultNames[index + 1];
        const sameLine = next !== undefined && Math.abs(next.top - name.top) < name.height / 2;
        const gap = sameLine ? next.left - (name.left + name.width) : Infinity;
        return gap < MIN_RESULT_NAME_GAP ? [`${describeBox(name)} ${gap.toFixed(1)}px`] : [];
    });
    report.expect(
        crowded.length === 0,
        `result name(s) under ${MIN_RESULT_NAME_GAP}px from the next: ${crowded.join(", ")}`,
    );
}

/**
 * A call shown by its seat stays on the board and never lies over the local hand's tiles, which take the taps, over a
 * decision control or the timer, or over what an open offer refers to (the latest discard, a kan a chankan may rob).
 */
function checkCallouts(board: BoardMeasure, report: PageReport): void {
    const outside = board.callouts.filter((callout) => !contains(board.board, callout));
    report.expect(outside.length === 0, `${outside.length} call(s) off the board`);
    const overHand = board.callouts.filter((callout) =>
        board.localTiles.some((tile) => intersects(callout, tile)),
    );
    report.expect(
        overHand.length === 0,
        `call(s) over the local hand: ${overHand.map(describeBox).join(", ")}`,
    );
    const controls = [
        ...(board.decisionCorner?.buttons ?? []),
        ...(board.timer ? [board.timer] : []),
    ];
    const overControl = board.callouts.filter((callout) =>
        controls.some((control) => intersects(callout, control)),
    );
    report.expect(
        overControl.length === 0,
        `call(s) over a decision control or the timer: ${overControl.map(describeBox).join(", ")}`,
    );
    const overSource = board.callouts.filter((callout) =>
        board.actionSources.some((source) => intersects(callout, source)),
    );
    report.expect(
        overSource.length === 0,
        `call(s) over the latest discard or an offered kan: ${overSource.map(describeBox).join(", ")}`,
    );
}

function grown(target: Box, by: number): Box {
    return {
        height: target.height + 2 * by,
        left: target.left - by,
        top: target.top - by,
        width: target.width + 2 * by,
    };
}

/**
 * Decision buttons and a round result's confirm sit wholly on the board and the screen, large enough to tap, and every
 * decision button wholly inside its corner, never scrolled or clipped out of it.
 */
function checkActions(board: BoardMeasure, screen: Box, report: PageReport): void {
    const { decisionCorner } = board;
    if (decisionCorner !== null) {
        const cut = decisionCorner.buttons.filter(
            (button) => !contains(decisionCorner.box, button),
        );
        report.expect(
            cut.length === 0,
            `decision button(s) outside their corner ${describeBox(decisionCorner.box)}: ${cut.map(describeBox).join(", ")}`,
        );
    }
    const outside = [...board.actions, ...(board.timer ? [board.timer] : [])].filter(
        (action) => !contains(board.board, action) || !contains(screen, action),
    );
    report.expect(
        outside.length === 0,
        `${outside.length} decision button(s) or the timer off the board or screen`,
    );
    const small = board.actions.filter(
        (action) =>
            action.width < MIN_ACTION_SIZE - EPSILON || action.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `decision buttons under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
    const buttons = decisionCorner?.buttons ?? [];
    const overlapping = buttons.filter((button, index) =>
        buttons.some((other, otherIndex) => otherIndex !== index && intersects(button, other)),
    );
    report.expect(
        overlapping.length === 0,
        `decision buttons over each other: ${overlapping.map(describeBox).join(", ")}`,
    );
    const { timer } = board;
    const overTimer = timer === null ? [] : buttons.filter((button) => intersects(button, timer));
    report.expect(
        overTimer.length === 0,
        `decision button(s) over the timer: ${overTimer.map(describeBox).join(", ")}`,
    );
    const tiles = [...board.otherTiles, ...board.localTiles];
    const crowded = (decisionCorner?.buttons ?? []).filter((button) =>
        tiles.some((tile) => intersects(grown(button, MIN_CONTROL_TILE_GAP), tile)),
    );
    report.expect(
        crowded.length === 0,
        `decision button(s) within ${MIN_CONTROL_TILE_GAP}px of a tile: ${crowded.map(describeBox).join(", ")}`,
    );
}

/**
 * The play switches sit wholly on the board and the screen, each large enough to tap, clear of every tile by the gap
 * a decision control keeps and off every decision control and the timer, and each shows the state it announces apart
 * from colour (its knob's side) and by its fill.
 */
function checkSwitches(board: BoardMeasure, screen: Box, report: PageReport): void {
    const { switches } = board;
    if (switches.length === 0) {
        return;
    }
    const boxes = switches.map((control) => control.box);
    const outside = boxes.filter((box) => !contains(board.board, box) || !contains(screen, box));
    report.expect(
        outside.length === 0,
        `${outside.length} play switch(es) off the board or screen`,
    );
    const small = boxes.filter(
        (box) => box.width < MIN_ACTION_SIZE - EPSILON || box.height < MIN_ACTION_SIZE - EPSILON,
    );
    report.expect(
        small.length === 0,
        `play switches under ${MIN_ACTION_SIZE}x${MIN_ACTION_SIZE}: ${small.map(describeBox).join(", ")}`,
    );
    const tiles = [...board.otherTiles, ...board.localTiles];
    const controls = [...board.actions, ...(board.timer ? [board.timer] : [])];
    const crowded = boxes.filter(
        (box) =>
            tiles.some((tile) => intersects(grown(box, MIN_CONTROL_TILE_GAP), tile)) ||
            controls.some((control) => intersects(box, control)),
    );
    report.expect(
        crowded.length === 0,
        `play switch(es) within ${MIN_CONTROL_TILE_GAP}px of a tile or over a decision control: ${crowded.map(describeBox).join(", ")}`,
    );
    const misread = switches.filter(
        (control) => control.knobRight !== control.checked || control.filled !== control.checked,
    );
    report.expect(
        misread.length === 0,
        `play switch(es) whose knob or fill does not show their state: ${misread.map((control) => describeBox(control.box)).join(", ")}`,
    );
}

/**
 * A mark the contrast check measures: the elements it is drawn on (`selector`), how far past their boxes it reaches
 * (an outline, a notch), and the CSS that hides it alone, each a selector suffix (a pseudo-element, a descendant, or
 * "") and its declarations. Each piece of information is a mark of its own (a stick's body apart from its dots), so
 * one never lends another its pixels. An `absent` mark must paint nothing (a toggle's check while it is off).
 */
interface ContrastMark {
    readonly name: string;
    readonly selector: string;
    readonly reach: number;
    readonly hide: readonly (readonly [suffix: string, declarations: string])[];
    readonly absent?: boolean;
}

const HIDDEN = "visibility: hidden !important";
const SHOWN = "visibility: visible !important";
const NO_OUTLINE = "outline-color: transparent !important";
const STICK_DOTS = " :is(.board-stick-icon__dot, .board-stick-icon__honba)";

/** The marks on the board that carry information, each measured against what it is painted on. */
const CONTRAST_MARKS: readonly ContrastMark[] = [
    {
        hide: [
            ["", NO_OUTLINE],
            ["::after", HIDDEN],
        ],
        name: "latest discard's ring and notch",
        reach: 12,
        selector: ".discard-tile--last",
    },
    { hide: [["", NO_OUTLINE]], name: "offered kan's ring", reach: 4, selector: ".meld--source" },
    {
        hide: [["::after", HIDDEN]],
        name: "turn bar",
        reach: 0,
        selector: ".board-center__seat--current",
    },
    {
        hide: [
            ["", HIDDEN],
            ["::after", SHOWN],
        ],
        name: "centre's riichi stick",
        reach: 1,
        selector: ".board-center__riichi:not(.board-center__riichi--none)",
    },
    {
        hide: [["::after", HIDDEN]],
        name: "centre's riichi stick's dot",
        reach: 0,
        selector: ".board-center__riichi:not(.board-center__riichi--none)",
    },
    {
        hide: [["", "box-shadow: none !important"]],
        name: "badge's turn underline",
        reach: 0,
        selector: ".nameplate--current .nameplate__pill",
    },
    {
        hide: [["", NO_OUTLINE]],
        name: "pinned badge's ring",
        reach: 4,
        selector: ".nameplate[aria-pressed='true'] .nameplate__pill",
    },
    {
        hide: [[" .board-stick-icon__body", HIDDEN]],
        name: "stick icon's body",
        reach: 1,
        selector: ".board-stick-icon",
    },
    {
        hide: [[STICK_DOTS, HIDDEN]],
        name: "stick icon's dots",
        reach: 0,
        selector: ".board-stick-icon",
    },
    { hide: [["", HIDDEN]], name: "furiten dot", reach: 0, selector: ".board-furiten__dot" },
    {
        hide: [
            ["", HIDDEN],
            [" .play-switch__knob", SHOWN],
        ],
        name: "switch track",
        reach: 0,
        selector: ".play-switch__track",
    },
    { hide: [["", HIDDEN]], name: "switch knob", reach: 0, selector: ".play-switch__knob" },
    {
        hide: [
            ["", "border-color: transparent !important"],
            ["::after", "border-color: currentcolor !important"],
        ],
        name: "toggle lamp's box",
        reach: 0,
        selector: ".decision-controls__lamp",
    },
    {
        hide: [["::after", HIDDEN]],
        name: "pressed toggle's check",
        reach: 0,
        selector: "[aria-pressed='true'] > .decision-controls__lamp",
    },
    {
        absent: true,
        hide: [["::after", HIDDEN]],
        name: "unpressed toggle's check",
        reach: 0,
        selector: "[aria-pressed='false'] > .decision-controls__lamp",
    },
    {
        hide: [["::after", HIDDEN]],
        name: "answered control's check",
        reach: 0,
        selector: ".decision-controls__action--chosen",
    },
    {
        hide: [["", NO_OUTLINE]],
        name: "declaring or selected tile's outline",
        reach: 4,
        selector: ":is(.hand-tile--declaring, .hand-tile--selected) .tile",
    },
    {
        hide: [["", NO_OUTLINE]],
        name: "held-back tile's rim",
        reach: 0,
        selector: ".hand-tile--disabled .tile",
    },
    {
        hide: [["::before", HIDDEN]],
        name: "connection dot",
        reach: 0,
        selector: ".game-menu__status",
    },
];

/** The paints the tile artwork authors as highlights (white sheen on a pinzu, a souzu), never inks a glyph is read by. */
const SPRITE_HIGHLIGHTS: readonly string[] = ["#fff", "#ffffff", "white"];

/** Hides every text's fill (a pseudo-element's too, which inherits it) and every face's glyph, nothing else. */
const HIDE_INK = `
    * { -webkit-text-fill-color: transparent !important; text-shadow: none !important;
        text-decoration-color: transparent !important; }
    .tile svg use { visibility: hidden !important; }
`;

/**
 * Paints every element's own text in one loud colour (`FORCE_INK`) or every pseudo-element's (`FORCE_PSEUDO_INK`), the
 * rest of the ink hidden: against the inkless shot, where each text's glyphs lie, whatever its own colour.
 */
const FORCE_INK = `
    * { -webkit-text-fill-color: #f0f !important; text-shadow: none !important;
        text-decoration-color: transparent !important; }
    *::before, *::after { -webkit-text-fill-color: transparent !important; }
    .tile svg use { visibility: hidden !important; }
`;
const FORCE_PSEUDO_INK = `
    * { -webkit-text-fill-color: transparent !important; text-shadow: none !important;
        text-decoration-color: transparent !important; }
    *::before, *::after { -webkit-text-fill-color: #f0f !important; }
    .tile svg use { visibility: hidden !important; }
`;

/** Hides the text a pseudo-element draws (" han", "✓"), nothing else. */
const HIDE_PSEUDO_TEXT = `
    *::before, *::after { -webkit-text-fill-color: transparent !important; text-shadow: none !important; }
`;

type ContrastKind = "glyph" | "mark" | "text";

type Rgb = readonly [number, number, number];

/** A colour as painted: its RGB and how much of it covers what lies beneath (its alpha times every opacity above it). */
interface PaintedColour {
    readonly rgb: Rgb;
    readonly alpha: number;
}

/** One ink of a face's sprite symbol: its colour (with the symbol's opacities) and where it comes from. */
interface GlyphInk extends PaintedColour {
    readonly name: string;
}

/**
 * A text (an element's own text nodes, or the text its pseudo-elements draw), a face's glyph or a mark, by the part of
 * its box (in viewport pixels) the page shows. A text names its painted colour and the shot that hides it alone
 * (`hiddenIn`); a glyph its symbol's inks and whether its face is under `MIN_GLYPH_DEVICE_PX` (`small`); a mark whether
 * it must paint nothing (`absent`).
 */
interface ContrastTarget {
    readonly label: string;
    readonly box: Box;
    readonly kind: ContrastKind;
    readonly colour?: PaintedColour;
    readonly hiddenIn?: "ink" | "pseudo";
    readonly inks?: readonly GlyphInk[];
    readonly small?: boolean;
    readonly absent?: boolean;
}

interface ContrastTargets {
    readonly texts: readonly ContrastTarget[];
    readonly glyphs: readonly ContrastTarget[];
    /** The marks in batches whose boxes never meet, so each batch hides at once and no mark lends another its pixels. */
    readonly marks: readonly (readonly ContrastTarget[])[];
    /** Targets the check cannot read honestly: a face whose symbol names no ink, anything under a CSS filter. */
    readonly unreadable: readonly string[];
}

/** A target under the floor: the colour measured, what it was measured against, and the ratio. */
interface ContrastFinding {
    readonly label: string;
    readonly ratio: number;
    readonly ink: string;
    readonly ground: string;
}

interface ContrastResult {
    readonly failures: readonly ContrastFinding[];
    /** A small face's strokes under the floor as drawn, its inks' colours passing: reported, never called a pass. */
    readonly reported: readonly ContrastFinding[];
    /** Targets whose ink did not show, or whose expected ink was missing, or an absent mark that painted, by label. */
    readonly missing: readonly string[];
    readonly collected: Readonly<Record<ContrastKind, number>>;
    readonly lowest: Readonly<Record<ContrastKind, number>>;
}

/**
 * Collect what the contrast check measures: the board's texts, its face-up tiles and its marks, inside the panel alone
 * while one covers the board (whatever lies under its dimming is not read), each by the part of it the viewport and
 * every clipping box above it show. Each mark element is tagged with its rule's batch (`data-contrast-<rule>`) for the
 * CSS that hides it.
 */
function collectContrastTargets(page: Page): Promise<ContrastTargets> {
    return page.evaluate(
        ({ highlights, least, marks }) => {
            const HIGHLIGHTS = new Set(highlights);
            const unreadable: string[] = [];
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function clipOf(rect: DOMRect | Box, element: Element): Box | null {
                let left = Math.max(0, rect.left);
                let top = Math.max(0, rect.top);
                let right = Math.min(window.innerWidth, rect.left + rect.width);
                let bottom = Math.min(window.innerHeight, rect.top + rect.height);
                for (
                    let above = element.parentElement;
                    above !== null;
                    above = above.parentElement
                ) {
                    const style = getComputedStyle(above);
                    if (style.overflowX !== "visible" || style.overflowY !== "visible") {
                        const outer = above.getBoundingClientRect();
                        left = Math.max(left, outer.left);
                        top = Math.max(top, outer.top);
                        right = Math.min(right, outer.right);
                        bottom = Math.min(bottom, outer.bottom);
                    }
                }
                return right - left >= 2 && bottom - top >= 2
                    ? { height: bottom - top, left, top, width: right - left }
                    : null;
            }
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function shown(element: Element): boolean {
                const rect = element.getBoundingClientRect();
                return (
                    rect.width >= 2 &&
                    rect.height >= 2 &&
                    element.checkVisibility({ opacityProperty: true, visibilityProperty: true })
                );
            }
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function meets(first: Box, second: Box): boolean {
                return (
                    first.left < second.left + second.width &&
                    second.left < first.left + first.width &&
                    first.top < second.top + second.height &&
                    second.top < first.top + first.height
                );
            }
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function named(element: Element): string {
                return element.className.toString().split(" ")[0] || element.tagName.toLowerCase();
            }
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function parsed(colour: string): PaintedColour | null {
                const parts =
                    /rgba?\((?<red>[\d.]+),? (?<green>[\d.]+),? (?<blue>[\d.]+)(?:,? \/? ?(?<alpha>[\d.]+))?\)/u.exec(
                        colour,
                    )?.groups;
                return parts === undefined
                    ? null
                    : {
                          alpha: parts.alpha === undefined ? 1 : Number(parts.alpha),
                          rgb: [Number(parts.red), Number(parts.green), Number(parts.blue)],
                      };
            }
            /** The opacity every element from `element` up to `until` (exclusive) applies, or null under a filter. */
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function opacityOf(element: Element, until: Element | null): number | null {
                let opacity = 1;
                for (
                    let at: Element | null = element;
                    at !== null && at !== until;
                    at = at.parentElement
                ) {
                    const style = getComputedStyle(at);
                    if (style.filter !== "none" || style.mixBlendMode !== "normal") {
                        return null;
                    }
                    opacity *= Number(style.opacity);
                }
                return opacity;
            }
            function textColour(
                element: Element,
                which: string | null,
                label: string,
            ): PaintedColour | null {
                const style = getComputedStyle(element, which);
                const colour = parsed(style.webkitTextFillColor || style.color);
                const opacity = opacityOf(element, null);
                if (colour === null || opacity === null) {
                    unreadable.push(label);
                    return null;
                }
                return { alpha: colour.alpha * opacity, rgb: colour.rgb };
            }
            const board = document.querySelector(".game-board");
            const scope = board?.querySelector(".board-overlay__panel") ?? board;
            if (scope === null || scope === undefined) {
                return { glyphs: [], marks: [], texts: [], unreadable };
            }
            const elements = [...scope.querySelectorAll("*")].filter(
                (element) => element.closest(".tile, svg") === null && shown(element),
            );
            const ownTexts: ContrastTarget[] = elements.flatMap((element) =>
                [...element.childNodes]
                    .filter(
                        (node) =>
                            node.nodeType === Node.TEXT_NODE &&
                            (node.textContent ?? "").trim() !== "",
                    )
                    .flatMap((node) => {
                        const range = document.createRange();
                        range.selectNode(node);
                        const box = clipOf(range.getBoundingClientRect(), element);
                        const label = `text ${named(element)} "${(node.textContent ?? "").trim().slice(0, 24)}"`;
                        const colour = box === null ? null : textColour(element, null, label);
                        return box === null || colour === null
                            ? []
                            : [
                                  {
                                      box,
                                      colour,
                                      hiddenIn: "ink" as const,
                                      kind: "text" as const,
                                      label,
                                  },
                              ];
                    }),
            );
            const pseudoTexts: ContrastTarget[] = elements.flatMap((element) =>
                (["::before", "::after"] as const).flatMap((which) => {
                    const { content } = getComputedStyle(element, which);
                    const box = clipOf(element.getBoundingClientRect(), element);
                    const label = `text ${named(element)}${which} ${content}`;
                    const colour =
                        /^".*\S.*"$/u.test(content) && box !== null
                            ? textColour(element, which, label)
                            : null;
                    return box === null || colour === null
                        ? []
                        : [
                              {
                                  box,
                                  colour,
                                  hiddenIn: "pseudo" as const,
                                  kind: "text" as const,
                                  label,
                              },
                          ];
                }),
            );
            const texts = [...ownTexts, ...pseudoTexts];
            /** The paint the artwork itself names for a node (its own attribute or the nearest in the symbol above it). */
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function authored(node: Element, attribute: string, symbol: Element): string | null {
                for (let at: Element | null = node; at !== null; at = at.parentElement) {
                    const value = at.getAttribute(attribute);
                    if (value !== null || at === symbol) {
                        return value;
                    }
                }
                return null;
            }
            /**
             * A symbol's inks: each fill and stroke, with the symbol's own opacities and the rendered instance's
             * (`instance`), but the artwork's own highlights: a paint the sprite authors white and that still paints white.
             * A paint is never dropped for being pale, so a real ink turned pale stays expected and fails.
             */
            function inksOf(symbol: Element, instance: number): GlyphInk[] {
                const inks = new Map<string, GlyphInk>();
                const shapes = symbol.querySelectorAll(
                    ":is(path, circle, ellipse, rect, polygon, polyline, line, text):not(:is(mask, clipPath, pattern) *)",
                );
                for (const node of shapes) {
                    const style = getComputedStyle(node);
                    const opacity = opacityOf(node, symbol);
                    for (const [paint, share, attribute] of [
                        [style.fill, style.fillOpacity, "fill"],
                        [style.stroke, style.strokeOpacity, "stroke"],
                    ] as const) {
                        const colour = parsed(paint);
                        const highlight =
                            HIGHLIGHTS.has(
                                (authored(node, attribute, symbol) ?? "").toLowerCase(),
                            ) && colour?.rgb.every((channel) => channel === 255) === true;
                        const ink =
                            colour === null || opacity === null || highlight
                                ? null
                                : {
                                      alpha: colour.alpha * Number(share) * opacity * instance,
                                      rgb: colour.rgb,
                                  };
                        if (ink !== null) {
                            inks.set(`${ink.rgb.join(",")}@${ink.alpha}`, {
                                ...ink,
                                name: `rgb(${ink.rgb.join(", ")})${ink.alpha < 1 ? ` at ${ink.alpha}` : ""}`,
                            });
                        }
                    }
                }
                return [...inks.values()];
            }
            const glyphs: ContrastTarget[] = [...scope.querySelectorAll(".tile:not(.tile-back)")]
                .filter((tile) => tile.querySelector("use") !== null && shown(tile))
                .flatMap((tile) => {
                    const use = tile.querySelector("use");
                    const href = use?.getAttribute("href") ?? "";
                    const symbol = document.querySelector(href);
                    const instance = use === null ? null : opacityOf(use, null);
                    const inks =
                        symbol === null || instance === null ? [] : inksOf(symbol, instance);
                    const rect = tile.getBoundingClientRect();
                    const box = clipOf(rect, tile);
                    const label = `glyph ${href.replace("#tile-", "")} in ${named(tile.parentElement ?? tile)}`;
                    if (inks.length === 0) {
                        unreadable.push(`${label} (no ink, or under a filter)`);
                        return [];
                    }
                    return box === null
                        ? []
                        : [
                              {
                                  box,
                                  inks,
                                  kind: "glyph" as const,
                                  label,
                                  small:
                                      Math.min(rect.width, rect.height) * window.devicePixelRatio <
                                      least,
                              },
                          ];
                });
            const batches: ContrastTarget[][] = [];
            for (const [rule, mark] of marks.entries()) {
                for (const element of [...scope.querySelectorAll(mark.selector)].filter(shown)) {
                    const rect = element.getBoundingClientRect();
                    const box = clipOf(
                        {
                            height: rect.height + 2 * mark.reach,
                            left: rect.left - mark.reach,
                            top: rect.top - mark.reach,
                            width: rect.width + 2 * mark.reach,
                        },
                        element,
                    );
                    if (box !== null) {
                        const target = {
                            absent: mark.absent === true,
                            box,
                            kind: "mark" as const,
                            label: `mark ${mark.name}`,
                        };
                        let batch = batches.findIndex((placed) =>
                            placed.every((other) => !meets(other.box, target.box)),
                        );
                        if (batch === -1) {
                            batch = batches.push([]) - 1;
                        }
                        batches[batch].push(target);
                        element.setAttribute(`data-contrast-${rule}`, String(batch));
                    }
                }
            }
            return { glyphs, marks: batches, texts, unreadable };
        },
        { highlights: SPRITE_HIGHLIGHTS, least: MIN_GLYPH_DEVICE_PX, marks: CONTRAST_MARKS },
    );
}

/** The CSS that hides the marks of one batch. */
function hideMarksCss(batch: number): string {
    return CONTRAST_MARKS.flatMap((mark, rule) =>
        mark.hide.map(
            ([suffix, declarations]) =>
                `${mark.selector}[data-contrast-${rule}="${batch}"]${suffix} { ${declarations}; }`,
        ),
    ).join("\n");
}

/** The viewport's pixels with `css` applied (none when null), as base64 PNG, once the page has drawn it. */
async function shootWith(page: Page, css: string | null): Promise<string> {
    const style = css === null ? null : await page.addStyleTag({ content: css });
    await page.evaluate(
        () =>
            new Promise<void>((done) => {
                requestAnimationFrame(() => requestAnimationFrame(() => done()));
            }),
    );
    const shot = await page.screenshot({ animations: "disabled", caret: "hide" });
    await style?.evaluate((element) => {
        if (element instanceof Element) {
            element.remove();
        }
    });
    return shot.toString("base64");
}

/**
 * The shots the contrast check reads, as base64 PNG: the page as drawn, without its ink, without its pseudo-elements'
 * text, and without each mark batch.
 */
interface ContrastShots {
    readonly drawn: string;
    readonly ink: string;
    readonly forced: string;
    readonly forcedPseudo: string;
    readonly pseudo: string;
    readonly marks: readonly string[];
}

/**
 * Measure the targets in the page, from its shots:
 * - a text: its painted colour (composited over what lies beneath) against the background the page paints under it,
 *   read under its glyphs only (where they lie is read from a shot painting every text one loud colour, whatever its
 *   own), its box cut both ways into small square cells (a sixth of its line high, at least two device pixels), the
 *   worst cell kept, so no band or patch under them is outvoted; and its ink must show somewhere (it changes a pixel);
 * - a glyph: each ink of its symbol, composited over the face's painted colour (the middle of the face, its glyph
 *   hidden), at every size; and, as drawn, each ink must show (a pixel nearest the blend of that ink with the face), its
 *   best pixel at the floor on a face of at least `MIN_GLYPH_DEVICE_PX`, below which a shortfall is only reported;
 * - a mark: its best changed pixel against the same pixel without it (an `absent` one must change none).
 */
function measureContrast(
    page: Page,
    { shots, targets }: { readonly shots: ContrastShots; readonly targets: ContrastTargets },
): Promise<ContrastResult> {
    return page.evaluate(
        async ({ floor, sets, shotSet }) => {
            const INK_GAP = 2;
            const TEXT_CELLS_A_LINE = 6;
            const TEXT_CELL_FLOOR = 2;
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            async function pixels(base64: string): Promise<ImageData> {
                const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
                const bitmap = await createImageBitmap(new Blob([bytes], { type: "image/png" }));
                const canvas = document.createElement("canvas");
                canvas.width = bitmap.width;
                canvas.height = bitmap.height;
                const context = canvas.getContext("2d", { willReadFrequently: true });
                if (context === null) {
                    throw new Error("no 2d canvas to read a screenshot");
                }
                context.drawImage(bitmap, 0, 0);
                return context.getImageData(0, 0, bitmap.width, bitmap.height);
            }
            const linear = Array.from({ length: 256 }, (_unused, value) =>
                value <= 10 ? value / 255 / 12.92 : ((value / 255 + 0.055) / 1.055) ** 2.4,
            );
            function luminance([red, green, blue]: Rgb): number {
                return (
                    0.2126 * linear[Math.round(red)] +
                    0.7152 * linear[Math.round(green)] +
                    0.0722 * linear[Math.round(blue)]
                );
            }
            function ratioOf(first: Rgb, second: Rgb): number {
                const [high, low] = [luminance(first), luminance(second)].toSorted(
                    (one, other) => other - one,
                );
                return (high + 0.05) / (low + 0.05);
            }
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function over({ alpha, rgb }: PaintedColour, ground: Rgb): Rgb {
                function mix(channel: 0 | 1 | 2): number {
                    return Math.round(alpha * rgb[channel] + (1 - alpha) * ground[channel]);
                }
                return [mix(0), mix(1), mix(2)];
            }
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function css(rgb: Rgb): string {
                return `rgb(${rgb.join(", ")})`;
            }
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function pixelAt(image: ImageData, at: number): Rgb {
                return [image.data[at], image.data[at + 1], image.data[at + 2]];
            }
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function changed(pixel: Rgb, ground: Rgb): boolean {
                return (
                    Math.max(
                        Math.abs(pixel[0] - ground[0]),
                        Math.abs(pixel[1] - ground[1]),
                        Math.abs(pixel[2] - ground[2]),
                    ) >= 8
                );
            }
            /** The ink a pixel lies nearest the blend of with its ground, or null for none. */
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function inkOf(inks: readonly GlyphInk[], pixel: Rgb, ground: Rgb): GlyphInk | null {
                let nearest: GlyphInk | null = null;
                let closest = Number.POSITIVE_INFINITY;
                const toPixel = pixel.map((value, channel) => value - ground[channel]);
                for (const ink of inks) {
                    const toInk = ink.rgb.map((value, channel) => value - ground[channel]);
                    const span = toInk.reduce((sum, value) => sum + value * value, 0);
                    const along = toInk.reduce(
                        (sum, value, channel) => sum + value * toPixel[channel],
                        0,
                    );
                    const share = span === 0 ? 0 : along / span;
                    const miss = toPixel.reduce(
                        (sum, value, channel) => sum + (value - share * toInk[channel]) ** 2,
                        0,
                    );
                    if (share > 0 && miss < closest) {
                        closest = miss;
                        nearest = ink;
                    }
                }
                return nearest;
            }
            const drawn = await pixels(shotSet.drawn);
            const scale = drawn.width / window.innerWidth;
            const failures: ContrastFinding[] = [];
            const reported: ContrastFinding[] = [];
            const missing: string[] = [];
            const collected = { glyph: 0, mark: 0, text: 0 };
            const lowest = {
                glyph: Number.POSITIVE_INFINITY,
                mark: Number.POSITIVE_INFINITY,
                text: Number.POSITIVE_INFINITY,
            };
            function deviceBox(box: Box): {
                left: number;
                top: number;
                right: number;
                bottom: number;
            } {
                return {
                    bottom: Math.min(drawn.height, Math.ceil((box.top + box.height) * scale)),
                    left: Math.floor(box.left * scale),
                    right: Math.min(drawn.width, Math.ceil((box.left + box.width) * scale)),
                    top: Math.floor(box.top * scale),
                };
            }
            /** Every pixel of a device-pixel area, drawn and in `without`. */
            function* pixelsIn(
                area: { left: number; top: number; right: number; bottom: number },
                without: ImageData,
            ): Generator<{ pixel: Rgb; ground: Rgb }> {
                for (let row = area.top; row < area.bottom; row += 1) {
                    for (let column = area.left; column < area.right; column += 1) {
                        const at = (row * drawn.width + column) * 4;
                        yield { ground: pixelAt(without, at), pixel: pixelAt(drawn, at) };
                    }
                }
            }
            /**
             * The part of an area the ink changed, as the box around its largest cluster of changed pixels (none more
             * than `INK_GAP` apart, so a stray pixel two shots draw differently never widens it), or null where none
             * changed: a pseudo-element's text is measured there, since its own box is not the element's.
             */
            function inkedArea(
                area: { left: number; top: number; right: number; bottom: number },
                without: ImageData,
            ): { left: number; top: number; right: number; bottom: number } | null {
                const inked = new Set<number>();
                const width = area.right - area.left;
                for (let row = area.top; row < area.bottom; row += 1) {
                    for (let column = area.left; column < area.right; column += 1) {
                        const at = (row * drawn.width + column) * 4;
                        if (changed(pixelAt(drawn, at), pixelAt(without, at))) {
                            inked.add((row - area.top) * width + column - area.left);
                        }
                    }
                }
                let largest: number[] = [];
                const seen = new Set<number>();
                for (const start of inked) {
                    const cluster = seen.has(start) ? [] : [start];
                    seen.add(start);
                    for (const member of cluster) {
                        const [row, column] = [Math.floor(member / width), member % width];
                        for (let down = -INK_GAP; down <= INK_GAP; down += 1) {
                            for (let across = -INK_GAP; across <= INK_GAP; across += 1) {
                                const neighbour = (row + down) * width + column + across;
                                if (
                                    column + across >= 0 &&
                                    column + across < width &&
                                    inked.has(neighbour) &&
                                    !seen.has(neighbour)
                                ) {
                                    seen.add(neighbour);
                                    cluster.push(neighbour);
                                }
                            }
                        }
                    }
                    largest = cluster.length > largest.length ? cluster : largest;
                }
                if (largest.length === 0) {
                    return null;
                }
                const rows = largest.map((pixel) => area.top + Math.floor(pixel / width));
                const columns = largest.map((pixel) => area.left + (pixel % width));
                return {
                    bottom: Math.max(...rows) + 1,
                    left: Math.min(...columns),
                    right: Math.max(...columns) + 1,
                    top: Math.min(...rows),
                };
            }
            /**
             * A small cell's painted background: the pixel of median luminance, a colour the page really painted (never
             * one mixed from channels), steady against a stray edge pixel.
             */
            function paintedOf(values: readonly Rgb[]): Rgb {
                return values.toSorted((one, other) => luminance(one) - luminance(other))[
                    Math.floor(values.length / 2)
                ];
            }
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function middleOf(values: readonly Rgb[]): Rgb {
                function middle(channel: 0 | 1 | 2): number {
                    const sorted = values
                        .map((value) => value[channel])
                        .toSorted((one, other) => one - other);
                    return sorted[Math.floor(sorted.length / 2)];
                }
                return [middle(0), middle(1), middle(2)];
            }
            function record(
                target: ContrastTarget,
                finding: ContrastFinding,
                report = false,
            ): void {
                if (finding.ratio < floor) {
                    (report ? reported : failures).push(finding);
                }
                if (!report) {
                    lowest[target.kind] = Math.min(lowest[target.kind], finding.ratio);
                }
            }
            function measureText(
                target: ContrastTarget,
                {
                    background,
                    forced,
                    without,
                }: { background: ImageData; forced: ImageData; without: ImageData },
            ): void {
                const inked = inkedArea(deviceBox(target.box), without);
                const { colour } = target;
                if (inked === null || colour === undefined) {
                    missing.push(target.label);
                    return;
                }
                const area = target.hiddenIn === "pseudo" ? inked : deviceBox(target.box);
                const { bottom, left: start, right: end, top: first } = area;
                const cell = Math.max(
                    TEXT_CELL_FLOOR,
                    Math.round((bottom - first) / TEXT_CELLS_A_LINE),
                );
                let worst: ContrastFinding | null = null;
                for (let top = first; top < bottom; top += cell) {
                    for (let left = start; left < end; left += cell) {
                        const part = {
                            bottom: Math.min(bottom, top + cell),
                            left,
                            right: Math.min(end, left + cell),
                            top,
                        };
                        const under = [...pixelsIn(part, background)].map((pair) => pair.ground);
                        const beneath = [...pixelsIn(part, forced)]
                            .map(({ ground: shape }, index) =>
                                changed(shape, under[index]) ? under[index] : null,
                            )
                            .filter((pixel) => pixel !== null);
                        const ground = beneath.length === 0 ? null : paintedOf(beneath);
                        const ink = ground === null ? null : over(colour, ground);
                        const ratio =
                            ground === null || ink === null
                                ? Number.POSITIVE_INFINITY
                                : ratioOf(ink, ground);
                        if (
                            ground !== null &&
                            ink !== null &&
                            (worst === null || ratio < worst.ratio)
                        ) {
                            worst = {
                                ground: css(ground),
                                ink: css(ink),
                                label: target.label,
                                ratio,
                            };
                        }
                    }
                }
                if (worst !== null) {
                    record(target, worst);
                }
            }
            function measureGlyph(target: ContrastTarget, without: ImageData): void {
                const area = deviceBox(target.box);
                const inks = target.inks ?? [];
                const inset = {
                    across: (area.right - area.left) / 4,
                    down: (area.bottom - area.top) / 4,
                };
                const face = middleOf(
                    [
                        ...pixelsIn(
                            {
                                bottom: Math.round(area.bottom - inset.down),
                                left: Math.round(area.left + inset.across),
                                right: Math.round(area.right - inset.across),
                                top: Math.round(area.top + inset.down),
                            },
                            without,
                        ),
                    ].map((pair) => pair.ground),
                );
                const best = new Map<GlyphInk, { ratio: number; pixel: Rgb; ground: Rgb }>();
                for (const { ground, pixel } of pixelsIn(area, without)) {
                    const ink =
                        changed(pixel, ground) && luminance(pixel) < luminance(ground)
                            ? inkOf(inks, pixel, ground)
                            : null;
                    if (ink !== null) {
                        const ratio = ratioOf(pixel, ground);
                        if (ratio > (best.get(ink)?.ratio ?? 0)) {
                            best.set(ink, { ground, pixel, ratio });
                        }
                    }
                }
                for (const ink of inks) {
                    const painted = over(ink, face);
                    record(target, {
                        ground: css(face),
                        ink: css(painted),
                        label: `${target.label} (${ink.name})`,
                        ratio: ratioOf(painted, face),
                    });
                    const shown = best.get(ink);
                    if (shown === undefined) {
                        missing.push(`${target.label} (${ink.name} not drawn)`);
                    } else if (shown.ratio < floor) {
                        (target.small === true ? reported : failures).push({
                            ground: css(shown.ground),
                            ink: css(shown.pixel),
                            label: `${target.label} (${ink.name}, as drawn)`,
                            ratio: shown.ratio,
                        });
                    }
                }
            }
            function measureMark(target: ContrastTarget, without: ImageData): void {
                let best: { ratio: number; pixel: Rgb; ground: Rgb } | null = null;
                for (const { ground, pixel } of pixelsIn(deviceBox(target.box), without)) {
                    const ratio = changed(pixel, ground) ? ratioOf(pixel, ground) : 0;
                    if (ratio > (best?.ratio ?? 0)) {
                        best = { ground, pixel, ratio };
                    }
                }
                if (target.absent === true) {
                    if (best !== null) {
                        missing.push(`${target.label} painted`);
                    }
                    return;
                }
                if (best === null) {
                    missing.push(target.label);
                    return;
                }
                record(target, {
                    ground: css(best.ground),
                    ink: css(best.pixel),
                    label: target.label,
                    ratio: best.ratio,
                });
            }
            const ink = await pixels(shotSet.ink);
            const pseudo = await pixels(shotSet.pseudo);
            const forced = await pixels(shotSet.forced);
            const forcedPseudo = await pixels(shotSet.forcedPseudo);
            for (const target of sets.texts) {
                collected.text += 1;
                const pseudoText = target.hiddenIn === "pseudo";
                measureText(target, {
                    background: ink,
                    forced: pseudoText ? forcedPseudo : forced,
                    without: pseudoText ? pseudo : ink,
                });
            }
            for (const target of sets.glyphs) {
                collected.glyph += 1;
                measureGlyph(target, ink);
            }
            for (const [batch, shot] of shotSet.marks.entries()) {
                const without = await pixels(shot);
                for (const target of sets.marks[batch]) {
                    collected.mark += 1;
                    measureMark(target, without);
                }
            }
            return { collected, failures, lowest, missing, reported };
        },
        { floor: MIN_CONTRAST, sets: targets, shotSet: shots },
    );
}

function describeFinding(finding: ContrastFinding): string {
    return `${finding.label} ${finding.ratio.toFixed(2)} (${finding.ink} on ${finding.ground})`;
}

/**
 * Every text, mark and face's glyph on the board (a held-back face included) keeps 4.5:1 against what it is painted
 * on (`measureContrast`), every target collected shows its ink (each of a face's inks), and an absent mark paints
 * nothing. A small face's strokes under the floor as drawn are reported in the summary, never counted as passing.
 * The page is left as it was.
 */
async function checkContrast(page: Page, report: PageReport): Promise<string> {
    const targets = await collectContrastTargets(page);
    const drawn = await shootWith(page, null);
    const ink = await shootWith(page, HIDE_INK);
    const pseudo = await shootWith(page, HIDE_PSEUDO_TEXT);
    const forced = await shootWith(page, FORCE_INK);
    const forcedPseudo = await shootWith(page, FORCE_PSEUDO_INK);
    const marks: string[] = [];
    for (const batch of targets.marks.keys()) {
        marks.push(await shootWith(page, hideMarksCss(batch)));
    }
    await page.evaluate((rules) => {
        for (const rule of Array.from(
            { length: rules },
            (_unused, index) => `data-contrast-${index}`,
        )) {
            for (const element of document.querySelectorAll(`[${rule}]`)) {
                element.removeAttribute(rule);
            }
        }
    }, CONTRAST_MARKS.length);
    const { collected, failures, lowest, missing, reported } = await measureContrast(page, {
        shots: { drawn, forced, forcedPseudo, ink, marks, pseudo },
        targets,
    });
    report.expect(
        targets.unreadable.length === 0,
        `contrast cannot read: ${targets.unreadable.join("; ")}`,
    );
    report.expect(
        collected.text > 0 && collected.glyph > 0,
        `contrast collected ${collected.text} text(s) and ${collected.glyph} face(s): nothing to read`,
    );
    report.expect(
        missing.length === 0,
        `contrast: ink missing or misplaced: ${missing.join("; ")}`,
    );
    report.expect(
        failures.length === 0,
        `under ${MIN_CONTRAST}:1 contrast: ${failures.map(describeFinding).join("; ")}`,
    );
    const kinds: readonly ContrastKind[] = ["text", "glyph", "mark"];
    const counts = kinds.map((kind) =>
        collected[kind] === 0
            ? `0 ${kind}s`
            : `${collected[kind]} ${kind}s >= ${lowest[kind].toFixed(2)}`,
    );
    const small =
        reported.length === 0
            ? ""
            : `; reported, small faces' strokes under ${MIN_CONTRAST}:1 as drawn: ${reported.map(describeFinding).join("; ")}`;
    return `contrast ${counts.join(", ")}${small}`;
}

/** A toggle's lamp shows its check exactly while the toggle is pressed, so its state never reads by colour alone. */
function checkLamps(board: BoardMeasure, report: PageReport): void {
    const misread = board.lamps.filter((lamp) => lamp.checked !== lamp.pressed);
    report.expect(
        misread.length === 0,
        `${misread.length} toggle lamp(s) whose check does not match the toggle's state`,
    );
}

function describeLocalTile(tiles: readonly Box[]): string {
    const [tile] = tiles;
    return tile ? `${tile.width.toFixed(1)}x${tile.height.toFixed(1)}` : "none";
}

async function checkBoard(
    { measure, page, report, viewport }: PageRun,
    panelScrolls = false,
): Promise<string> {
    const board = await measureBoard(page);
    const screen = await viewportBox(page);
    checkBoardContent(board, report);
    report.expect(
        board.aside === null || board.zones === null || !intersects(board.zones, board.aside.box),
        `the table's surface ${board.zones === null ? "" : describeBox(board.zones)} reaches under the aside`,
    );
    if (viewport.supported) {
        const crowded = findOverlaps(board.centerTexts);
        report.expect(crowded.length === 0, `centre pieces overlap: ${crowded.join(", ")}`);
    }
    checkOverlay(board, viewport, report);
    if (viewport.supported) {
        checkResultPanel(await measureResultPanel(page), panelScrolls, report);
    }
    checkCallouts(board, report);
    checkStandings(board, { screen, viewport }, report);
    const pageExtent = { height: measure.scrollHeight, left: 0, top: 0, width: measure.innerWidth };
    if (viewport.portrait) {
        report.expect(
            contains(pageExtent, board.board),
            "the board is outside the scrollable page",
        );
        checkAside(board, pageExtent, report);
    } else {
        report.expect(
            contains(screen, board.board),
            `the board ${describeBox(board.board)} leaves the viewport`,
        );
        const asideBelow =
            board.aside !== null &&
            board.aside.story &&
            board.aside.box.top >= board.board.top + board.board.height - EPSILON;
        checkAside(board, asideBelow ? pageExtent : screen, report);
    }
    if (viewport.supported && !viewport.portrait) {
        checkLocalHand(board, { floor: viewport.ownTileFloor, screen }, report);
        checkRiverGaps(board, report);
        checkStripsApart(board, report);
        report.badgeAnchors = badgeAnchors(board);
        report.togglePlace = board.toggle;
        report.controlPlaces =
            board.timer === null ? null : [...(board.decisionCorner?.buttons ?? []), board.timer];
        checkActions(board, screen, report);
        checkSwitches(board, screen, report);
        checkLamps(board, report);
        checkNotices(board, report);
        checkResultNames(board, report);
        checkLeave(board, screen, report);
        checkReplayControls(board, screen, report);
        checkOpponentFaces(board, report);
    }
    if (viewport.desktop) {
        checkReplayText(board, report);
    } else if (viewport.supported && !viewport.portrait) {
        checkPhoneNarration(board, screen, report);
    }
    const fonts = Math.min(...board.fonts.map((font) => font.px));
    const scroll = `scroll ${describeSize(board.boardScroll)}`;
    const actions = board.actions.length === 0 ? "" : `, ${board.actions.length} button(s)`;
    return `board ${describeSize(board.boardClient)} ${scroll}, local tile ${describeLocalTile(board.localTiles)}${actions}, min text ${fonts}px`;
}

async function isShown(page: Page, selector: string): Promise<boolean> {
    return page.locator(selector).first().isVisible();
}

async function checkPanel(page: Page, countdown: boolean, report: PageReport): Promise<string> {
    const title = ".rotate-panel__title, .rotate-panel .failure-panel__title";
    const wayBack = [
        ".rotate-panel__leave:not([hidden])",
        ".rotate-panel .leave-confirm__leave",
        ".rotate-panel .failure-panel__leave",
    ].join(", ");
    await checkVisible(page, [title, wayBack], report);
    const seconds = page.locator(".rotate-panel__seconds");
    report.expect(
        (await seconds.count()) === (countdown ? 1 : 0),
        countdown ? "no countdown on the panel" : "a countdown on a panel with no decision",
    );
    return countdown ? `countdown ${await seconds.first().textContent()}` : "no countdown";
}

async function checkGame(run: PageRun): Promise<string> {
    const { measure, page, report, viewport } = run;
    const seconds = Number(
        await page.locator(".game__rotate .rotate-panel__seconds").textContent(),
    );
    report.expect(seconds > 0, `the open decision's countdown reads ${seconds}`);
    const { rotates } = viewport;
    report.expect(
        (await isShown(page, ".game__rotate")) === rotates,
        rotates ? "the rotate panel is hidden on an upright phone" : "the rotate panel shows",
    );
    report.expect(
        (await isShown(page, ".game__play")) === !rotates,
        rotates ? "the table shows on an upright phone" : "the table is hidden",
    );
    if (!rotates) {
        await checkVisible(
            page,
            [...BOARD_VISIBLE, ".game__play .decision-controls__countdown"],
            report,
        );
        return `countdown ${seconds}, ${await checkBoard(run)}`;
    }
    await checkVisible(
        page,
        [".game__rotate .rotate-panel__seconds", ".game__rotate .rotate-panel__leave"],
        report,
    );
    const panel = await page.evaluate(() => {
        const element = document.querySelector(".game__rotate");
        if (element === null) {
            return null;
        }
        const { height, left, top, width } = element.getBoundingClientRect();
        return {
            clientHeight: element.clientHeight,
            rect: { height, left, top, width },
            scrollHeight: element.scrollHeight,
        };
    });
    report.expect(panel !== null, "no .game__rotate");
    if (panel !== null) {
        const screen = { height: measure.innerHeight, left: 0, top: 0, width: measure.innerWidth };
        report.expect(
            contains(panel.rect, screen) && contains(screen, panel.rect),
            `the rotate panel ${describeBox(panel.rect)} does not cover the viewport`,
        );
        report.expect(
            panel.scrollHeight <= panel.clientHeight + EPSILON,
            "the rotate panel's content needs scrolling",
        );
    }
    return `countdown ${seconds}, rotate panel shown`;
}

async function checkPage(
    { page, report, viewport }: Omit<PageRun, "measure">,
    pageCase: PageCase,
): Promise<string> {
    const measure = await measurePage(page);
    const run = { measure, page, report, viewport };
    report.expect(
        measure.scrollWidth <= measure.innerWidth,
        `horizontal page overflow: ${measure.scrollWidth} > ${measure.innerWidth}`,
    );
    await checkVisible(page, pageCase.required.visible, report);
    switch (pageCase.kind) {
        case "document": {
            return `page ${measure.scrollWidth}x${measure.scrollHeight}`;
        }
        case "board": {
            return checkBoard(run, pageCase.panelScrolls);
        }
        case "panel": {
            return checkPanel(page, pageCase.countdown, report);
        }
        case "game": {
            return checkGame(run);
        }
    }
}

interface PageLoad {
    readonly context: BrowserContext;
    readonly viewport: Viewport;
    readonly origin: string;
    readonly shots: string;
}

async function loadPage(page: Page, pageCase: PageCase, origin: string): Promise<void> {
    await page.goto(origin + pageCase.path);
    if (pageCase.kind === "board" && pageCase.prepare) {
        await pageCase.prepare(page);
    }
    const { attached = [], visible } = pageCase.required;
    for (const selector of visible) {
        await page.waitForSelector(selector, { state: "visible", timeout: SELECTOR_TIMEOUT_MS });
    }
    for (const selector of attached) {
        await page.waitForSelector(selector, { state: "attached", timeout: SELECTOR_TIMEOUT_MS });
    }
}

/** The tile faces a page draws: every face's sprite symbol, with content, and whether a shown face drew a box. */
interface TileFaces {
    readonly count: number;
    readonly unresolved: readonly string[];
    readonly drawn: boolean;
}

/**
 * Fail a page whose tile sprite never loaded, or whose faces name a symbol the sprite lacks or holds empty: either
 * leaves the faces blank, which a layout check alone passes.
 */
async function checkTileFaces(page: Page, report: PageReport): Promise<void> {
    const loaded = await page
        .waitForFunction(() => document.documentElement.dataset.tileSprite === "ready", null, {
            timeout: SELECTOR_TIMEOUT_MS,
        })
        .then(() => true)
        .catch(() => false);
    report.expect(loaded, "the tile sprite did not load");
    const faces = await page.evaluate((): TileFaces => {
        const uses = [...document.querySelectorAll(".tile svg use")].filter(
            (use) => use instanceof SVGUseElement,
        );
        const unresolved = uses
            .map((use) => use.getAttribute("href") ?? "")
            .filter(
                (href) => (document.querySelector(`symbol${href}`)?.childElementCount ?? 0) === 0,
            );
        const shown = uses.filter((use) => use.closest("svg")?.checkVisibility() === true);
        const drawn =
            shown.length === 0 ||
            shown.some((use) => {
                const bounds = use.getBBox();
                return bounds.width > 0 && bounds.height > 0;
            });
        return { count: uses.length, drawn, unresolved: [...new Set(unresolved)] };
    });
    if (faces.count === 0) {
        return;
    }
    report.expect(
        faces.unresolved.length === 0,
        `tile faces with no sprite symbol: ${faces.unresolved.join(", ")}`,
    );
    report.expect(faces.drawn, "no tile face drew");
}

/**
 * Fail a page whose face did not load (its FontFace `loaded` and `document.fonts.check` true, since `check` is also true
 * for a family no face declares), or, with the face blocked, whose FontFace did not fail once asked to load (WebKit
 * leaves a face whose preload failed `unloaded` until then): the checks that follow then measure the fallback stack.
 */
async function checkFont(page: Page, pageCase: PageCase, report: PageReport): Promise<void> {
    const expected = pageCase.fontBlocked === true ? "error" : "loaded";
    if (expected === "error") {
        await page.evaluate(async (family) => {
            const faces: FontFace[] = [];
            document.fonts.forEach((face) => {
                if (face.family.replaceAll('"', "") === family) {
                    faces.push(face);
                }
            });
            await Promise.allSettled(faces.map((face) => face.load()));
        }, FONT_FAMILY);
    }
    const font = await page
        .waitForFunction(
            (family) => {
                const statuses: string[] = [];
                document.fonts.forEach((face) => {
                    if (face.family.replaceAll('"', "") === family) {
                        statuses.push(face.status);
                    }
                });
                const settled =
                    statuses.length > 0 &&
                    statuses.every((status) => status === "loaded" || status === "error");
                return settled && { checked: document.fonts.check(`16px "${family}"`), statuses };
            },
            FONT_FAMILY,
            { timeout: SELECTOR_TIMEOUT_MS },
        )
        .then((handle) => handle.jsonValue())
        .catch(() => null);
    if (font === null || font === false) {
        report.expect(false, `the ${FONT_FAMILY} face never loaded or failed`);
        return;
    }
    report.expect(
        font.statuses.length === 1 && font.statuses[0] === expected,
        `the ${FONT_FAMILY} face is ${font.statuses.join(", ")}, not ${expected}`,
    );
    if (expected === "loaded") {
        report.expect(font.checked, `document.fonts.check says ${FONT_FAMILY} is not ready`);
    }
}

/** The request for the face a page was told to fail, which the browser reports as a console error. */
function isBlockedFont(pageCase: PageCase, url: string): boolean {
    return pageCase.fontBlocked === true && url.endsWith(FONT_EXTENSION);
}

async function runPage(
    { context, origin, shots, viewport }: PageLoad,
    pageCase: PageCase,
): Promise<PageReport> {
    const report = new PageReport();
    const page = await context.newPage();
    page.on("console", (message) => {
        if (message.type() === "error" && !isBlockedFont(pageCase, message.location().url)) {
            report.failures.push(`console error: ${message.text()}`);
        }
    });
    page.on("pageerror", (error) => report.failures.push(`page error: ${error.message}`));
    page.on("requestfailed", (request) => {
        if (!isBlockedFont(pageCase, request.url())) {
            report.failures.push(`request failed: ${request.url()}`);
        }
    });
    try {
        await loadPage(page, pageCase, origin);
        await emulateInsets(page, viewport.insets);
        await checkCaptureModel(page, viewport, report);
        await page.evaluate(() => document.fonts.ready.then(() => undefined));
        await checkFont(page, pageCase, report);
        await page.waitForTimeout(SETTLE_MS);
        await checkTileFaces(page, report);
        report.summary = await checkPage({ page, report, viewport }, pageCase);
        await page.screenshot({ path: join(shots, `${viewport.name}-${pageCase.name}.png`) });
        if (pageCase.contrast === true && CONTRAST_VIEWPORTS.has(viewport.name)) {
            report.summary += `, ${await checkContrast(page, report)}`;
        }
        if (pageCase.kind === "board") {
            await checkWinnerPaging(page, report);
        }
    } catch (error: unknown) {
        report.failures.push(error instanceof Error ? error.message : String(error));
    } finally {
        await page.close();
    }
    if (report.checks === 0 && report.failures.length === 0) {
        report.failures.push("no check ran");
    }
    return report;
}

/** One page at one viewport, checked in a context of its own, its findings named by both. */
interface PageTask {
    readonly viewport: Viewport;
    readonly pageCase: PageCase;
}

interface TaskResult {
    readonly name: string;
    readonly viewport: string;
    readonly page: string;
    readonly report: PageReport;
}

async function runTask(
    browser: Browser,
    { pageCase, viewport }: PageTask,
    { fixtures, shots }: { readonly fixtures: Fixtures; readonly shots: string },
): Promise<TaskResult> {
    const frames = pageCase.kind === "game" ? fixtures.frames.get(pageCase.checkpoint) : [];
    const context = await openContext(browser, viewport, {
        fontBlocked: pageCase.fontBlocked,
        frames: frames ?? [],
        origin: fixtures.origin,
    });
    try {
        const report = await runPage(
            { context, origin: fixtures.origin, shots, viewport },
            pageCase,
        );
        return {
            name: `${viewport.name} ${pageCase.name}`,
            page: pageCase.name,
            report,
            viewport: viewport.name,
        };
    } finally {
        await context.close();
    }
}

/** Run `tasks` with at most `limit` at once, keeping their order in the results. */
async function runPooled<Task, Result>(
    tasks: readonly Task[],
    limit: number,
    run: (task: Task) => Promise<Result>,
): Promise<Result[]> {
    const results: Result[] = [];
    let next = 0;
    async function worker(): Promise<void> {
        for (let index = next++; index < tasks.length; index = next++) {
            results[index] = await run(tasks[index]);
        }
    }
    await Promise.all(Array.from({ length: Math.min(limit, tasks.length) }, worker));
    return results;
}

/** The pages and viewports a run checks: all of them, or the ones `--page` and `--viewport` name. */
interface Selection {
    readonly pages: readonly PageCase[];
    readonly viewports: readonly Viewport[];
    readonly partial: boolean;
}

/** The selected pages at each of an engine's selected viewports. */
function tasksOf(engine: BrowserType, selection: Selection): PageTask[] {
    const viewports = selection.viewports.filter((viewport) => viewport.engine === engine);
    return viewports.flatMap((viewport) =>
        selection.pages
            .filter(({ onlyAt }) => onlyAt === undefined || onlyAt.includes(viewport.name))
            .filter(
                ({ name }) => viewport.onlyPages === undefined || viewport.onlyPages.includes(name),
            )
            .map((pageCase) => ({ pageCase, viewport })),
    );
}

/** Check an engine's tasks in one browser, several pages at once. */
async function runEngine(
    browser: Browser,
    tasks: readonly PageTask[],
    run: { readonly fixtures: Fixtures; readonly shots: string },
): Promise<TaskResult[]> {
    return runPooled(tasks, PAGES_AT_ONCE, (task) => runTask(browser, task, run));
}

function median(values: readonly number[]): number {
    const sorted = values.toSorted((left, right) => left - right);
    return sorted[Math.floor(sorted.length / 2)];
}

/** One load's timing and what the replay view says it read, from its `replay-load` measure. */
interface LoadRun {
    readonly ms: number;
    readonly detail: unknown;
}

/** One load of the largest replay on a slowed CPU: the view's `replay-load` measure. */
async function measureReplayLoad(browser: Browser, origin: string): Promise<LoadRun> {
    const context = await openContext(browser, VIEWPORTS[0], { frames: [], origin });
    try {
        const page = await context.newPage();
        const cdp = await context.newCDPSession(page);
        await cdp.send("Emulation.setCPUThrottlingRate", { rate: LOAD_CPU_SLOWDOWN });
        await page.goto(`${origin}/play/history/${BUDGET_GAME_ID}`);
        await page.waitForSelector(".replay-controls", { timeout: SELECTOR_TIMEOUT_MS * 2 });
        return await page.evaluate((name) => {
            const [entry] = performance.getEntriesByName(name, "measure");
            return entry instanceof PerformanceMeasure
                ? { detail: entry.detail, ms: entry.duration }
                : { detail: null, ms: Number.NaN };
        }, LOAD_MEASURE);
    } finally {
        await context.close();
    }
}

/** Why a load's timing does not count: it read something other than the whole fixture, or recorded no time. */
function invalidLoad({ detail, ms }: LoadRun): string | null {
    if (JSON.stringify(detail) !== JSON.stringify(LOAD_EXPECTED)) {
        return `read ${JSON.stringify(detail)}, not the fixture's ${JSON.stringify(LOAD_EXPECTED)}`;
    }
    return Number.isFinite(ms) && ms > 0 ? null : `recorded no time (${ms})`;
}

async function checkReplayLoad(browser: Browser, origin: string): Promise<string[]> {
    const runs: LoadRun[] = [];
    for (let run = 0; run < LOAD_RUNS; run += 1) {
        runs.push(await measureReplayLoad(browser, origin));
    }
    const invalid = runs.flatMap((run) => invalidLoad(run) ?? []);
    if (invalid.length > 0) {
        return invalid.map((reason) => `replay load: a run ${reason}`);
    }
    const typical = median(runs.map((run) => run.ms));
    const shown = runs.map((run) => run.ms.toFixed(0)).join(", ");
    console.info(
        `replay load at ${LOAD_CPU_SLOWDOWN}x CPU slowdown: median ${typical.toFixed(0)} ms (${shown}), budget ${LOAD_BUDGET_MS} ms`,
    );
    return typical > LOAD_BUDGET_MS
        ? [`replay load: median ${typical.toFixed(0)} ms over the ${LOAD_BUDGET_MS} ms budget`]
        : [];
}

function reportFailures(results: readonly TaskResult[]): string[] {
    return results.flatMap(({ name, report }) => {
        if (report.summary !== "") {
            console.info(`${name}: ${report.summary}`);
        }
        return report.failures.map((failure) => `${name}: ${failure}`);
    });
}

/**
 * Every badge keeps one place at a viewport, whatever the seats hold: the live board's decisions stories (an anchor's
 * three checkpoints, the dense prompts, panels over it) all put each seat's badge at the same point.
 */
function checkBadgePlaces(results: readonly TaskResult[]): string[] {
    const live = results.filter(
        ({ page, report }) => page.startsWith("decisions-") && report.badgeAnchors !== null,
    );
    const viewports = [...new Set(live.map(({ viewport }) => viewport))];
    return viewports.flatMap((viewport) => {
        const pages = live.filter((result) => result.viewport === viewport);
        const placed = pages.flatMap(({ page, report }) =>
            Object.entries(report.badgeAnchors ?? {}).map(([seat, point]) => ({
                page,
                point,
                seat,
            })),
        );
        return [...new Set(placed.map(({ seat }) => seat))].flatMap((seat) => {
            const [first, ...rest] = placed.filter((place) => place.seat === seat);
            if (first === undefined) {
                return [];
            }
            return rest
                .filter(
                    ({ point }) =>
                        Math.abs(point[0] - first.point[0]) > EPSILON ||
                        Math.abs(point[1] - first.point[1]) > EPSILON,
                )
                .map(
                    ({ page, point }) =>
                        `${viewport}: the ${seat} badge stands at ${Math.round(point[0])},${Math.round(point[1])} on ${page}, at ${Math.round(first.point[0])},${Math.round(first.point[1])} on ${first.page}`,
                );
        });
    });
}

/**
 * A decision's controls and timer stand where they stood while it was open once it is answered or has run out
 * (`CONTROL_FAMILIES`), at each viewport.
 */
function checkControlPlaces(results: readonly TaskResult[]): string[] {
    return CONTROL_FAMILIES.flatMap((family) => {
        const members = results.filter(
            ({ page, report }) =>
                (page === family || page.startsWith(`${family}-`)) && report.controlPlaces !== null,
        );
        return members.flatMap(({ page, report, viewport }) => {
            const open = members.find(
                (member) => member.page === family && member.viewport === viewport,
            );
            const expected = open?.report.controlPlaces;
            if (page === family || expected === undefined || expected === null) {
                return [];
            }
            const places = report.controlPlaces ?? [];
            const moved =
                places.length !== expected.length ||
                places.some(
                    (place, index) =>
                        Math.abs(place.left - expected[index].left) > EPSILON ||
                        Math.abs(place.top - expected[index].top) > EPSILON ||
                        Math.abs(place.width - expected[index].width) > EPSILON ||
                        Math.abs(place.height - expected[index].height) > EPSILON,
                );
            return moved
                ? [
                      `${viewport}: ${page}'s controls or timer stand apart from ${family}'s: ${places.map(describeBox).join(", ")}`,
                  ]
                : [];
        });
    });
}

function sameBox(first: Box, second: Box): boolean {
    return (
        Math.abs(first.left - second.left) <= EPSILON &&
        Math.abs(first.top - second.top) <= EPSILON &&
        Math.abs(first.width - second.width) <= EPSILON &&
        Math.abs(first.height - second.height) <= EPSILON
    );
}

/** The landscape phones, whose column and band the toggle pin is about; an upright board lays its controls in rows. */
const LANDSCAPE_PHONES: ReadonlySet<string> = new Set(
    VIEWPORTS.filter((viewport) => !viewport.desktop && !viewport.portrait).map(({ name }) => name),
);

/** A landscape phone's toggle stands where it stood before it was pressed (`TOGGLE_FAMILIES`). */
function checkTogglePlaces(results: readonly TaskResult[]): string[] {
    return TOGGLE_FAMILIES.flatMap(([off, on]) =>
        results
            .filter(({ page, viewport }) => page === on && LANDSCAPE_PHONES.has(viewport))
            .flatMap(({ report, viewport }) => {
                const before = results.find(
                    (result) => result.page === off && result.viewport === viewport,
                );
                const [was, is] = [before?.report.togglePlace, report.togglePlace];
                if (was === undefined || was === null || is === null) {
                    return before === undefined
                        ? []
                        : [`${viewport}: ${on} or ${off} shows no toggle`];
                }
                return sameBox(was, is)
                    ? []
                    : [
                          `${viewport}: the toggle moves when pressed, ${describeBox(was)} on ${off}, ${describeBox(is)} on ${on}`,
                      ];
            }),
    );
}

/** Both engines' pages at once, then, on a full run, the replay load budget on the Chromium browser, the CPU idle. */
async function checkAll(
    fixtures: Fixtures,
    shots: string,
    selection: Selection,
): Promise<string[]> {
    const [chromiumBrowser, webkitBrowser] = await Promise.all([
        chromium.launch(),
        webkit.launch(),
    ]);
    try {
        const run = { fixtures, shots };
        const results = await Promise.all([
            runEngine(chromiumBrowser, tasksOf(chromium, selection), run),
            runEngine(webkitBrowser, tasksOf(webkit, selection), run),
        ]);
        const pageFailures = [
            ...reportFailures(results.flat()),
            ...checkBadgePlaces(results.flat()),
            ...checkControlPlaces(results.flat()),
            ...checkTogglePlaces(results.flat()),
        ];
        if (selection.partial) {
            return pageFailures;
        }
        return [...pageFailures, ...(await checkReplayLoad(chromiumBrowser, fixtures.origin))];
    } finally {
        await Promise.all([chromiumBrowser.close(), webkitBrowser.close()]);
    }
}

/** Remove the last run's screenshots, so the folder holds only this run's. */
async function clearShots(folder: string): Promise<void> {
    const files = await readdir(folder).catch(() => []);
    await Promise.all(
        files.filter((file) => file.endsWith(".png")).map((file) => rm(join(folder, file))),
    );
}

/** Keep the items whose name contains one of `filters`, or every item when there are none. */
function matching<Item extends { readonly name: string }>(
    items: readonly Item[],
    filters: readonly string[],
): readonly Item[] {
    if (filters.length === 0) {
        return items;
    }
    return items.filter((item) => filters.some((filter) => item.name.includes(filter)));
}

/** The run's selection from `--page` and `--viewport` (each repeatable, matching a name by substring). */
function selectRun(pageFilters: readonly string[], viewportFilters: readonly string[]): Selection {
    return {
        pages: matching(PAGES, pageFilters),
        partial: pageFilters.length > 0 || viewportFilters.length > 0,
        viewports: matching(VIEWPORTS, viewportFilters),
    };
}

async function main(): Promise<number> {
    const { values } = parseArgs({
        options: {
            page: { default: [], multiple: true, type: "string" },
            shots: { default: DEFAULT_SHOTS, type: "string" },
            viewport: { default: [], multiple: true, type: "string" },
        },
    });
    const selection = selectRun(values.page, values.viewport);
    if (tasksOf(chromium, selection).length + tasksOf(webkit, selection).length === 0) {
        console.error(
            `Visual check selected nothing: pages ${PAGES.map(({ name }) => name).join(", ")}; viewports ${VIEWPORTS.map(({ name }) => name).join(", ")}`,
        );
        return 1;
    }
    const shots = resolve(values.shots);
    if (shots === DEFAULT_SHOTS) {
        await clearShots(shots);
    }
    const frames = await transcriptFrames();
    const { origin, server } = await startServer();
    const failures = await checkAll({ frames, origin }, shots, selection).finally(() =>
        server.close(),
    );
    if (failures.length > 0) {
        console.error(
            `Visual check failed:\n${failures.map((failure) => `  ${failure}`).join("\n")}`,
        );
        return 1;
    }
    const pages = tasksOf(chromium, selection).length + tasksOf(webkit, selection).length;
    const scope = selection.partial ? "partial run, no replay load budget; " : "";
    console.info(`Visual check passed: ${scope}${pages} pages; screenshots in ${shots}`);
    return 0;
}

process.exitCode = await main();
