const TAIL_CHARS = 4;

/** A player's name split where a narrow column shortens it: the head gives way to an ellipsis, the tail always shows. */
export interface NameParts {
    readonly head: string;
    readonly tail: string;
}

/**
 * Split a name so that its last few characters, which tell AI players apart ("ai-tsumogiri-1" from "ai-tsumogiri-2"),
 * survive shortening; a short name has no tail.
 */
export function nameParts(name: string): NameParts {
    const chars = [...name];
    if (chars.length <= TAIL_CHARS + 1) {
        return { head: name, tail: "" };
    }
    const cut = chars.length - TAIL_CHARS;
    return { head: chars.slice(0, cut).join(""), tail: chars.slice(cut).join("") };
}
