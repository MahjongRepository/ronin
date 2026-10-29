const TRANSCRIPT_FILES: Record<string, unknown> = import.meta.glob("./seat-scenarios/*.json", {
    eager: true,
    import: "default",
});

/**
 * The generated seat transcripts by file name without its extension (`call_prompt_seat_1`), unparsed: data for the
 * tests and the storybook, which parse each at its boundary. Only storybook views import this module, so the
 * transcripts ship in the storybook's own chunk, never the game's.
 */
export const SEAT_TRANSCRIPTS: ReadonlyMap<string, unknown> = new Map(
    Object.entries(TRANSCRIPT_FILES).map(([path, raw]) => [
        path.slice("./seat-scenarios/".length, -".json".length),
        raw,
    ]),
);
