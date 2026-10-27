import { describe, expect, it } from "vitest";

import { parseReplay } from "../replay/load.js";
import { MalformedReplayError, POSITION, toReplay } from "../replay/paipu.js";
import FULL_GAME from "./fixtures/replays/full_game.txt?raw";
import KANS from "./fixtures/replays/kans.txt?raw";
import RIICHI from "./fixtures/replays/riichi.txt?raw";
import TRUNCATED_MID_ROUND from "./fixtures/replays/truncated_mid_round.txt?raw";

function convert(text) {
    return toReplay(parseReplay(text));
}

function firstRound(text) {
    return convert(text).rounds[0];
}

function kindOf(message) {
    return Object.keys(message)[0];
}

/** Each position of a round as the messages it adds to the log, with its callouts. */
function stepsOf(round) {
    return round.positions.map((position, index) => {
        const start = index === 0 ? 0 : round.positions[index - 1].end;
        const messages = round.log.slice(start, position.end);
        return { kind: position.kind, kinds: messages.map(kindOf), messages, say: position.say };
    });
}

/** The truncated fixture cut before the rinshan draw that follows its closed kan's dora reveal. */
function endingOnTheDoraReveal(text) {
    return text.trimEnd().split("\n").slice(0, -1).join("\n");
}

function insertLine(text, number, line) {
    const lines = text.split("\n");
    return [...lines.slice(0, number - 1), line, ...lines.slice(number - 1)].join("\n");
}

describe("toReplay", () => {
    it("seats each hand from the round's dealer", () => {
        const { rounds } = convert(FULL_GAME);

        expect(rounds[0].log[0].qipai.shoupai.slice(0, 2)).toEqual([
            "m4m6m7m7p1p9s5s5s6s9z3z3z7",
            "m5m8m9p4p7p8p9s2s4s8s8s9z4",
        ]);
        expect(rounds[1].log[0].qipai.jushu).toBe(1);
    });

    it("deals all four hands with red fives", () => {
        const { shoupai } = firstRound(RIICHI).log[0].qipai;

        expect(shoupai.map((hand) => hand.match(/\d/g).length)).toEqual([13, 13, 13, 13]);
        expect(shoupai[0]).toContain("m0");
        expect(shoupai[1]).toContain("p0");
    });

    it("draws after a kan from the dead wall", () => {
        const draws = firstRound(KANS)
            .log.map(kindOf)
            .filter((kind) => kind === "zimo" || kind === "gangzimo");

        expect(draws).toEqual([
            "zimo",
            "gangzimo",
            "zimo",
            "zimo",
            "zimo",
            "zimo",
            "zimo",
            "gangzimo",
            "zimo",
            "zimo",
            "gangzimo",
        ]);
    });

    it("builds an added kan from the caller's pon", () => {
        const { log } = firstRound(KANS);

        expect(log).toContainEqual({ fulou: { l: 1, m: "z555=" } });
        expect(log).toContainEqual({ gang: { l: 1, m: "z555=5" } });
    });

    it("marks tsumogiri and riichi discards", () => {
        const steps = stepsOf(firstRound(RIICHI));
        const riichiDiscards = steps.filter((step) => step.say.some((s) => s.name === "lizhi"));

        expect(riichiDiscards.map((step) => [step.messages, step.say])).toEqual([
            [[{ dapai: { l: 1, p: "z7_*" } }], [{ name: "lizhi", l: 1 }]],
            [[{ dapai: { l: 3, p: "z4*" } }], [{ name: "lizhi", l: 3 }]],
        ]);
        expect(steps.flatMap((step) => step.messages)).toContainEqual({
            dapai: { l: 1, p: "m9_" },
        });
    });

    it("folds a dora reveal into the next visible position", () => {
        const steps = stepsOf(firstRound(KANS));
        const holding = (kind, m) => steps.findIndex((step) => step.messages[0][kind]?.m === m);

        const openKan = holding("fulou", "z6666=");
        expect(steps[openKan].say).toEqual([{ name: "gang", l: 2 }]);
        expect(steps.slice(openKan, openKan + 4).map((step) => step.kinds)).toEqual([
            ["fulou"],
            ["gangzimo"],
            ["dapai"],
            ["kaigang", "zimo"],
        ]);

        const closedKan = holding("gang", "s1111");
        expect(steps.slice(closedKan).map((step) => step.kinds)).toEqual([
            ["gang"],
            ["kaigang", "gangzimo"],
        ]);
    });

    it("ends a truncated round on its trailing silent records", () => {
        const round = firstRound(endingOnTheDoraReveal(TRUNCATED_MID_ROUND));
        const last = stepsOf(round).at(-1);

        expect(last.kind).toBe(POSITION.SILENT);
        expect(last.messages).toEqual([{ kaigang: { baopai: "s9" } }]);
        expect(round.outcome).toBeNull();
    });

    it("folds silent records before a round end into the round's last position", () => {
        const round = firstRound(insertLine(KANS, 31, '{"t": 6, "ti": 108}'));
        const last = stepsOf(round).at(-1);

        expect(last.kind).toBe(POSITION.DRAW);
        expect(last.kinds).toEqual(["kaigang", "gangzimo", "kaigang"]);
    });

    it("names the file line of a record it cannot read", () => {
        const broken = insertLine(KANS, 6, '{"t": 99}');

        expect(() => convert(broken)).toThrow(
            expect.objectContaining({ name: MalformedReplayError.name, line: 6 }),
        );
    });
});
