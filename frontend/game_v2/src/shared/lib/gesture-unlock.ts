/** The events a first user gesture arrives as: a press, a touch's end (iOS Safari's activation), a key. */
const GESTURE_EVENTS = ["pointerdown", "touchend", "keydown"] as const;

/**
 * Call `unlock` synchronously inside every gesture's handler on `target` until it resolves true, then stop listening,
 * so a gesture the browser does not count as activation (a touch's pointerdown) leaves the next one to try; a failure
 * is reported on the console and ends the tries. Returns the listeners' removal.
 */
export function unlockOnGesture(target: EventTarget, unlock: () => Promise<boolean>): () => void {
    const listeners = new AbortController();
    function onGesture(): void {
        unlock().then(
            (unlocked) => {
                if (unlocked) {
                    listeners.abort();
                }
            },
            (error: unknown) => {
                listeners.abort();
                console.error("The audio could not be unlocked:", error);
            },
        );
    }
    for (const type of GESTURE_EVENTS) {
        target.addEventListener(type, onGesture, {
            capture: true,
            passive: true,
            signal: listeners.signal,
        });
    }
    return () => listeners.abort();
}
