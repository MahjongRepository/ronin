"use strict";

const RONIN_RULE = {
    配給原点: 25000,
    順位点: ['+20.0', '+10.0', '-10.0', '-20.0'],   /* uma 10/20 */
    赤牌: { m: 1, p: 1, s: 1 },
    連風牌は2符: true,
    クイタンあり: true,
    喰い替え許可レベル: 0,                          /* kuikae forbidden */
    場数: 2,                                       /* hanchan */
    途中流局あり: true,                            /* abortive draws */
    流し満貫あり: true,
    ノーテン宣言あり: true,
    ノーテン罰あり: true,
    最大同時和了数: 2,                             /* double ron */
    連荘方式: 2,                                   /* renchan on dealer win, tenpai, abortive draw */
    トビ終了あり: true,
    オーラス止めあり: false,
    延長戦方式: 0,
    一発あり: true,
    裏ドラあり: true,
    カンドラあり: true,
    カン裏あり: true,
    カンドラ後乗せ: false,
    ツモ番なしリーチあり: true,
    リーチ後暗槓許可レベル: 1,
    ダブル役満あり: true,
    役満の複合あり: true,
    数え役満あり: true,
    役満パオあり: true,
    切り上げ満貫あり: true,
};

export default RONIN_RULE;
