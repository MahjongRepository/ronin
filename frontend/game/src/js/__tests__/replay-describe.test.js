import { describe, expect, it } from "vitest";

import { outcomeParts } from "../replay/describe.js";
import { parseReplay } from "../replay/load.js";
import { toReplay } from "../replay/paipu.js";
import wire from "../ronin/wire.js";
import { firstLineOf } from "./replay-edits.js";
import DOUBLE_RON_ON_HONBA from "./fixtures/replays/double_ron_on_honba.txt?raw";
import EAGER_GAME from "./fixtures/replays/eager_game.txt?raw";
import KYUUSHU from "./fixtures/replays/kyuushu.txt?raw";
import NAGASHI from "./fixtures/replays/nagashi.txt?raw";
import PAO from "./fixtures/replays/pao.txt?raw";
import TRUNCATED_MID_ROUND from "./fixtures/replays/truncated_mid_round.txt?raw";

/** Each round's outcome as the round list writes it, its Japanese parts as plain text. */
function outcomes(text) {
    const replay = toReplay(parseReplay(text));
    return replay.rounds.map((round) =>
        outcomeParts(replay, round)
            .map((part) => (typeof part === "string" ? part : part.ja))
            .join(""),
    );
}

/** The replay with its first round played on two honba: each payer of its tsumo pays 200 more. */
function withFirstTsumoOnTwoHonba(text) {
    const lines = text.split("\n");
    const start = firstLineOf(lines, wire.E.ROUND_STARTED);
    const end = firstLineOf(lines, wire.E.ROUND_END);
    const roundStart = JSON.parse(lines[start]);
    const roundEnd = JSON.parse(lines[end]);
    roundStart.h = 2;
    for (const seat of Object.keys(roundEnd.sch)) {
        roundEnd.sch[seat] += seat === String(roundEnd.ws) ? 6 : -2;
    }
    lines[start] = JSON.stringify(roundStart);
    lines[end] = JSON.stringify(roundEnd);
    return lines.join("\n");
}

describe("outcomeParts", () => {
    it("tells a tsumo by its points and each payer's share, the honba paid on top apart", () => {
        expect(outcomes(EAGER_GAME).slice(0, 2)).toEqual([
            "Tsumo: Diana 8,000 (2,000/4,000)",
            "Tsumo: Bob 12,000 (4,000 all)",
        ]);
        expect(outcomes(withFirstTsumoOnTwoHonba(EAGER_GAME))[0]).toBe(
            "Tsumo: Diana 8,000 (2,000/4,000) (+600 honba)",
        );
    });

    it("tells a ron by its winner and discarder, and a double ron by its discarder first", () => {
        expect(outcomes(EAGER_GAME)[2]).toBe("Ron: Charlie from Alice 1,300 (+300 honba)");
        expect(outcomes(DOUBLE_RON_ON_HONBA)[2]).toBe(
            "Double ron from Bob: Alice 1,600, Diana 1,600 (+1,200 honba)",
        );
    });

    it("names who pays a pao tsumo in place of its split", () => {
        expect(outcomes(PAO)).toEqual(["Tsumo: Alice 32,000 (pao: Diana pays)"]);
    });

    it("names a draw and the seats it names before its Japanese name", () => {
        expect(outcomes(EAGER_GAME)[3]).toBe("Exhaustive draw: tenpai Alice, Bob (荒牌平局)");
        expect(outcomes(NAGASHI)).toEqual(["Nagashi mangan: Alice (流し満貫)"]);
        expect(outcomes(KYUUSHU)).toEqual(["Nine terminals: Alice (九種九牌)"]);
    });

    it("says where the replay cuts a round off", () => {
        expect(outcomes(TRUNCATED_MID_ROUND)).toEqual(["Cut off: the server stopped the game"]);
    });
});
