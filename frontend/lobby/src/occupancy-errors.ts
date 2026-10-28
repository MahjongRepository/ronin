import { type MessageKey, t } from "@/i18n";

const OCCUPANCY = {
    ALREADY_IN_GAME: "already_in_game",
    ALREADY_IN_QUEUE: "already_in_queue",
    ALREADY_IN_ROOM: "already_in_room",
    MATCH_STARTING: "match_starting",
    REPLACED_BY_NEW_CONNECTION: "replaced_by_new_connection",
} as const;

type OccupancyCode = (typeof OCCUPANCY)[keyof typeof OCCUPANCY];

type OccupancyText = Readonly<Partial<Record<OccupancyCode, MessageKey>>>;

const OCCUPANCY_TEXT: Readonly<Record<OccupancyCode, MessageKey>> = {
    [OCCUPANCY.ALREADY_IN_GAME]: "occupancy.already_in_game",
    [OCCUPANCY.ALREADY_IN_QUEUE]: "occupancy.already_in_queue",
    [OCCUPANCY.ALREADY_IN_ROOM]: "occupancy.already_in_room",
    [OCCUPANCY.MATCH_STARTING]: "occupancy.match_starting",
    [OCCUPANCY.REPLACED_BY_NEW_CONNECTION]: "occupancy.replaced_by_new_connection",
};

function isOccupancyCode(code: unknown): code is OccupancyCode {
    return typeof code === "string" && Object.hasOwn(OCCUPANCY_TEXT, code);
}

function describeOccupancyError(code: unknown, pageText: OccupancyText = {}): string | null {
    if (!isOccupancyCode(code)) {
        return null;
    }
    return t(pageText[code] ?? OCCUPANCY_TEXT[code]);
}

export { OCCUPANCY, OCCUPANCY_TEXT, describeOccupancyError, isOccupancyCode };
export type { OccupancyCode, OccupancyText };
