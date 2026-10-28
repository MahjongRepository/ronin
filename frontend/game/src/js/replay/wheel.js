import { isModified } from "./keys.js";

/** A wheel delta in pixels, whatever unit the device reports it in (pixels, lines or pages). */
const WHEEL_UNIT_PX = Object.freeze({
    [WheelEvent.DOM_DELTA_PIXEL]: 1,
    [WheelEvent.DOM_DELTA_LINE]: 40,
    [WheelEvent.DOM_DELTA_PAGE]: 800,
});

/**
 * A gesture in pixels (a trackpad, a smooth wheel) steps once it has scrolled WHEEL_START_PX, so a graze steps nothing;
 * a notch reported in lines or pages, or one that far at once, steps at once.
 */
export const WHEEL_START_PX = 30;

/** Scrolling this far within one gesture steps again, at most every WHEEL_STEP_MS: a notch is a step, a swipe a few. */
export const WHEEL_STEP_PX = 100;
export const WHEEL_STEP_MS = 150;

/** A wheel quiet this long ends its gesture: the next one may step at once, even from a result. */
export const WHEEL_GESTURE_GAP_MS = 200;

/** Overflow this small is a text box a fraction of a pixel past the box's edge, rounded up, not content to scroll to. */
const SCROLL_SLACK_PX = 3;

/** Whether `element`, up to the stage, is a box that scrolls its own content, such as tall final standings. */
function isInScrollingBox(element, stage) {
    for (let node = element; node !== null && node !== stage; node = node.parentElement) {
        const { overflowY } = window.getComputedStyle(node);
        if (
            (overflowY === "auto" || overflowY === "scroll") &&
            node.scrollHeight - node.clientHeight > SCROLL_SLACK_PX
        ) {
            return true;
        }
    }
    return false;
}

/**
 * The wheel over the board steps: down is Next, up is Back. A gesture steps once it has scrolled WHEEL_START_PX (a
 * notch at once); one that goes on (a spun wheel, a trackpad swipe and its momentum) steps once per WHEEL_STEP_PX, at
 * most every WHEEL_STEP_MS, and stops at a result or the standings until the wheel rests. A pinch (Ctrl), a sideways
 * scroll, and the wheel over a box that scrolls are left to the browser; the help and the round list lie outside the
 * board, so their scrolling never steps. The event's `deltaMode` is read before its deltas: Firefox reports a notch
 * in lines only then, and in pixels otherwise.
 */
export function bindWheel(viewer, stage) {
    const stepper = new WheelStepper(viewer);
    stage.on("wheel.replay-wheel", (event) => {
        const native = event.originalEvent;
        const { deltaMode } = native;
        const { deltaX, deltaY } = native;
        if (isModified(native) || Math.abs(deltaX) >= Math.abs(deltaY)) {
            return;
        }
        if (isInScrollingBox(native.target, stage[0])) {
            return;
        }
        event.preventDefault();
        stepper.scroll(
            deltaY * WHEEL_UNIT_PX[deltaMode],
            deltaMode !== WheelEvent.DOM_DELTA_PIXEL,
            performance.now(),
        );
    });
}

/** One wheel gesture at a time: the scroll it has travelled since its last step, and whether a result stopped it. */
class WheelStepper {
    #lastEventAt = -Infinity;
    #lastStepAt = -Infinity;
    #direction = 0;
    #travelled = 0;
    #stepped = false;
    #stopped = false;

    constructor(viewer) {
        this.viewer = viewer;
    }

    /**
     * A scroll by `delta` pixels (down positive) at `now`, `notched` in lines or pages, which is a step's distance
     * whatever its size; turning back starts a gesture.
     */
    scroll(delta, notched, now) {
        const direction = Math.sign(delta);
        if (now - this.#lastEventAt >= WHEEL_GESTURE_GAP_MS || direction !== this.#direction) {
            this.#travelled = 0;
            this.#stepped = false;
            this.#stopped = false;
        }
        this.#lastEventAt = now;
        this.#direction = direction;
        if (this.#stopped) {
            return;
        }
        if (!this.#stepped) {
            this.#travelled += Math.abs(delta);
            if (notched || this.#travelled >= WHEEL_START_PX) {
                this.#step(now);
            }
            return;
        }
        if (now - this.#lastStepAt < WHEEL_STEP_MS) {
            return;
        }
        this.#travelled += notched ? WHEEL_STEP_PX : Math.abs(delta);
        if (this.#travelled >= WHEEL_STEP_PX) {
            this.#step(now);
        }
    }

    #step(now) {
        this.#lastStepAt = now;
        this.#travelled = 0;
        this.#stepped = true;
        if (this.#direction > 0) {
            this.viewer.next();
        } else {
            this.viewer.back();
        }
        this.#stopped = this.viewer.isAtStop();
    }
}
