import { type SessionStatusDisplay } from "@/entities/session";
import { t } from "@/shared/i18n";
import { CONNECTION_STATUS, type ConnectionStatus } from "@/shared/protocol";

/** The socket's round trip and whether it is slow enough for the settings cog to warn of it. */
export interface RoundTripDisplay {
    readonly ms: number;
    readonly slow: boolean;
}

/** The settings cog's mark: a dot in its tone, and the word its label reads out. */
export interface CogAlert {
    readonly tone: ConnectionStatus | "slow";
    readonly word: string;
}

/** What the page shows of its connection: the session's status, the round trip while connected, and the cog's mark. */
export interface ConnectionDisplay {
    readonly status: SessionStatusDisplay;
    readonly roundTrip: RoundTripDisplay | null;
    readonly cogAlert: CogAlert | null;
}

/** From it on the player feels the lag on every own discard, so the settings cog warns of it. */
export const POOR_ROUND_TRIP_MS = 400;

/**
 * The connection's display from the session's status and the socket's round trip: the round trip only while the
 * status reads connected, and the cog marked by the status while it has a word to say (a drop, an end), else by a slow
 * round trip.
 */
export function connectionDisplay(
    status: SessionStatusDisplay,
    roundTripMs: number | null,
): ConnectionDisplay {
    const roundTrip =
        status.tone === CONNECTION_STATUS.CONNECTED && roundTripMs !== null
            ? { ms: roundTripMs, slow: roundTripMs >= POOR_ROUND_TRIP_MS }
            : null;
    return { cogAlert: cogAlert(status, roundTrip), roundTrip, status };
}

function cogAlert(
    status: SessionStatusDisplay,
    roundTrip: RoundTripDisplay | null,
): CogAlert | null {
    if (status.word !== "") {
        return { tone: status.tone, word: status.word };
    }
    return roundTrip?.slow === true ? { tone: "slow", word: t("game.status.word.slow") } : null;
}
