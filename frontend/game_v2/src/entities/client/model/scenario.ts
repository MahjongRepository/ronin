import { type GameSessionData } from "@/shared/session";

import { startGameClient } from "./dispatch";
import { type ClientTimeline, buildClientTimeline } from "./timeline";
import { type ClientEffect, type ClientEvent, type GameClientState } from "./types";

/** The client events a seat's scenario takes: everything but a replay line, which only a replay file holds. */
export type ScenarioEvent = Exclude<ClientEvent, { kind: "replay_line" }>;

/**
 * One step of a scenario: a client event, with the effects stepping it must describe, exactly and in order. An
 * omitted `effects` means none, so every send a scenario causes is one it names. `label` names the step so its
 * state can be found.
 */
export interface ScenarioStep {
    readonly event: ScenarioEvent;
    readonly effects?: readonly ClientEffect[];
    readonly label?: string;
}

/**
 * A scripted run of the game client for one seat: the lobby's handoff it starts from, then the ordered client
 * events it takes (server messages as raw wire payloads, transport events, local intents, time advances as ticks),
 * all plain data. What the client sends is asserted on the steps, never fed in: the effects of the start and of
 * each step.
 */
export interface SeatScenario {
    readonly name: string;
    readonly gameId: string;
    readonly seat: number;
    readonly handoff: GameSessionData;
    readonly startAt: number;
    readonly startEffects?: readonly ClientEffect[];
    readonly steps: readonly ScenarioStep[];
}

/** Where a run parted from its scenario: a step's effects, or the seat the client ended up seeing from. */
export type ScenarioMismatch =
    | {
          readonly kind: "effects";
          readonly step: number | "start";
          readonly label: string | null;
          readonly expected: readonly ClientEffect[];
          readonly actual: readonly ClientEffect[];
      }
    | { readonly kind: "seat"; readonly expected: number; readonly actual: number | null };

export interface ScenarioRun {
    readonly timeline: ClientTimeline;
    readonly mismatches: readonly ScenarioMismatch[];
}

/** JSON with every object's keys sorted, so two effects compare by content, whatever their keys' order. */
function canonicalJson(value: unknown): string {
    return JSON.stringify(value, (_key, inner: unknown) =>
        typeof inner === "object" && inner !== null && !Array.isArray(inner)
            ? Object.fromEntries(
                  Object.entries(inner).toSorted(([left], [right]) => left.localeCompare(right)),
              )
            : inner,
    );
}

type EffectsCheck = Omit<Extract<ScenarioMismatch, { kind: "effects" }>, "kind">;

function effectsMismatch(check: EffectsCheck): ScenarioMismatch[] {
    if (canonicalJson(check.expected) === canonicalJson(check.actual)) {
        return [];
    }
    return [{ ...check, kind: "effects" }];
}

function seatMismatch(scenario: SeatScenario, last: GameClientState): ScenarioMismatch[] {
    const actual = last.viewerSeat;
    return actual === scenario.seat ? [] : [{ actual, expected: scenario.seat, kind: "seat" }];
}

/**
 * Run a scenario through the dispatcher: the timeline of its states, and every place the effects it described or
 * the seat it saw from parted from the scenario. A payload that does not parse is reported as an effect, so it is
 * a mismatch too. Nothing runs IO; the effects are compared, never executed.
 */
export function runSeatScenario(scenario: SeatScenario): ScenarioRun {
    const start = startGameClient(scenario.gameId, scenario.handoff, scenario.startAt);
    const timeline = buildClientTimeline(
        start.state,
        scenario.steps.map((step) => step.event),
    );
    const startMismatch = effectsMismatch({
        actual: start.effects,
        expected: scenario.startEffects ?? [],
        label: null,
        step: "start",
    });
    const stepMismatches = timeline.entries.flatMap((entry, index) => {
        const { effects = [], label = null } = scenario.steps[index];
        return effectsMismatch({ actual: entry.effects, expected: effects, label, step: index });
    });
    const last = timeline.entries.at(-1)?.state ?? start.state;
    return {
        mismatches: [...startMismatch, ...stepMismatches, ...seatMismatch(scenario, last)],
        timeline,
    };
}

/** The index into the run's timeline states of the state after the step labelled `label`. */
export function scenarioStateIndex(scenario: SeatScenario, label: string): number {
    const index = scenario.steps.findIndex((step) => step.label === label);
    if (index === -1) {
        throw new Error(`Scenario ${scenario.name} has no step labelled ${label}`);
    }
    return index + 1;
}
