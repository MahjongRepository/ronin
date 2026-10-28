import { describe, expect, it } from "vitest";

import Majiang from "../../vendor/majiang-core/index.js";
import { parseReplay } from "../replay/load.js";
import { MalformedReplayError, NOTE, POSITION, toReplay } from "../replay/paipu.js";
import { OUTCOME } from "../replay/round-end.js";
import wire from "../ronin/wire.js";
import { firstLineOf } from "./replay-edits.js";
import AI_DEALER_ABSENT from "./fixtures/replays/ai_dealer_absent.txt?raw";
import AI_REPLACEMENTS from "./fixtures/replays/ai_replacements.txt?raw";
import CHANKAN_ADDED from "./fixtures/replays/chankan_added.txt?raw";
import CHANKAN_AI_REPLACEMENT from "./fixtures/replays/chankan_ai_replacement.txt?raw";
import CHANKAN_CLOSED_KOKUSHI from "./fixtures/replays/chankan_closed_kokushi.txt?raw";
import DOUBLE_RON from "./fixtures/replays/double_ron.txt?raw";
import DOUBLE_RON_HEAD_BUMP from "./fixtures/replays/double_ron_head_bump.txt?raw";
import EXHAUSTIVE_TENPAI from "./fixtures/replays/exhaustive_tenpai.txt?raw";
import FOUR_KANS from "./fixtures/replays/four_kans.txt?raw";
import FOUR_RIICHI from "./fixtures/replays/four_riichi.txt?raw";
import FOUR_WINDS_RIICHI from "./fixtures/replays/four_winds_riichi.txt?raw";
import FULL_GAME from "./fixtures/replays/full_game.txt?raw";
import KANS from "./fixtures/replays/kans.txt?raw";
import KYUUSHU from "./fixtures/replays/kyuushu.txt?raw";
import NAGASHI from "./fixtures/replays/nagashi.txt?raw";
import PAO from "./fixtures/replays/pao.txt?raw";
import RIICHI from "./fixtures/replays/riichi.txt?raw";
import RON_RIICHI_DISCARD from "./fixtures/replays/ron_riichi_discard.txt?raw";
import TRIPLE_RON from "./fixtures/replays/triple_ron.txt?raw";
import TRUNCATED_AFTER_ROUND from "./fixtures/replays/truncated_after_round.txt?raw";
import TRUNCATED_MID_ROUND from "./fixtures/replays/truncated_mid_round.txt?raw";

const FIXTURES = import.meta.glob("./fixtures/replays/*.txt", {
    query: "?raw",
    import: "default",
    eager: true,
});

function convert(text) {
    return toReplay(parseReplay(text));
}

function firstRound(text) {
    return convert(text).rounds[0];
}

function kindOf(message) {
    return Object.keys(message)[0];
}

/** Each position of a round as the messages of its range, with its callouts. */
function stepsOf(round) {
    return round.positions.map((position) => {
        const messages = round.log.slice(position.start, position.end);
        return {
            kind: position.kind,
            kinds: messages.map(kindOf),
            messages,
            say: position.say,
            position,
        };
    });
}

/** The truncated fixture cut before the rinshan draw that follows its closed kan's dora reveal. */
function endingOnTheDoraReveal(text) {
    return text.trimEnd().split("\n").slice(0, -1).join("\n");
}

/** The replay with its first round end's ron made liable on its own discarder, who pays the whole ron either way. */
function withLiableDiscarder(text) {
    const lines = text.split("\n");
    const index = firstLineOf(lines, wire.E.ROUND_END);
    const roundEnd = JSON.parse(lines[index]);
    lines[index] = JSON.stringify({ ...roundEnd, ps: roundEnd.ls });
    return lines.join("\n");
}

/** The position of a round's result, with the messages of its range. */
function resultOf(round) {
    return stepsOf(round).find((step) => step.kind === POSITION.RESULT);
}

function insertLine(text, number, line) {
    const lines = text.split("\n");
    return [...lines.slice(0, number - 1), line, ...lines.slice(number - 1)].join("\n");
}

/** The seats an AI player holds for their human at a position. */
function replacedSeats(position) {
    return position.replaced.flatMap((replaced, seat) => (replaced ? [seat] : []));
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

    it("flags all last: the fourth round of the game's last wind and of its sudden-death extension", () => {
        const flagged = (text) =>
            convert(text)
                .rounds.map((round, index) => (round.final ? index : null))
                .filter((index) => index !== null);

        expect(flagged(FULL_GAME)).toEqual([7, 11]);
        expect(flagged(FULL_GAME.replace('"gt": 0', '"gt": 1'))).toEqual([3, 7]);
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
        expect(steps.slice(closedKan, closedKan + 2).map((step) => step.kinds)).toEqual([
            ["gang"],
            ["kaigang", "gangzimo"],
        ]);
    });

    it("notes each AI replacement and human return on the next visible position, and holds the seats AI plays at each", () => {
        const controlled = (round) =>
            stepsOf(round).map(({ kind, position }) => [
                kind,
                replacedSeats(position),
                position.notes,
            ]);
        const [first, second] = convert(AI_REPLACEMENTS).rounds;
        const { LEFT, ABSENT } = wire.SEAT_CONTROL_REASON;

        expect(controlled(first)).toEqual([
            [POSITION.DEAL, [3], [{ kind: NOTE.AI_REPLACEMENT, seat: 3, reason: ABSENT }]],
            [POSITION.DRAW, [3], undefined],
            [POSITION.DISCARD, [3], undefined],
            [POSITION.DRAW, [3], undefined],
            [POSITION.DISCARD, [3], undefined],
            [POSITION.DRAW, [3], undefined],
            [POSITION.DISCARD, [2, 3], [{ kind: NOTE.AI_REPLACEMENT, seat: 2, reason: LEFT }]],
            [POSITION.RESULT, [2, 3], undefined],
        ]);
        expect(controlled(second)).toEqual([
            [
                POSITION.DEAL,
                [0, 2],
                [
                    { kind: NOTE.HUMAN_RETURN, seat: 3 },
                    { kind: NOTE.AI_REPLACEMENT, seat: 0, reason: LEFT },
                ],
            ],
            [POSITION.DRAW, [0, 2], undefined],
            [POSITION.DISCARD, [0], [{ kind: NOTE.HUMAN_RETURN, seat: 2 }]],
            ...[2, 3, 0].flatMap(() => [
                [POSITION.DRAW, [0], undefined],
                [POSITION.DISCARD, [0], undefined],
            ]),
        ]);
    });

    it("notes seats absent at the deal on it, and never an AI player's seat from the game's start", () => {
        const { rounds } = convert(AI_DEALER_ABSENT);
        const { ABSENT } = wire.SEAT_CONTROL_REASON;
        const positions = rounds.flatMap((round) => round.positions);

        expect(rounds[0].positions[0].notes).toEqual([
            { kind: NOTE.AI_REPLACEMENT, seat: 1, reason: ABSENT },
            { kind: NOTE.AI_REPLACEMENT, seat: 3, reason: ABSENT },
        ]);
        expect(
            stepsOf(rounds[0])
                .slice(1, 3)
                .map((step) => step.messages),
        ).toEqual([[{ zimo: { l: 0, p: "z5" } }], [{ dapai: { l: 0, p: "z5_" } }]]);
        expect(new Set(positions.map((position) => replacedSeats(position).join()))).toEqual(
            new Set(["1,3"]),
        );
    });

    it("ends a truncated round on its trailing silent records", () => {
        const round = firstRound(endingOnTheDoraReveal(TRUNCATED_MID_ROUND));
        const last = stepsOf(round).at(-1);

        expect(last.kind).toBe(POSITION.SILENT);
        expect(last.messages).toEqual([{ kaigang: { baopai: "s9" } }]);
        expect(round.outcome).toBeNull();
    });

    it("folds silent records before a round end into its result", () => {
        const last = stepsOf(firstRound(FOUR_KANS)).at(-1);

        expect(last.kind).toBe(POSITION.RESULT);
        expect(last.kinds).toEqual(["kaigang", "pingju"]);
    });

    it("names the file line of a record it cannot read", () => {
        const unreadable = [
            '{"t": 99}',
            '{"t": 101, "s": 4, "ai": 1, "r": 0}',
            '{"t": 101, "s": 0, "ai": 1, "r": 2}',
            '{"t": 101, "s": 0, "ai": 2}',
            '{"t": 101, "s": 0, "ai": 0}',
            '{"t": 101, "s": 1, "ai": 1, "r": 1}',
        ];
        const leavingAiSeatFromTheStart = '{"t": 101, "s": 0, "ai": 1, "r": 0}';
        const absentAfterTheFirstRound = firstLineOf(FULL_GAME.split("\n"), wire.E.ROUND_END) + 2;

        for (const record of unreadable) {
            expect(() => convert(insertLine(KANS, 6, record))).toThrow(
                expect.objectContaining({ name: MalformedReplayError.name, line: 6 }),
            );
        }
        expect(() => convert(insertLine(AI_DEALER_ABSENT, 7, leavingAiSeatFromTheStart))).toThrow(
            expect.objectContaining({ name: MalformedReplayError.name, line: 7 }),
        );
        expect(() =>
            convert(
                insertLine(
                    FULL_GAME,
                    absentAfterTheFirstRound,
                    '{"t": 101, "s": 1, "ai": 1, "r": 1}',
                ),
            ),
        ).toThrow(
            expect.objectContaining({
                name: MalformedReplayError.name,
                line: absentAfterTheFirstRound,
            }),
        );
    });
});

function play(model, message) {
    const [kind, body] = Object.entries(message)[0];
    model[kind === "gangzimo" ? "zimo" : kind](body);
}

function scoresBySeat(wireScores) {
    return [0, 1, 2, 3].map((seat) => wireScores[seat] * wire.SCORE_DIV);
}

function dealtScores(qijia, round) {
    const board = new Majiang.Board({ qijia });
    board.qipai(round.log[0].qipai);
    return board.defen;
}

/** full_game.txt with a riichi stick on the table from its first deal on, which the winner of the game takes. */
function fullGameEndingWithAStickOnTheTable() {
    const { lines, lineNumbers } = parseReplay(FULL_GAME);
    const stick = 10;
    const edited = lines.map((line) => {
        if (line.t === wire.E.ROUND_STARTED) {
            return { ...line, r: 1 };
        }
        if (line.t !== wire.E.GAME_END) {
            return line;
        }
        const st = line.st.map((standing) =>
            standing.s === line.ws ? { ...standing, sc: standing.sc + stick } : standing,
        );
        return { ...line, st, lb: stick };
    });
    return { lines: edited, lineNumbers };
}

const SETTLED_GAMES = [
    ...Object.entries(FIXTURES).map(([path, text]) => [path, parseReplay(text)]),
    ["full_game.txt ending with a stick on the table", fullGameEndingWithAStickOnTheTable()],
];

describe("toReplay round ends", () => {
    it("builds wins with their ura dora, discarder, riichi mark and liable seat", () => {
        const tsumo = firstRound(RIICHI);
        expect(resultOf(tsumo).messages[0].hule).toMatchObject({
            l: 1,
            baojia: null,
            shoupai: expect.stringMatching(/\*$/),
            fubaopai: ["p8"],
        });
        expect(resultOf(tsumo).say).toEqual([{ name: "zimo", l: 1 }]);
        expect(tsumo.outcome).toMatchObject({
            kind: OUTCOME.TSUMO,
            winners: [{ seat: 1, points: 8000, liable: null, paid: [4000, 0, 2000, 2000] }],
            loser: null,
        });

        const ron = firstRound(RON_RIICHI_DISCARD);
        expect(resultOf(ron).messages[0].hule).toMatchObject({
            l: 1,
            baojia: 2,
            shoupai: expect.stringMatching(/\*$/),
            fubaopai: ["z6"],
        });
        expect(resultOf(ron).say).toEqual([{ name: "rong", l: 1 }]);
        expect(ron.outcome).toMatchObject({ kind: OUTCOME.RON, loser: 2 });

        expect(resultOf(firstRound(PAO)).messages[0].hule).toMatchObject({
            l: 1,
            baojia: null,
            pao: 0,
            headBumped: [],
            page: null,
        });
        const liableDiscarder = firstRound(withLiableDiscarder(RON_RIICHI_DISCARD));
        expect(resultOf(liableDiscarder).messages[0].hule.pao).toBeNull();
        expect(liableDiscarder.outcome.winners[0].liable).toBeNull();
    });

    it("builds a rinshan kaihou tsumo with the kan among its melds", () => {
        const rinshan = resultOf(firstRound(KANS)).messages[0].hule;

        expect(rinshan).toMatchObject({
            l: 3,
            baojia: null,
            shoupai: "m2m3m4m9p0p6p7s6s7s8m9,s1111",
        });
        expect(rinshan.hupai.map((yaku) => yaku.name)).toContain("嶺上開花");
    });

    it("shows a robbed kan as declared before the ron", () => {
        const [added, closed] = [CHANKAN_ADDED, CHANKAN_CLOSED_KOKUSHI].map((text) => {
            const steps = stepsOf(firstRound(text));
            const result = steps.findIndex((step) => step.kind === POSITION.RESULT);
            return steps
                .slice(result - 1, result + 1)
                .map(({ kind, messages, say }) => ({ kind, messages, say }));
        });
        const robbedAs = (m) => [
            {
                kind: POSITION.CALL,
                messages: [{ gang: { l: 1, m } }],
                say: [{ name: "gang", l: 1 }],
            },
            {
                kind: POSITION.RESULT,
                messages: [{ hule: expect.objectContaining({ l: 2, baojia: 1 }) }],
                say: [{ name: "rong", l: 2 }],
            },
        ];

        expect(added).toEqual(robbedAs("p666-6"));
        expect(closed).toEqual(robbedAs("m9999"));

        const steps = stepsOf(firstRound(CHANKAN_AI_REPLACEMENT));
        expect(
            steps
                .slice(-2)
                .map(({ kind, position }) => [kind, position.replaced[3], position.notes]),
        ).toEqual([
            [POSITION.CALL, false, undefined],
            [
                POSITION.RESULT,
                true,
                [
                    {
                        kind: NOTE.AI_REPLACEMENT,
                        seat: 3,
                        reason: wire.SEAT_CONTROL_REASON.LEFT,
                    },
                ],
            ],
        ]);
    });

    it("ends a double ron's position at its first win", () => {
        const round = firstRound(DOUBLE_RON);
        const result = resultOf(round);

        expect(result.kinds).toEqual(["hule"]);
        expect(result.messages[0].hule.l).toBe(1);
        expect(round.log.slice(result.position.end)).toEqual([
            { hule: expect.objectContaining({ l: 2, baojia: 0 }) },
        ]);
        expect(result.position.wins).toBe(2);
        expect(result.say).toEqual([
            { name: "rong", l: 1 },
            { name: "rong", l: 2 },
        ]);
        expect(round.outcome.kind).toBe(OUTCOME.DOUBLE_RON);

        const headBumped = firstRound(DOUBLE_RON_HEAD_BUMP);
        const wins = headBumped.log.filter((message) => "hule" in message);
        expect(wins.map(({ hule }) => [hule.l, hule.headBumped, hule.page])).toEqual([
            [1, [3], { number: 1, count: 2 }],
            [2, [3], { number: 2, count: 2 }],
        ]);
    });

    it("names each abortive draw and reveals the kyuushu declarer's hand", () => {
        const draws = [KYUUSHU, FOUR_RIICHI, FOUR_WINDS_RIICHI, FOUR_KANS, TRIPLE_RON].map((text) =>
            resultOf(firstRound(text)),
        );
        const pingju = (step) => step.messages.at(-1).pingju;

        expect(draws.map((step) => pingju(step).name)).toEqual([
            "九種九牌",
            "四家立直",
            "四風連打",
            "四開槓",
            "三家和了",
        ]);
        const [kyuushu, , , , tripleRon] = draws;
        expect(pingju(kyuushu)).toMatchObject({
            shoupai: [null, "m1m2m3m4m9p1p9s1s9z1z2z3z4z5", null, null],
            players: [1],
        });
        expect(tripleRon.say).toEqual([1, 2, 3].map((l) => ({ name: "rong", l })));
    });

    it("opens the tenpai hands of an exhaustive draw", () => {
        const round = firstRound(EXHAUSTIVE_TENPAI);
        const { pingju } = resultOf(round).messages[0];

        expect(pingju.shoupai.map((hand) => hand !== null)).toEqual([false, true, true, false]);
        expect(pingju.tenpai).toEqual([false, true, true, false]);
        expect(round.outcome).toMatchObject({ kind: OUTCOME.EXHAUSTIVE, tenpai: [1, 2] });
    });

    it("calls a draw's round end without score changes damaged, naming its line", () => {
        const lines = EXHAUSTIVE_TENPAI.split("\n");
        const index = firstLineOf(lines, wire.E.ROUND_END);
        const roundEnd = JSON.parse(lines[index]);
        delete roundEnd.sch;
        lines[index] = JSON.stringify(roundEnd);

        expect(() => convert(lines.join("\n"))).toThrow(
            expect.objectContaining({ name: MalformedReplayError.name, line: index + 1 }),
        );
    });

    it("names the nagashi mangan player and opens the tenpai hands", () => {
        const round = firstRound(NAGASHI);

        expect(resultOf(round).messages[0].pingju).toMatchObject({
            shoupai: [null, null, null, "m2m3m4m5m6m7s2s3s4s5s6s7z5"],
            tenpai: [false, false, false, true],
            players: [1],
        });
        expect(round.outcome).toMatchObject({
            kind: OUTCOME.NAGASHI,
            name: "流し満貫",
            players: [1],
        });
    });

    it("closes a completed game with its standings after every win of the last result", () => {
        const game = convert(DOUBLE_RON_HEAD_BUMP);
        const { log, positions } = game.rounds.at(-1);

        expect(positions.slice(-2)).toEqual([
            expect.objectContaining({ kind: POSITION.RESULT, start: 3, end: 4, wins: 2 }),
            expect.objectContaining({ kind: POSITION.SUMMARY, start: 5, end: 5 }),
        ]);
        expect(log).toHaveLength(5);
        expect(game.standings).toMatchObject({
            defen: [-7000, 41000, 41000, 25000],
            rank: [4, 1, 2, 3],
            point: [-57, 51, 21, -15],
        });
    });

    it("leaves a truncated game without standings", () => {
        const game = convert(TRUNCATED_AFTER_ROUND);

        expect(game.standings).toBeNull();
        expect(game.rounds.at(-1).positions.at(-1).kind).toBe(POSITION.RESULT);
    });

    it.each(SETTLED_GAMES)(
        "puts each win on its winner and leaves the model's scores equal to each next deal: %s",
        (_, parsed) => {
            const { lines } = parsed;
            const replay = toReplay(parsed);
            const roundEnds = lines.filter((line) => line.t === wire.E.ROUND_END);

            roundEnds.forEach((roundEnd, index) => {
                const round = replay.rounds[index];
                const next = replay.rounds[index + 1];
                const model = new Majiang.Board({ qijia: replay.qijia });
                model.qipai(round.log[0].qipai);
                const result = round.positions.find(
                    (position) => position.kind === POSITION.RESULT,
                );
                round.log.slice(1, result.end).forEach((message) => play(model, message));
                expect(model.defen, `round ${index}: scores at the result`).toEqual(
                    scoresBySeat(roundEnd.scs),
                );
                const wins = round.log.filter((message) => "hule" in message);
                const winners = roundEnd.wn ?? (roundEnd.ws === undefined ? [] : [roundEnd]);
                expect(
                    wins.map(({ hule }) => model.player_id[hule.l]),
                    `round ${index}: winners' seats`,
                ).toEqual(winners.map((winner) => winner.ws));

                round.log.slice(result.end).forEach((message) => play(model, message));
                model.last();
                expect(model.defen, `round ${index}: settled scores`).toEqual(
                    [0, 1, 2, 3].map(
                        (seat) => (roundEnd.scs[seat] + roundEnd.sch[seat]) * wire.SCORE_DIV,
                    ),
                );
                if (next !== undefined) {
                    expect(model.defen, `round ${index}: next deal`).toEqual(
                        dealtScores(replay.qijia, next),
                    );
                    expect(model.lizhibang, `round ${index}: sticks carried`).toBe(
                        next.log[0].qipai.lizhibang,
                    );
                } else if (replay.standings !== null) {
                    const { defen, gongtuo } = replay.standings;
                    const sticksTaken = gongtuo.reduce((sum, points) => sum + points, 0);
                    expect(model.defen, "final standings").toEqual(
                        defen.map((score, seat) => score - gongtuo[seat]),
                    );
                    expect(sticksTaken, "sticks left to the winner").toBe(model.lizhibang * 1000);
                }
            });
        },
    );
});
