import { type Page } from "playwright";

import { type BoardCase, type PageCase, SELECTOR_TIMEOUT_MS } from "./model.ts";

/** What a selector's first match holds: its text, whitespace collapsed, and whether a player sees it. */
interface ReadText {
    readonly text: string;
    readonly seen: boolean;
}

/** Read a selector's first match once it is attached, waiting first, where `drawn`, for it to show (it may not). */
async function readText(page: Page, selector: string, drawn: boolean): Promise<ReadText | null> {
    const element = page.locator(selector).first();
    const found = await element
        .waitFor({ state: "attached", timeout: SELECTOR_TIMEOUT_MS })
        .then(() => true)
        .catch(() => false);
    if (!found) {
        return null;
    }
    if (drawn) {
        await element.waitFor({ state: "visible", timeout: SELECTOR_TIMEOUT_MS }).catch(() => {});
    }
    return element.evaluate((node) => {
        const rect = node.getBoundingClientRect();
        return {
            seen:
                node.checkVisibility({ opacityProperty: true, visibilityProperty: true }) &&
                rect.width >= 1 &&
                rect.height >= 1,
            text: node.textContent.replaceAll(/\s+/gu, " ").trim(),
        };
    });
}

/**
 * Require each selector's first match to show its text to a player (displayed, opaque, visible, of some size, its
 * whitespace collapsed), so a page proves its state, not only that an element of its kind is there: throws, failing
 * the page, on the first that reads otherwise or is not seen.
 */
export async function expectTexts(
    page: Page,
    texts: Readonly<Record<string, string>>,
): Promise<void> {
    for (const [selector, text] of Object.entries(texts)) {
        const read = await readText(page, selector, true);
        if (read?.text !== text || !read.seen) {
            throw new Error(
                `${selector} ${read === null ? "is missing" : `reads ${JSON.stringify(read.text)}${read.seen ? "" : ", unseen"}`}, not "${text}" shown`,
            );
        }
    }
}

/**
 * Require each selector's first match to hold its text whether or not it is drawn: for words that are deliberately
 * not on screen (a live region's announcement, a word a short board leaves out), never for what a player must see.
 */
export async function expectAnnounced(
    page: Page,
    texts: Readonly<Record<string, string>>,
): Promise<void> {
    for (const [selector, text] of Object.entries(texts)) {
        const read = await readText(page, selector, false);
        if (read?.text !== text) {
            throw new Error(
                `${selector} ${read === null ? "is missing" : `holds ${JSON.stringify(read.text)}`}, not "${text}"`,
            );
        }
    }
}

/** The board's tiles, but a decision control's preview faces, which a paired control may shed (the spec's Decisions). */
export const BOARD_VISIBLE = [
    ".game-board .board-table .tile:not(.decision-controls__tiles .tile)",
    ".board-local .board-area--bottom-hand .tile",
    ".board-table .nameplate:not(.nameplate--bottom)",
];

export function boardCase(name: string, query: string, extra: readonly string[] = []): BoardCase {
    return {
        kind: "board",
        name,
        path: `/play/storybook/board${query}`,
        required: { visible: [...BOARD_VISIBLE, ...extra] },
    };
}

/** A decisions story: the live board at a checkpoint of a generated seat transcript. */
export function decisionCase(story: string, extra: readonly string[]): BoardCase {
    return {
        kind: "board",
        name: `decisions-${story.replaceAll("_", "-")}`,
        path: `/play/storybook/decisions?state=${story}`,
        required: { visible: [...BOARD_VISIBLE, ...extra] },
    };
}

export const ACTION = ".board-actions .decision-controls__action";

export function documentCase(name: string, path: string, content: string): PageCase {
    return { kind: "document", name, path, required: { visible: [content] } };
}
