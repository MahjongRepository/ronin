const OCCUPANCY = {
    ALREADY_IN_GAME: "already_in_game",
    ALREADY_IN_QUEUE: "already_in_queue",
    ALREADY_IN_ROOM: "already_in_room",
    MATCH_STARTING: "match_starting",
    REPLACED_BY_NEW_CONNECTION: "replaced_by_new_connection",
} as const;

type OccupancyCode = (typeof OCCUPANCY)[keyof typeof OCCUPANCY];

type OccupancyText = Readonly<Partial<Record<OccupancyCode, string>>>;

const OCCUPANCY_TEXT: Readonly<Record<OccupancyCode, string>> = {
    [OCCUPANCY.ALREADY_IN_GAME]: "You are already playing a game. Finish it first.",
    [OCCUPANCY.ALREADY_IN_QUEUE]: "You are searching for a match. Cancel the search first.",
    [OCCUPANCY.ALREADY_IN_ROOM]: "You are already seated at a table. Leave it first.",
    [OCCUPANCY.MATCH_STARTING]: "Your match is starting. Try again in a moment to join its game.",
    [OCCUPANCY.REPLACED_BY_NEW_CONNECTION]:
        "This page is open in another tab or window and continues there. You can close this one.",
};

function isOccupancyCode(code: unknown): code is OccupancyCode {
    return typeof code === "string" && Object.hasOwn(OCCUPANCY_TEXT, code);
}

function describeOccupancyError(code: unknown, pageText: OccupancyText = {}): string | null {
    if (!isOccupancyCode(code)) {
        return null;
    }
    return pageText[code] ?? OCCUPANCY_TEXT[code];
}

export { OCCUPANCY, OCCUPANCY_TEXT, describeOccupancyError, isOccupancyCode };
export type { OccupancyCode, OccupancyText };
