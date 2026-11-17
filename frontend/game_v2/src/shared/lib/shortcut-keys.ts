/** The shortcut convention a keyboard follows: Apple's, ⌘ where others take Ctrl, or the others'. */
export type ShortcutKeys = "apple" | "other";

/**
 * The shortcut convention of the platform a user agent names: Apple's for macOS, iOS and iPadOS, whose iPad names
 * itself a Mac.
 */
export function shortcutKeysOf(userAgent: string): ShortcutKeys {
    return /Macintosh|iPhone|iPad|iPod/.test(userAgent) ? "apple" : "other";
}
