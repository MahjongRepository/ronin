import { type Page } from "playwright";

import { type Box } from "./boxes.ts";
import { type PageMeasure, type PageReport, SELECTOR_TIMEOUT_MS } from "./model.ts";

export function measurePage(page: Page): Promise<PageMeasure> {
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

export async function checkVisible(
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

export function viewportBox(page: Page): Promise<Box> {
    return page.evaluate(() => ({
        height: window.innerHeight,
        left: window.scrollX,
        top: window.scrollY,
        width: window.innerWidth,
    }));
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
export async function checkTileFaces(page: Page, report: PageReport): Promise<void> {
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
