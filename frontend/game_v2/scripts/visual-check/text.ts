import { type Page } from "playwright";

import { type PageCase, type PageReport, SELECTOR_TIMEOUT_MS } from "./model.ts";

/** The smallest computed font size of the board's centre text, dora label and nameplates, in CSS pixels. */
export const MIN_TEXT_PX = 10;

/** The app's one face, which every page must have loaded before it is checked and shot. */
const FONT_FAMILY = "Inter";
export const FONT_EXTENSION = ".woff2";

/**
 * Fail a page whose face did not load (its FontFace `loaded` and `document.fonts.check` true, since `check` is also true
 * for a family no face declares), or, with the face blocked, whose FontFace did not fail once asked to load (WebKit
 * leaves a face whose preload failed `unloaded` until then): the checks that follow then measure the fallback stack.
 */
export async function checkFont(page: Page, pageCase: PageCase, report: PageReport): Promise<void> {
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
export function isBlockedFont(pageCase: PageCase, url: string): boolean {
    return pageCase.fontBlocked === true && url.endsWith(FONT_EXTENSION);
}
