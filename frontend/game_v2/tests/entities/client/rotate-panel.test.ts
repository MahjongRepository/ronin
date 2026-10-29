import { render } from "lit-html";
import { describe, expect, it } from "vitest";

import { loadSeatScenario } from "#tests/fixtures/seat-transcripts";
import {
    type DecisionCountdown,
    RotatePanel,
    type RotatePanelProps,
    rotatePanelProps,
    runSeatScenario,
    scenarioStateIndex,
    timelineStates,
} from "@/entities/client";
import { CONNECTION_STATUS } from "@/shared/protocol";

function running(secondsLeft: number): DecisionCountdown {
    return { kind: "running", move: "turn", secondsLeft };
}

function renderPanel(props: RotatePanelProps): HTMLElement {
    const host = document.createElement("div");
    render(RotatePanel(props), host);
    return host;
}

describe("RotatePanel", () => {
    it("shows the player-facing session status and the open prompt's seconds left", () => {
        const { scenario } = loadSeatScenario("call_prompt_seat_1");
        const run = runSeatScenario(scenario);
        const prompt = timelineStates(run.timeline)[scenarioStateIndex(scenario, "prompt")];

        const host = renderPanel(rotatePanelProps(prompt, () => {}));

        expect(host.querySelector("[role=status]")?.textContent).toBe("Connected");
        expect(host.querySelector(".rotate-panel__seconds")?.textContent).toBe("5");
    });

    it("names a chankan prompt as the chance to rob the kan, not a call on the last discard", () => {
        const { scenario } = loadSeatScenario("chankan_robbed_seat_3");
        const run = runSeatScenario(scenario);
        const prompt = timelineStates(run.timeline)[scenarioStateIndex(scenario, "chankan prompt")];

        const host = renderPanel(rotatePanelProps(prompt, () => {}));

        expect(host.querySelector(".rotate-panel__decision p")?.textContent).toMatch(
            /^You can rob the kan\./,
        );
    });

    it("names a round result awaiting the player's OK, with the seconds to the round advance", () => {
        const { scenario } = loadSeatScenario("own_turn_seat_1");
        const run = runSeatScenario(scenario);
        const roundEnd = timelineStates(run.timeline)[scenarioStateIndex(scenario, "round end")];

        const host = renderPanel(rotatePanelProps(roundEnd, () => {}));

        expect(host.querySelector(".rotate-panel__decision p")?.textContent).toMatch(
            /^The round's result awaits your OK\./,
        );
        expect(host.querySelector(".rotate-panel__seconds")?.textContent).toBe("10");
    });

    it("announces the countdown only when it crosses 10 and 5 seconds and when it expires", () => {
        const status = { label: "Connected", tone: CONNECTION_STATUS.CONNECTED };
        const countdowns = [12, 10, 6, 5, 1].map(running);
        const expired: DecisionCountdown = { kind: "expired", move: "turn" };

        const announced = [...countdowns, expired].map(
            (countdown) =>
                renderPanel({ countdown, onLeave: () => {}, status }).querySelector(
                    "[aria-live=polite]",
                )?.textContent,
        );

        expect(announced).toEqual([
            "",
            "10 seconds or less left",
            "10 seconds or less left",
            "5 seconds or less left",
            "5 seconds or less left",
            "Time is up",
        ]);
    });
});
