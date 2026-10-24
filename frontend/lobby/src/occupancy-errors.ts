const OCCUPANCY_ERROR_TEXT: Readonly<Record<string, string>> = {
    already_in_game: "You are already playing a game. Finish it before joining another.",
    already_in_queue: "You are already searching for a match. Leave the queue first.",
    already_in_room: "You are already seated in a room. Leave it first.",
};

export function describeOccupancyError(code: unknown): string | null {
    if (typeof code !== "string" || !Object.hasOwn(OCCUPANCY_ERROR_TEXT, code)) {
        return null;
    }
    return OCCUPANCY_ERROR_TEXT[code];
}
