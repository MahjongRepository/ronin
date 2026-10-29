const TRANSCRIPT_FILES: Record<string, unknown> = import.meta.glob("./seat-scenarios/*.json", {
    eager: true,
    import: "default",
});

/**
 * Every generated seat transcript by file name without its extension (`call_prompt_seat_1`), unparsed: data for the
 * tests, which parse each at its boundary. The storybook imports only the transcripts its stories run, one by one,
 * so its chunk carries no other.
 */
export const SEAT_TRANSCRIPTS: ReadonlyMap<string, unknown> = new Map(
    Object.entries(TRANSCRIPT_FILES).map(([path, raw]) => [
        path.slice("./seat-scenarios/".length, -".json".length),
        raw,
    ]),
);
