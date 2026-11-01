/**
 * The controls under `root` that a component rendered with `key` among its `data-focus-key` keys, in document order.
 * A key derives from the state the component draws, so the focus follows the state instead of the markup's classes or
 * ARIA. A key is a plain word (letters, digits, `-`, `_`, `:`), never quoted; a control holds one or more, space
 * separated (its own and a group's, `focusKeys`).
 */
export function keyedControls(root: ParentNode, key: string): HTMLElement[] {
    return [...root.querySelectorAll<HTMLElement>(`[data-focus-key~="${key}"]`)];
}

/** Focus the first control under `root` holding `key` (`keyedControls`); a key no control holds focuses nothing. */
export function focusByKey(root: ParentNode, key: string, options?: FocusOptions): void {
    root.querySelector<HTMLElement>(`[data-focus-key~="${key}"]`)?.focus(options);
}

/** The `data-focus-key` value of a control holding `keys`, absent ones skipped; null when it holds none. */
export function focusKeys(...keys: readonly (string | null | undefined)[]): string | null {
    const held = keys.filter((key) => key !== null && key !== undefined && key !== "");
    return held.length === 0 ? null : held.join(" ");
}
