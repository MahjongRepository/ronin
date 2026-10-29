import {
    type SeatScenario,
    type SeatTranscript,
    parseSeatTranscript,
    seatScenarioFromTranscript,
} from "@/entities/client";

const TRANSCRIPT_FILES: Record<string, unknown> = import.meta.glob("./seat-scenarios/*.json", {
    eager: true,
    import: "default",
});

/** The generated seat transcripts by file name without its extension (`call_prompt_seat_1`), unparsed. */
export const SEAT_TRANSCRIPTS: ReadonlyMap<string, unknown> = new Map(
    Object.entries(TRANSCRIPT_FILES).map(([path, raw]) => [
        path.slice("./seat-scenarios/".length, -".json".length),
        raw,
    ]),
);

/** A transcript with the seat scenario it describes. */
export interface GeneratedScenario {
    readonly transcript: SeatTranscript;
    readonly scenario: SeatScenario;
}

/** The seat scenario a transcript describes, run from a handoff of its own game. */
export function scenarioFromTranscript(transcript: SeatTranscript): GeneratedScenario {
    const handoff = {
        gameTicket: `ticket-${transcript.seat}`,
        wsUrl: `ws://game/ws/${transcript.gameId}`,
    };
    return { scenario: seatScenarioFromTranscript(transcript, handoff), transcript };
}

export function loadSeatScenario(name: string): GeneratedScenario {
    const raw = SEAT_TRANSCRIPTS.get(name);
    if (raw === undefined) {
        throw new Error(`No seat transcript named ${name}`);
    }
    const [error, transcript] = parseSeatTranscript(raw);
    if (error) {
        throw new Error(`${name}: ${error.message}`);
    }
    return scenarioFromTranscript(transcript);
}

/** The payload of the transcript's received message labelled `label`. */
export function receivedPayload(
    transcript: SeatTranscript,
    label: string,
): Readonly<Record<string, unknown>> {
    const event = transcript.events.find((candidate) => candidate.label === label);
    if (event?.kind !== "received") {
        throw new Error(`${transcript.scenario} has no received message labelled ${label}`);
    }
    return event.payload;
}
