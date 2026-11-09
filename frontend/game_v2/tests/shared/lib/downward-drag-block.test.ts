import { afterEach, describe, expect, test } from "vitest";

import { blockDownwardDrags } from "@/shared/lib";

const START_Y = 100;
const BELOW_START_Y = 130;
const ABOVE_START_Y = 70;

let stop: (() => void) | null = null;

function touchEvent(type: string, clientYs: readonly number[]): Event {
    return Object.assign(new Event(type, { bubbles: true, cancelable: true }), {
        touches: clientYs.map((clientY) => ({ clientY })),
    });
}

function dragIsRefused(target: Element, moveYs: readonly number[]): boolean {
    target.dispatchEvent(touchEvent("touchstart", [START_Y]));
    const move = touchEvent("touchmove", moveYs);
    target.dispatchEvent(move);
    return move.defaultPrevented;
}

function scrollingBox(scrollTop: number): HTMLElement {
    const box = document.createElement("div");
    box.style.overflowY = "auto";
    Object.defineProperties(box, {
        clientHeight: { value: 100 },
        scrollHeight: { value: 400 },
        scrollTop: { value: scrollTop },
    });
    document.body.append(box);
    return box;
}

describe("blockDownwardDrags", () => {
    afterEach(() => {
        stop?.();
        document.body.replaceChildren();
    });

    test("refuses a drag down the page and leaves one up, the swipe that hides the bars", () => {
        stop = blockDownwardDrags(document);

        expect(dragIsRefused(document.body, [BELOW_START_Y])).toBe(true);
        expect(dragIsRefused(document.body, [ABOVE_START_Y])).toBe(false);
    });

    test("leaves a drag down a box scrolled down, and refuses one at the box's top", () => {
        stop = blockDownwardDrags(document);

        expect(dragIsRefused(scrollingBox(40), [BELOW_START_Y])).toBe(false);
        expect(dragIsRefused(scrollingBox(0), [BELOW_START_Y])).toBe(true);
    });

    test("leaves a two-finger gesture alone", () => {
        stop = blockDownwardDrags(document);

        expect(dragIsRefused(document.body, [BELOW_START_Y, ABOVE_START_Y])).toBe(false);
    });

    test("refuses nothing once stopped", () => {
        blockDownwardDrags(document)();

        expect(dragIsRefused(document.body, [BELOW_START_Y])).toBe(false);
    });
});
