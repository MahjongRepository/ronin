import { type Page } from "playwright";

const FRAME_WAIT_MS = 50;
const FRAME_TRIES = 100;
const SETTLE_MS = 300;
const NUDGE_EVERY = 10;

/** Paint a 1px element for two frames, so the compositor sends a frame. */
async function nudge(page: Page): Promise<void> {
    await page.evaluate(() => {
        const mark = document.createElement("div");
        mark.style.cssText =
            "position:fixed;left:0;top:0;width:1px;height:1px;opacity:0.01;pointer-events:none";
        document.documentElement.append(mark);
        requestAnimationFrame(() => requestAnimationFrame(() => mark.remove()));
    });
}

/** Nudge until the screencast delivers a frame past its `seen`th, painted after this call. */
async function awaitFrameAfter(page: Page, count: () => number, seen: number): Promise<void> {
    await nudge(page);
    for (let tries = 0; tries < FRAME_TRIES && count() <= seen; tries += 1) {
        if (tries % NUDGE_EVERY === NUDGE_EVERY - 1) {
            await nudge(page);
        }
        await page.waitForTimeout(FRAME_WAIT_MS);
    }
}

/**
 * The viewport as WebKit's compositor shows it, a screencast frame (JPEG): Playwright's `page.screenshot()` in WebKit on
 * Linux paints in software and flattens a CSS perspective (no divide, Playwright #21620, WebKit bug 68276), so a shot of
 * the tilted table must come from the compositor. A frame arrives only when something paints, so a 1px element
 * nudges one; it keeps nudging for a settling while, then returns a frame painted after it, never one the screencast
 * delivers late from before the page's last change. `oversample` asks for a frame that many times the device's pixels, which a reader scales back down: a
 * JPEG halves its colour's resolution, which would soften a thin red stroke's colour.
 */
export async function compositorShot(page: Page, oversample = 1): Promise<Buffer> {
    const viewport = page.viewportSize();
    if (viewport === null) {
        throw new Error("a compositor shot needs a viewport");
    }
    const scale = oversample * (await page.evaluate(() => window.devicePixelRatio));
    let latest: Buffer | null = null;
    let frames = 0;
    let started = false;
    await page.screencast.start({
        onFrame: (frame) => {
            if (started) {
                latest = frame.data;
                frames += 1;
            }
        },
        quality: 100,
        size: {
            height: Math.round(viewport.height * scale),
            width: Math.round(viewport.width * scale),
        },
    });
    started = true;
    await awaitFrameAfter(page, () => frames, 0);
    for (let waited = 0; waited < SETTLE_MS; waited += FRAME_WAIT_MS) {
        await nudge(page);
        await page.waitForTimeout(FRAME_WAIT_MS);
    }
    await awaitFrameAfter(page, () => frames, frames);
    await page.screencast.stop();
    if (latest === null) {
        throw new Error("no screencast frame arrived");
    }
    return latest;
}
