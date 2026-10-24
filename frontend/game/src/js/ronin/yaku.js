"use strict";

const YAKU_NAMES = {
    0:  '門前清自摸和', 1: '立直',       2: 'オープン立直',
    3:  '一発',         4: '槍槓',       5: '嶺上開花',
    6:  '海底摸月',     7: '河底撈魚',   8: 'ダブル立直',
    9:  'ダブルオープン立直', 10: '流し満貫', 11: '人和',
    12: '平和',         13: '断幺九',     14: '一盃口',
    15: '翻牌 白',      16: '翻牌 發',    17: '翻牌 中',
    18: '自風 東',      19: '自風 南',    20: '自風 西',
    21: '自風 北',      22: '場風 東',    23: '場風 南',
    24: '場風 西',      25: '場風 北',
    26: '三色同順',     27: '一気通貫',   28: '混全帯幺九',
    29: '混老頭',       30: '対々和',     31: '三暗刻',
    32: '三槓子',       33: '三色同刻',   34: '七対子',
    35: '小三元',       36: '混一色',     37: '純全帯幺九',
    38: '二盃口',       39: '清一色',
    100: '国士無双',    101: '九蓮宝燈',  102: '四暗刻',
    103: '大三元',      104: '小四喜',    105: '緑一色',
    106: '四槓子',      107: '字一色',    108: '清老頭',
    109: '大車輪',      110: '大七星',    111: '大四喜',
    112: '国士無双十三面', 113: '四暗刻単騎', 114: '純正九蓮宝燈',
    115: '天和',        116: '地和',      117: '人和',
    118: '差し込み',    119: '八連荘',
    120: 'ドラ',        121: '赤ドラ',    122: '裏ドラ',
};

const YAKUMAN_IDS = { min: 100, max: 119 };
const YAKUMAN_HAN = 13;

function isYakuman(yi) { return yi >= YAKUMAN_IDS.min && yi <= YAKUMAN_IDS.max; }

function yakuEntry(yi, han) {
    const name = YAKU_NAMES[yi] || ('役' + yi);
    if (isYakuman(yi)) return { name, fanshu: '*'.repeat(Math.max(1, Math.round(han / YAKUMAN_HAN))) };
    return { name, fanshu: han };
}

/** A win's hand result as majiang-ui's dialog reads it: its yaku rows, total han and fu, and the yakuman multiple. */
function buildHupai(hr) {
    const yk = hr ? hr.yk || [] : [];
    const yakumanHan = yk.filter(y => isYakuman(y.yi)).reduce((sum, y) => sum + y.han, 0);
    return {
        hupai:     yk.map(y => yakuEntry(y.yi, y.han)),
        fanshu:    hr ? hr.han : 0,
        fu:        hr ? hr.fu : 0,
        damanguan: Math.round(yakumanHan / YAKUMAN_HAN),
    };
}

export { yakuEntry, buildHupai };
