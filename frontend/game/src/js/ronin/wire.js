/* Mirrors backend/game/messaging/wire_enums.py and backend/game/wire/enums.py */

const wire = {

    /* client → server: t */
    T: {
        GAME_ACTION: 3,
        RECONNECT:   6,
        JOIN_GAME:   7,
    },

    /* game_action: a */
    A: {
        DISCARD:        0,
        DECLARE_RIICHI: 1,
        DECLARE_TSUMO:  2,
        CALL_RON:       3,
        CALL_PON:       4,
        CALL_CHI:       5,
        CALL_KAN:       6,
        CALL_KYUUSHU:   7,
        PASS:           8,
        CONFIRM_ROUND:  9,
    },

    /* server → client: t */
    E: {
        MELD:          0,
        DRAW:          1,
        DISCARD:       2,
        CALL_PROMPT:   3,
        ROUND_END:     4,
        RIICHI_DECL:   5,
        DORA_REVEALED: 6,
        ERROR:         7,
        GAME_STARTED:  8,
        ROUND_STARTED: 9,
        GAME_END:      10,
        FURITEN:       11,
        TURN:          12,
    },

    /* call_prompt: clt */
    CLT: { RON: 0, MELD: 1, CHANKAN: 2 },

    MELD_CALL: { PON: 0, CHI: 1, OPEN_KAN: 2 },

    /* draw: aa[].a; tl holds tile ids for RIICHI, tile types for KAN and ADDED_KAN */
    PA: { DISCARD: 0, RIICHI: 1, TSUMO: 2, KAN: 3, ADDED_KAN: 4, KYUUSHU: 5 },

    /* round_end: rt */
    RT: { TSUMO: 0, RON: 1, DOUBLE_RON: 2, EXHAUSTIVE: 3, ABORTIVE: 4, NAGASHI: 5 },

    WIND: { EAST: 0, SOUTH: 1, WEST: 2, NORTH: 3 },

    /* game_started: gt */
    GAME_TYPE: { HANCHAN: 0, TONPUSEN: 1 },

    KAN: { OPEN: 'open', CLOSED: 'closed', ADDED: 'added' },

    MELD: { CHI: 'chi', PON: 'pon', OPEN_KAN: 'open_kan',
            CLOSED_KAN: 'closed_kan', ADDED_KAN: 'added_kan' },

    /* session messages: type */
    SESSION: {
        ERROR:              'session_error',
        PLAYER_LEFT:        'player_left',
        PLAYER_RECONNECTED: 'player_reconnected',
        GAME_RECONNECTED:   'game_reconnected',
    },

    SESSION_ERROR: {
        INVALID_MESSAGE:           'invalid_message',
        INTERNAL_ERROR:            'internal_error',
        NOT_IN_GAME:               'not_in_game',
        ALREADY_IN_GAME:           'already_in_game',
        RATE_LIMITED:              'rate_limited',
        INVALID_TICKET:            'invalid_ticket',
        RECONNECT_NO_SESSION:      'reconnect_no_session',
        RECONNECT_GAME_MISMATCH:   'reconnect_game_mismatch',
        RECONNECT_RETRY_LATER:     'reconnect_retry_later',
        RECONNECT_ALREADY_ACTIVE:  'reconnect_already_active',
        JOIN_GAME_NOT_FOUND:       'join_game_not_found',
        JOIN_GAME_ALREADY_STARTED: 'join_game_already_started',
        JOIN_GAME_NO_SESSION:      'join_game_no_session',
    },

    GAME_ERROR: { STALE_ACTION: 'stale_action' },

    WAIT_ID: 'wi',

    /* game_started, game_reconnected: tm = { tb, bk, rb, mb, md } */
    TIMER_SETTINGS: 'tm',

    /* game_reconnected during a round advance: re = the round end's result fields { rt, ... } */
    ROUND_RESULT: 're',

    NUM_TILES:     136,
    SEAT_SPACE:    544,   /* 4 × 136 */
    DISCARD_FLAGS: 4,     /* bit 0 = tsumogiri, bit 1 = riichi */
    SCORE_DIV:     100,   /* wire scores are divided by 100 */
};

export default wire;
