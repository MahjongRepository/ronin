import {
    type ClientEffect,
    type GameClientState,
    type PlaySwitch,
    type ScenarioStep,
    type SeatScenario,
    type SeatTranscript,
    parseSeatTranscript,
    scenarioCheckpoint,
    scenarioStateIndex,
    seatScenarioFromTranscript,
} from "@/entities/client";
import { SEAT_TRANSCRIPTS } from "@/fixtures/seat-transcripts";

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

/** The payloads of every message the transcript's seat received, up to and including the one labelled `label`. */
export function receivedThrough(
    transcript: SeatTranscript,
    label: string,
): readonly Readonly<Record<string, unknown>>[] {
    const received = transcript.events.filter((event) => event.kind === "received");
    const last = received.findIndex((event) => event.label === label);
    if (last === -1) {
        throw new Error(`${transcript.scenario} has no received message labelled ${label}`);
    }
    return received.slice(0, last + 1).map((event) => event.payload);
}

/** The client state after the step labelled `label` of the named transcript's scenario, which must run clean. */
export function checkpointState(name: string, label: string): GameClientState {
    return scenarioCheckpoint(loadSeatScenario(name).scenario, label);
}

/** The index of the scenario's step labelled `label`. */
function stepIndex(scenario: SeatScenario, label: string): number {
    return scenarioStateIndex(scenario, label) - 1;
}

/** A hand-written branch: the scenario's steps through the one labelled `label`, then `steps`. */
export function branchAfter(
    scenario: SeatScenario,
    label: string,
    steps: readonly ScenarioStep[],
): SeatScenario {
    const kept = scenario.steps.slice(0, scenarioStateIndex(scenario, label));
    return { ...scenario, steps: [...kept, ...steps] };
}

/** The scenario with `steps` taken right after the step labelled `label`, the rest following as generated. */
export function insertedAfter(
    scenario: SeatScenario,
    label: string,
    steps: readonly ScenarioStep[],
): SeatScenario {
    const at = scenarioStateIndex(scenario, label);
    return { ...scenario, steps: scenario.steps.toSpliced(at, 0, ...steps) };
}

/**
 * The scenario with the player turning the play switches on just before the step labelled `label`, at its time, each
 * press sending nothing.
 */
export function switchedOnBefore(
    scenario: SeatScenario,
    label: string,
    switches: readonly PlaySwitch[],
): SeatScenario {
    const index = stepIndex(scenario, label);
    const { at } = scenario.steps[index].event;
    const presses = switches.map((playSwitch): ScenarioStep => ({
        event: { at, intent: { playSwitch, type: "toggle_switch" }, kind: "intent" },
    }));
    return { ...scenario, steps: scenario.steps.toSpliced(index, 0, ...presses) };
}

/** The scenario with the step labelled `label` expected to describe `effects`, hand-written. */
export function expecting(
    scenario: SeatScenario,
    label: string,
    effects: readonly ClientEffect[],
): SeatScenario {
    const index = stepIndex(scenario, label);
    const steps = scenario.steps.with(index, { ...scenario.steps[index], effects });
    return { ...scenario, steps };
}

/**
 * The send the transcript recorded for the player's answer labelled `answer` expected instead on the step labelled
 * `opens`, the message whose wait a play switch answers at once; the player's press it recorded then sends nothing,
 * the decision being answered. The send comes from what the server accepted, never from the client under test.
 */
export function answeredBySwitch(
    scenario: SeatScenario,
    opens: string,
    answer: string,
): SeatScenario {
    const sent = scenario.steps[stepIndex(scenario, answer)].effects ?? [];
    return expecting(expecting(scenario, opens, sent), answer, []);
}
