import { ROUND_RESULT_TYPE } from "@/shared/protocol";

export type WirePayload = Record<string, unknown>;

export const WIRE_DRAW: WirePayload = { d: 0, t: 1 };

export const WIRE_GAME_STARTED: WirePayload = {
    dd: [
        [1, 1],
        [1, 1],
    ],
    dl: 0,
    gid: "g1",
    gt: 0,
    p: [{ ai: 0, nm: "P0", s: 0 }],
    t: 8,
};

export const WIRE_GAME_RECONNECTED: WirePayload = {
    cp: 0,
    dc: [1, 2],
    dd: [
        [1, 2],
        [3, 4],
    ],
    di: [0],
    dl: 0,
    f: false,
    gid: "g1",
    h: 0,
    mt: [0, 1, 2],
    n: 1,
    p: [
        { ai: 0, nm: "P1", s: 0 },
        { ai: 0, nm: "P2", s: 1 },
        { ai: 1, nm: "B1", s: 2 },
        { ai: 1, nm: "B2", s: 3 },
    ],
    pst: [],
    r: 0,
    rh: [],
    s: 0,
    tm: { bk: 20, gp: 3, mb: 60, md: 10, ra: 15, rb: 5, tb: 5 },
    tr: 70,
    type: "game_reconnected",
    w: 0,
    wi: 7,
};

export const WIRE_ROUND_STARTED: WirePayload = {
    cp: 0,
    di: [0],
    dl: 0,
    h: 0,
    n: 1,
    p: [{ s: 0, sc: 250 }],
    r: 0,
    t: 9,
    w: 0,
};

export const WIRE_GAME_END: WirePayload = {
    lb: 0,
    nr: 1,
    st: [{ fs: 0, s: 0, sc: 250 }],
    t: 10,
    ws: 0,
};

/** A tsumo round end; a wait id opens the round advance, and the game's last round end carries none. */
export function wireRoundEnd(waitId: number | null): WirePayload {
    const roundEnd: WirePayload = {
        ct: [0, 4, 8],
        hr: { fu: 30, han: 3, pt: 39, yk: [{ han: 1, yi: 0 }] },
        ml: [],
        rc: 0,
        rt: ROUND_RESULT_TYPE.TSUMO,
        sch: { "0": 30, "1": -10, "2": -10, "3": -10 },
        scs: { "0": 280, "1": 240, "2": 240, "3": 240 },
        t: 4,
        ws: 0,
        wt: 12,
    };
    return waitId === null ? roundEnd : { ...roundEnd, wi: waitId };
}

export function wireSessionError(code: string): WirePayload {
    return { code, message: `server said ${code}`, type: "session_error" };
}
