import { type BrowserContextOptions, type Page, chromium, devices, webkit } from "playwright";

import { type Box, type Size, contains, describeBox, describeSize } from "./boxes.ts";
import { type Insets, type PageReport, type Viewport } from "./model.ts";

/** The smallest local hand tile a landscape table may draw on a supported phone, in CSS pixels: a tap target. */
const MIN_TAP: Size = { height: 42, width: 32 };
/** The notch phone's capture model: an iPhone 13's full display in landscape, less the insets the gate emulates. */
const NOTCH_VIEWPORT: Size = { height: 390, width: 844 };
const NOTCH_INSETS: Insets = { bottom: 21, left: 47, right: 47 };
const NOTCH_SAFE_AREA: Box = { height: 369, left: 47, top: 0, width: 750 };
const NOTCH_BOARD: Size = { height: 390, width: 750 };

function deviceOptions(name: string): BrowserContextOptions {
    const { defaultBrowserType: _engine, ...options } = devices[name];
    return options;
}

/**
 * A short laptop's window (1366x768 less its browser's chrome), where the core is bounded by the foreground band rather
 * than its share of the height: the band's corners shared, a chip bounded by its row.
 */
export const SHORT_DESKTOP = "desktop-short";
/** A narrow desktop (800x600, a tablet's or a small window's), where the desktop's geometry takes the phone's chrome. */
export const NARROW_DESKTOP = "desktop-narrow";
/** A large desktop (2560x1440), where the chrome steps up: a control's height against the band. */
export const LARGE_DESKTOP = "desktop-large";
/** A short tablet's or a small laptop's window (1024x510): wide, but under the phone board's 520px height. */
export const SHORT_TABLET = "tablet-short";

/** The smallest supported landscape (667x375), the one viewport a page names none is checked at. */
export const FLOOR = "phone-se-landscape";
/** The notched landscape phone, whose insets and capture model only it emulates. */
export const NOTCH_PHONE = "phone-notch-landscape";
/** The upright phone, where the live game shows the rotate panel and a board lays out upright. */
export const UPRIGHT_PHONE = "phone-portrait";
/**
 * A narrow desktop window (375x548): the live game shows the rotate panel even without touch input,
 * while replays and storybooks keep their upright board.
 */
export const SHORT_UPRIGHT = "window-upright";
/**
 * A near-square upright window (800x801, no touch screen), where the river tile is largest against the right strip's
 * room, so the densest right strip takes its second meld line beside the decisions, the options and the notices.
 */
export const SQUARE_UPRIGHT = "window-square";
/** The mid desktop (1440x900), the spec's reference desktop. */
export const MID_DESKTOP = "desktop-1440";
/** The three classes the representative worst cases are chosen across: the floor, the mid and the largest desktop. */
export const WORST_CASES: readonly string[] = [FLOOR, MID_DESKTOP, LARGE_DESKTOP];

/** A laptop window under the short desktop's 760px (1280x720), which shares the band's corners. */
export const SHORT_LAPTOP = "laptop-720";
/** The shortest regular desktop (1440x770), just over the short desktop's 760px: the band's corners its own. */
export const SHORTEST_REGULAR_DESKTOP = "laptop-770";

/**
 * An ultrawide window (2560x1080), where the own hand starts past the play switches: the own badge keeps a lane of its
 * own and the decisions' row starts past it.
 */
export const ULTRAWIDE = "window-2560";

/** Laptop windows on either side of the short desktop's 760px. */
const LAPTOP_VIEWPORTS: readonly Viewport[] = (
    [
        [SHORT_LAPTOP, 1280, 720],
        [SHORTEST_REGULAR_DESKTOP, 1440, 770],
    ] as const
).map(([name, width, height]) => ({
    context: { viewport: { height, width } },
    desktop: true,
    engine: chromium,
    name,
    portrait: false,
    rotates: false,
    supported: true,
}));
export const LAPTOPS: readonly string[] = [SHORT_LAPTOP, SHORTEST_REGULAR_DESKTOP];

/**
 * Small desktop windows (700x540, 900x600) where a panel's content meets the board's height and width at once: the
 * a short result's pager and confirm stay clickable.
 */
const SMALL_WINDOW_VIEWPORTS: readonly Viewport[] = [
    [700, 540],
    [900, 600],
].map(([width, height]) => ({
    context: { viewport: { height, width } },
    desktop: true,
    engine: chromium,
    name: `window-${width}`,
    portrait: false,
    rotates: false,
    supported: true,
}));
export const SMALL_WINDOWS: readonly string[] = SMALL_WINDOW_VIEWPORTS.map(({ name }) => name);
/** The smaller window, smaller each way, where a panel's content binds first. */
export const [SMALLEST_WINDOW] = SMALL_WINDOWS;

/**
 * Wider phones at the floor's height and a larger landscape phone, where the centre must keep a full six-tile row
 * while the hand and decisions fit beside the rivers.
 */
const WIDER_PHONE_VIEWPORTS: readonly Viewport[] = [
    { height: 375, width: 680 },
    { height: 375, width: 700 },
    { height: 430, width: 932 },
].map((dimensions) => ({
    context: {
        ...deviceOptions("iPhone SE (3rd gen) landscape"),
        screen: dimensions,
        viewport: dimensions,
    },
    desktop: false,
    engine: webkit,
    name: `phone-${dimensions.width}`,
    ownTileFloor: MIN_TAP,
    portrait: false,
    rotates: false,
    supported: true,
}));
export const WIDER_PHONES: readonly string[] = WIDER_PHONE_VIEWPORTS.map(({ name }) => name);

/** An iPhone 11 in landscape Safari (iOS 26): its 896x414 display less the address capsule and the toolbar. */
const SAFARI_11_VIEWPORT: Size = { height: 275, width: 896 };
const SAFARI_11_INSETS: Insets = { bottom: 0, left: 44, right: 44 };
const SAFARI_11_SAFE_AREA: Box = { height: 275, left: 44, top: 0, width: 808 };
/** A Galaxy A25 (1080x2340 at 2.625, 891x411 CSS) in landscape Chrome: its status bar and 56px toolbar taken. */
const CHROME_A25_VIEWPORT: Size = { height: 331, width: 891 };
const CHROME_A25_SCREEN: Size = { height: 411, width: 891 };

/** The iPhone 11 in landscape Safari, whose 275px box the solver fell through to its 2px river tile (2026-11-08). */
export const SAFARI_PHONE = "phone-11-safari";
/** A Galaxy A25 in landscape Chrome, the Android box the same release broke on. */
export const CHROME_PHONE = "phone-a25-chrome";
/** An iPhone 11 in landscape with its browser's bars gone: the board down to the screen's edge, past the bottom inset. */
export const FULLSCREEN_PHONE = "phone-11-fullscreen";

const FULLSCREEN_11_VIEWPORT: Size = { height: 414, width: 896 };
const FULLSCREEN_11_INSETS: Insets = { bottom: 21, left: 44, right: 44 };
const FULLSCREEN_11_SAFE_AREA: Box = { height: 393, left: 44, top: 0, width: 808 };
const FULLSCREEN_11_BOARD: Size = { height: 414, width: 808 };

/**
 * Phones as their browsers box the board with their bars shown, not as their displays: a page's viewport is the
 * display less the browser's own bars until the swipe the board asks for collapses them (the live page stands a large
 * viewport tall for that). Each is a measured or estimated box of a device the game shipped unplayable on; a page
 * naming them runs on their real, far shorter height, where every px floor of the chrome binds first, and must still
 * lay out whole and tappable. The floor display's Safari box (667x236) is shorter still and pinned by the geometry's
 * tests alone: its decisions' column cannot hold a call over the band's row, which the swipe resolves.
 */
const BROWSER_PHONE_VIEWPORTS: readonly Viewport[] = [
    {
        barsShown: { riverFloor: { height: 17, width: 13 } },
        captureModel: {
            board: { height: SAFARI_11_SAFE_AREA.height, width: SAFARI_11_SAFE_AREA.width },
            safeArea: SAFARI_11_SAFE_AREA,
            viewport: SAFARI_11_VIEWPORT,
        },
        context: {
            ...deviceOptions("iPhone 11 landscape"),
            screen: { height: 414, width: 896 },
            viewport: SAFARI_11_VIEWPORT,
        },
        desktop: false,
        engine: webkit,
        insets: SAFARI_11_INSETS,
        name: SAFARI_PHONE,
        ownTileFloor: MIN_TAP,
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        barsShown: { riverFloor: { height: 17, width: 13 } },
        context: {
            ...deviceOptions("Pixel 7 landscape"),
            screen: CHROME_A25_SCREEN,
            viewport: CHROME_A25_VIEWPORT,
        },
        desktop: false,
        engine: chromium,
        name: CHROME_PHONE,
        ownTileFloor: MIN_TAP,
        portrait: false,
        rotates: false,
        supported: true,
    },
];
export const BROWSER_PHONES: readonly string[] = BROWSER_PHONE_VIEWPORTS.map(({ name }) => name);

/**
 * The acceptance viewports, each checked only on the pages that name it (`PageCase.at`): the floor, the mid and the
 * largest desktop, across which the representative worst cases are chosen (`WORST_CASES`), the desktops, laptops,
 * windows, tablet and phones that each guard one path of the layout, the upright phone that gets the rotate panel,
 * the notched landscape phone (its insets cover the plain one), and the phones boxed by their browsers
 * (`BROWSER_PHONES`). The notched phone is the full-display capture model: Playwright's "iPhone 13 landscape" options
 * with the viewport and screen set to the full 844x390 display after them (the device's own 750x342 is an older
 * Safari's viewport with its chrome), then the insets, so its safe area is 750x369. It is not what a browser gives
 * the board; the browser phones are, and a layout that holds only on the full displays has failed on a phone.
 */
export const VIEWPORTS: readonly Viewport[] = [
    {
        context: { viewport: { height: 900, width: 1440 } },
        desktop: true,
        engine: chromium,
        name: MID_DESKTOP,
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: { viewport: { height: 657, width: 1366 } },
        desktop: true,
        engine: chromium,
        name: SHORT_DESKTOP,
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: { viewport: { height: 600, width: 800 } },
        desktop: true,
        engine: chromium,
        name: NARROW_DESKTOP,
        portrait: false,
        rotates: false,
        supported: true,
    },
    ...LAPTOP_VIEWPORTS,
    ...SMALL_WINDOW_VIEWPORTS,
    {
        context: { viewport: { height: 1080, width: 2560 } },
        desktop: true,
        engine: chromium,
        name: ULTRAWIDE,
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: { viewport: { height: 510, width: 1024 } },
        desktop: false,
        engine: chromium,
        name: SHORT_TABLET,
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: { viewport: { height: 1440, width: 2560 } },
        desktop: true,
        engine: chromium,
        name: LARGE_DESKTOP,
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: deviceOptions("iPhone 13"),
        desktop: false,
        engine: webkit,
        name: UPRIGHT_PHONE,
        ownTileFloor: MIN_TAP,
        portrait: true,
        rotates: true,
        supported: true,
    },
    {
        context: { viewport: { height: 548, width: 375 } },
        desktop: true,
        engine: chromium,
        name: SHORT_UPRIGHT,
        portrait: true,
        rotates: true,
        supported: true,
    },
    {
        context: { viewport: { height: 801, width: 800 } },
        desktop: true,
        engine: chromium,
        name: SQUARE_UPRIGHT,
        portrait: true,
        rotates: false,
        supported: true,
    },
    {
        captureModel: {
            board: NOTCH_BOARD,
            safeArea: NOTCH_SAFE_AREA,
            viewport: NOTCH_VIEWPORT,
        },
        context: {
            ...deviceOptions("iPhone 13 landscape"),
            screen: NOTCH_VIEWPORT,
            viewport: NOTCH_VIEWPORT,
        },
        desktop: false,
        engine: webkit,
        insets: NOTCH_INSETS,
        name: NOTCH_PHONE,
        ownTileFloor: MIN_TAP,
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        captureModel: {
            board: FULLSCREEN_11_BOARD,
            safeArea: FULLSCREEN_11_SAFE_AREA,
            viewport: FULLSCREEN_11_VIEWPORT,
        },
        context: {
            ...deviceOptions("iPhone 11 landscape"),
            screen: FULLSCREEN_11_VIEWPORT,
            viewport: FULLSCREEN_11_VIEWPORT,
        },
        desktop: false,
        engine: webkit,
        insets: FULLSCREEN_11_INSETS,
        name: FULLSCREEN_PHONE,
        ownTileFloor: MIN_TAP,
        portrait: false,
        rotates: false,
        supported: true,
    },
    {
        context: deviceOptions("iPhone SE (3rd gen) landscape"),
        desktop: false,
        engine: webkit,
        name: FLOOR,
        ownTileFloor: MIN_TAP,
        portrait: false,
        rotates: false,
        supported: true,
    },
    ...WIDER_PHONE_VIEWPORTS,
    ...BROWSER_PHONE_VIEWPORTS,
];

/** The page sees the capture model's viewport, and the emulated insets leave exactly its safe area. */
export async function checkCaptureModel(
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
        const board = document.querySelector(".game-board")?.getBoundingClientRect() ?? null;
        return {
            board: board === null ? null : { height: board.height, width: board.width },
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
    if (seen.board !== null) {
        report.expect(
            seen.board.width === captureModel.board.width &&
                seen.board.height === captureModel.board.height,
            `the board is ${describeSize(seen.board)}, not the capture model's ${describeSize(captureModel.board)}`,
        );
    }
}

export async function emulateInsets(page: Page, insets: Insets | undefined): Promise<void> {
    if (insets === undefined) {
        return;
    }
    const { bottom, left, right } = insets;
    await page.addStyleTag({
        content: `:root { --ronin-safe-left: ${left}px; --ronin-safe-right: ${right}px; --ronin-safe-bottom: ${bottom}px; }`,
    });
}
