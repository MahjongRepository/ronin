import { type BrowserContextOptions, type Page, chromium, devices, webkit } from "playwright";

import { type Box, type Size, contains, describeBox, describeSize } from "./boxes.ts";
import { type Insets, type PageReport, type Viewport } from "./model.ts";

/** The smallest local hand tile a landscape table may draw on a supported phone, in CSS pixels: a tap target. */
const MIN_TAP: Size = { height: 42, width: 32 };
/** The notch phone's capture model: an iPhone 13's full display in landscape, less the insets the gate emulates. */
const NOTCH_VIEWPORT: Size = { height: 390, width: 844 };
const NOTCH_INSETS: Insets = { bottom: 21, left: 47, right: 47 };
const NOTCH_SAFE_AREA: Box = { height: 369, left: 47, top: 0, width: 750 };

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
 * The shortest upright board, an iPhone SE's Safari viewport (375x548) in a window that is no touch screen, so the live
 * game lays its board out upright instead of showing the rotate panel: the side badges, the decisions' two rows and
 * the notices' place over them against the core.
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
 * Wider phones at the floor's height, where the own badge's slot is whole again beside the 36px own tile and the right
 * hand's placement must still keep the band whole.
 */
const WIDER_PHONE_VIEWPORTS: readonly Viewport[] = [680, 700].map((width) => ({
    context: {
        ...deviceOptions("iPhone SE (3rd gen) landscape"),
        screen: { height: 375, width },
        viewport: { height: 375, width },
    },
    desktop: false,
    engine: webkit,
    name: `phone-${width}`,
    ownTileFloor: MIN_TAP,
    portrait: false,
    rotates: false,
    supported: true,
}));
export const WIDER_PHONES: readonly string[] = WIDER_PHONE_VIEWPORTS.map(({ name }) => name);

/**
 * The acceptance viewports, each checked only on the pages that name it (`PageCase.at`): the floor, the mid and the
 * largest desktop, across which the representative worst cases are chosen (`WORST_CASES`), the desktops, laptops,
 * windows, tablet and phones that each guard one path of the layout, the upright phone that gets the rotate panel,
 * and the notched landscape phone (its insets cover the plain one). The notched phone is the agreed capture model,
 * not measured Safari chrome: Playwright's "iPhone 13 landscape" options with the viewport and screen set to the full
 * 844x390 display after them (the device's own 750x342 is Safari's viewport with its chrome), then the insets, so its
 * safe area is 750x369.
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
        rotates: false,
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
        captureModel: { safeArea: NOTCH_SAFE_AREA, viewport: NOTCH_VIEWPORT },
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

export async function emulateInsets(page: Page, insets: Insets | undefined): Promise<void> {
    if (insets === undefined) {
        return;
    }
    const { bottom, left, right } = insets;
    await page.addStyleTag({
        content: `:root { --ronin-safe-left: ${left}px; --ronin-safe-right: ${right}px; --ronin-safe-bottom: ${bottom}px; }`,
    });
}
