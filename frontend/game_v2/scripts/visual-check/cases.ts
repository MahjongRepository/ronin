import { type BoardCase, type PageCase } from "./model.ts";

/** The board's tiles, but a decision control's preview faces, which a paired control may shed (the spec's Decisions). */
export const BOARD_VISIBLE = [
    ".game-board .board-table .tile:not(.decision-controls__tiles .tile)",
    ".board-local .board-area--bottom-hand .tile",
    ".board-table .nameplate",
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
