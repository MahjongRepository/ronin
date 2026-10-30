const TAIL_CHARS = 4;

/** A player's name split where a narrow column shortens it: the head gives way to an ellipsis, the tail always shows. */
export interface NameParts {
    readonly head: string;
    readonly tail: string;
}

/**
 * Split a name so that its end, which tells AI players apart ("Tsumogiri 1" from "Tsumogiri 2"), survives shortening:
 * the tail is its last word when that word is short, the space before it ending the head, which a shortened head gives
 * up with its last letters; else its last few characters; a short name has no tail.
 */
export function nameParts(name: string): NameParts {
    const chars = [...name];
    if (chars.length <= TAIL_CHARS + 1) {
        return { head: name, tail: "" };
    }
    const space = chars.lastIndexOf(" ");
    const lastWord = chars.length - space - 1;
    const cut = space > 0 && lastWord <= TAIL_CHARS ? space + 1 : chars.length - TAIL_CHARS;
    return { head: chars.slice(0, cut).join(""), tail: chars.slice(cut).join("") };
}
