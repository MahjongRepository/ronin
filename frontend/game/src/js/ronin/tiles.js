"use strict";

/* id = t34*4 + copy; red fives are copy 0 */
const RED_IDS = { 16: 'm0', 52: 'p0', 88: 's0' };
const SUITS   = 'mps';

function tileToStr(id) {
    return RED_IDS[id] || typeToStr(Math.floor(id / 4));
}

function typeToStr(t34) {
    if (t34 < 27) return SUITS[Math.floor(t34 / 9)] + (t34 % 9 + 1);
    return 'z' + (t34 - 26);
}

function strTo34(p) {
    const s = p[0], n = p[1];
    if (n == '0') return { m: 4, p: 13, s: 22 }[s];
    if (s == 'z') return 26 + +n;
    return SUITS.indexOf(s) * 9 + (+n - 1);
}

function strToBaseId(p) { return strTo34(p) * 4; }

function redIdOf(p) {
    if (p[1] == '0') return strToBaseId(p);
    return undefined;
}

function idsOf(p, hand) {
    const red = redIdOf(p);
    const t34 = strTo34(p);
    const out = [];
    for (const id of hand) {
        if (red != null) {
            if (id == red) out.push(id);
            continue;
        }
        if (Math.floor(id / 4) == t34 && RED_IDS[id] == null) out.push(id);
    }
    return out;
}

function idsToStrs(ids) {
    return ids.slice().sort((a, b) => a - b).map(tileToStr);
}

function handStr(ids) {
    return idsToStrs(ids).join('');
}

export { tileToStr, typeToStr, strTo34, strToBaseId, redIdOf, idsOf, idsToStrs, handStr };
