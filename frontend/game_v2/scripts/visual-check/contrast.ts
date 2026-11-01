import { type Page } from "playwright";

import { type Box } from "./boxes.ts";
import { type PageReport } from "./model.ts";

/** WCAG's floor for text and marks against what they are painted on (the spec's Automated checks). */
const MIN_CONTRAST = 4.5;
/**
 * The viewports the contrast check runs at: the spec's three, and the narrow desktop, whose faces are the smallest at one
 * device pixel to a CSS pixel; the other desktops paint the same colours at sizes in between.
 */
export const CONTRAST_VIEWPORTS: ReadonlySet<string> = new Set([
    "phone-se-landscape",
    "phone-notch-landscape",
    "desktop-1440",
    "desktop-narrow",
]);
/**
 * The narrowest face, in device pixels, whose red strokes the contrast check fails: below it the sprite's finest red
 * strokes (a pinzu's ring) are narrower than a pixel, so no pixel shows their colour whatever the palette; they are
 * reported in the page's summary instead (the spec: reported, not redrawn). Every face on a phone is wider.
 * The limit is the artwork's: those strokes are about 5 of the face's 300 units (half a device pixel at this bound; the
 * 800x600 window's smallest faces read 3.4-4.4:1), each drawn on a white band about four times as wide (the 1p's ring),
 * so a stroke wide enough for a pixel there (two to three times as wide) would all but cover the band: thickening it is
 * a redraw of the artwork, not a change to the sprite's build.
 */
const MIN_GLYPH_DEVICE_PX = 24;

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
        selector: ".board-river__latest",
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
        hide: [["::after", HIDDEN]],
        name: "badge's turn bar",
        reach: 0,
        selector: ".nameplate--current .nameplate__pill",
    },
    {
        hide: [["", "box-shadow: none !important"]],
        name: "pinned badge's ring",
        reach: 0,
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
    /**
     * Targets the check cannot read honestly: a face whose symbol names no ink, anything under a recolouring filter. A
     * face whose symbol is empty (the blank haku) is drawn blank by design and not collected.
     */
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
            /** Whether `filter` changes an element's own pixels: drop shadows alone are painted beneath them. */
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function recolours(filter: string): boolean {
                return (
                    filter !== "none" &&
                    filter.replaceAll(/drop-shadow\((?:[^()]|\([^()]*\))*\)/g, "").trim() !== ""
                );
            }
            /**
             * The opacity every element from `element` up to `until` (exclusive) applies, or null under a filter that
             * recolours it.
             */
            // eslint-disable-next-line unicorn/consistent-function-scoping -- runs in the page, outside the script's scope
            function opacityOf(element: Element, until: Element | null): number | null {
                let opacity = 1;
                for (
                    let at: Element | null = element;
                    at !== null && at !== until;
                    at = at.parentElement
                ) {
                    const style = getComputedStyle(at);
                    if (recolours(style.filter) || style.mixBlendMode !== "normal") {
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
                    if (symbol !== null && symbol.childElementCount === 0) {
                        return [];
                    }
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
export async function checkContrast(page: Page, report: PageReport): Promise<string> {
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
