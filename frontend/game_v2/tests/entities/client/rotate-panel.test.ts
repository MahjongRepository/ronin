import { render } from "lit-html";
import { describe, expect, it } from "vitest";

import { loadSeatScenario } from "#tests/fixtures/seat-transcripts";
import {
    type DecisionCountdown,
    type LeaveControls,
    NO_PLAY_UI,
    RotatePanel,
    type RotatePanelView,
    playDisplay,
    runSeatScenario,
    scenarioStateIndex,
    timelineStates,
} from "@/entities/client";
import { CONNECTION_STATUS } from "@/shared/protocol";

const LEAVE: LeaveControls = { command: { kind: "ask_leave" }, confirming: false };

function running(secondsLeft: number): DecisionCountdown {
    return { clock: null, kind: "running", move: "turn", secondsLeft };
}

function inBank(secondsLeft: number): DecisionCountdown {
    const clock = { bankSeconds: secondsLeft, baseSeconds: 0, inBank: true };
    return { clock, kind: "running", move: "turn", secondsLeft };
}

function renderPanel(view: RotatePanelView): HTMLElement {
    const host = document.createElement("div");
    render(
        RotatePanel(view, () => {}),
        host,
    );
    return host;
}

describe("RotatePanel", () => {
    it("shows the player-facing session status and the open prompt's seconds left", () => {
        const { scenario } = loadSeatScenario("call_prompt_seat_1");
        const run = runSeatScenario(scenario);
        const prompt = timelineStates(run.timeline)[scenarioStateIndex(scenario, "prompt")];

        const host = renderPanel(playDisplay(prompt, NO_PLAY_UI));

        expect(host.querySelector("[role=status]")?.textContent).toBe("Connected");
        expect(host.querySelector(".rotate-panel__seconds")?.textContent).toBe("25");
    });

    it("names a chankan prompt as the chance to rob the kan, not a call on the last discard", () => {
        const { scenario } = loadSeatScenario("chankan_robbed_seat_3");
        const run = runSeatScenario(scenario);
        const prompt = timelineStates(run.timeline)[scenarioStateIndex(scenario, "chankan prompt")];

        const host = renderPanel(playDisplay(prompt, NO_PLAY_UI));

        expect(host.querySelector(".rotate-panel__decision p")?.textContent).toMatch(
            /^You can rob the kan\./,
        );
    });

    it("names a round result awaiting the player's OK, with the seconds to the round advance", () => {
        const { scenario } = loadSeatScenario("own_turn_seat_1");
        const run = runSeatScenario(scenario);
        const roundEnd = timelineStates(run.timeline)[scenarioStateIndex(scenario, "round end")];

        const host = renderPanel(playDisplay(roundEnd, NO_PLAY_UI));

        expect(host.querySelector(".rotate-panel__decision p")?.textContent).toMatch(
            /^The round's result awaits your OK\./,
        );
        expect(host.querySelector(".rotate-panel__seconds")?.textContent).toBe("10");
    });

    it("announces the countdown only when its turn enters the bank, crosses 10 and 5 seconds and expires", () => {
        const status = { label: "Connected", tone: CONNECTION_STATUS.CONNECTED, word: "" };
        const countdowns = [running(12), inBank(12), ...[10, 6, 5, 1].map(running), inBank(8)];
        const expired: DecisionCountdown = { kind: "expired", move: "turn" };

        const announced = [...countdowns, expired].map(
            (countdown) =>
                renderPanel({
                    failure: null,
                    leave: LEAVE,
                    owedCountdown: countdown,
                    status,
                }).querySelector("[aria-live=polite]")?.textContent,
        );

        expect(announced).toEqual([
            "",
            "Your time bank is running",
            "10 seconds or less left",
            "10 seconds or less left",
            "5 seconds or less left",
            "5 seconds or less left",
            "10 seconds or less left",
            "Time is up",
        ]);
    });
});
