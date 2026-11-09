const SCROLLING_OVERFLOW = new Set(["auto", "scroll"]);

function startsInScrolledBox(target: EventTarget | null): boolean {
    let box = target instanceof Element ? target : null;
    while (box !== null && box !== document.body && box !== document.documentElement) {
        const scrolls = SCROLLING_OVERFLOW.has(getComputedStyle(box).overflowY);
        if (scrolls && box.scrollHeight > box.clientHeight) {
            return box.scrollTop > 0;
        }
        box = box.parentElement;
    }
    return false;
}

/**
 * Refuse every one-finger drag downward from its first move, but one that scrolls a box already scrolled down, and
 * return how to stop. It cannot wait for the page's top: iOS makes a drag uncancelable once it has started scrolling.
 */
export function blockDownwardDrags(page: Document): () => void {
    const listeners = new AbortController();
    let startY = 0;

    function onTouchStart(event: TouchEvent): void {
        startY = event.touches[0]?.clientY ?? startY;
    }

    function onTouchMove(event: TouchEvent): void {
        const [touch] = event.touches;
        if (event.touches.length !== 1 || touch === undefined || !event.cancelable) {
            return;
        }
        if (touch.clientY > startY && !startsInScrolledBox(event.target)) {
            event.preventDefault();
        }
    }

    page.addEventListener("touchstart", onTouchStart, { passive: true, signal: listeners.signal });
    page.addEventListener("touchmove", onTouchMove, { passive: false, signal: listeners.signal });
    return () => listeners.abort();
}
