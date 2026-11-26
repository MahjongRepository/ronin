package wire

import "strconv"

// A number is never renumbered or reused; a few aliases share one with another key.
type Key uint8

const (
	KeyReplayVersion       Key = 0
	KeyEventType           Key = 1
	KeyAIPlayer            Key = 2
	KeyHasAkadora          Key = 3
	KeyCurrentPlayer       Key = 4
	KeyClosedTiles         Key = 5
	KeyPackedMove          Key = 6
	KeyDice                Key = 7
	KeyDealerDice          Key = 8
	KeyDoraIndicators      Key = 9
	KeyDealer              Key = 10
	KeyDiscards            Key = 11
	KeyEndCause            Key = 12
	KeyFinalScore          Key = 13
	KeyFu                  Key = 14
	KeyGameID              Key = 15
	KeyGameSettings        Key = 16
	KeyGameType            Key = 17
	KeyHonba               Key = 18
	KeyHan                 Key = 19
	KeyHonbaBonus          Key = 20
	KeyHeadBumpedSeats     Key = 21
	KeyHandResult          Key = 22
	KeyKanType             Key = 23
	KeyLeftoverBonus       Key = 24
	KeyHandLimit           Key = 25
	KeyLeftoverRiichi      Key = 26
	KeyLoserSeat           Key = 27
	KeyPackedMeld          Key = 28
	KeyMelds               Key = 29
	KeyRoundNumber         Key = 30
	KeyName                Key = 31
	KeyRoundCount          Key = 32
	KeyNotenSeats          Key = 33
	KeyPlayers             Key = 34
	KeyPaoLiability        Key = 35
	KeyPaoSeat             Key = 36
	KeyPoints              Key = 37
	KeyQualifyingRivers    Key = 38
	KeyQualifyingSeats     Key = 39
	KeyRiichiSticks        Key = 40
	KeyRiichiCollected     Key = 41
	KeyRonCallers          Key = 42
	KeyRiichiDiscard       Key = 43
	KeyRobbedKan           Key = 44
	KeyAbortiveReason      Key = 45
	KeyRiichiStickValue    Key = 46
	KeyResultType          Key = 47
	KeyRNGVersion          Key = 48
	KeyRoundInWind         Key = 49
	KeySeat                Key = 50
	KeyScore               Key = 51
	KeyScoreChanges        Key = 52
	KeyScores              Key = 53
	KeySeed                Key = 54
	KeyPaoShare            Key = 55
	KeyStandings           Key = 56
	KeyTsumogiri           Key = 57
	KeyTenpaiHands         Key = 58
	KeyTileID              Key = 59
	KeyTiles               Key = 60
	KeyTilesRemaining      Key = 61
	KeyTenpaiSeats         Key = 62
	KeyUraDora             Key = 63
	KeyWind                Key = 64
	KeyWinners             Key = 65
	KeyWinnerSeat          Key = 66
	KeyWinningTile         Key = 67
	KeyYakumanCount        Key = 68
	KeyYakuID              Key = 69
	KeyYaku                Key = 70
	KeyYakuYakumanCount    Key = 71
	KeyAction              Key = 72
	KeyAvailableActions    Key = 73
	KeyAvailableCalls      Key = 74
	KeyRoundAdvanceSeconds Key = 75
	KeyBankSeconds         Key = 76
	KeyGameErrorCode       Key = 77
	KeyCallers             Key = 78
	KeyCallType            Key = 79
	KeySessionErrorCode    Key = 80
	KeyCallerSeat          Key = 81
	KeyWaitElapsed         Key = 82
	KeyFuriten             Key = 83
	KeyFirstDealer         Key = 84
	KeyFromSeat            Key = 85
	KeyGameTicket          Key = 86
	KeyGameStartConfirm    Key = 87
	KeyActionKanType       Key = 88
	KeyKuikaeTiles         Key = 89
	KeyLatestDiscardSeat   Key = 90
	KeyMaxBankSeconds      Key = 91
	KeySessionErrorMessage Key = 92
	KeyGameErrorMessage    Key = 93
	KeyMyTiles             Key = 94
	KeyConfirmationOwed    Key = 95
	KeyCallOptions         Key = 96
	KeyPlayerStates        Key = 97
	KeyRoundAdvanceTimeout Key = 98
	KeyRoundResult         Key = 99
	KeyRoundHistory        Key = 100
	KeyIsRiichi            Key = 101
	KeyRiichiSeats         Key = 102
	KeySequenceTiles       Key = 103
	KeyStandInReason       Key = 104
	KeyBaseTurnSeconds     Key = 105
	KeyTileCount           Key = 106
	KeyTimerSettings       Key = 107
	KeySessionType         Key = 108
	KeyWaitID              Key = 109
	KeyShownHands          Key = 110
)

const (
	KeyPendingGameTimeout = KeyPoints
	KeySeatControlReason  = KeyRiichiSticks
	KeyPaysHonba          = KeyHonbaBonus
)

const keyCount = int(KeyShownHands) + 1

var keyNames = [keyCount]string{
	KeyReplayVersion:       "REPLAY_VERSION",
	KeyEventType:           "EVENT_TYPE",
	KeyAIPlayer:            "AI_PLAYER",
	KeyHasAkadora:          "HAS_AKADORA",
	KeyCurrentPlayer:       "CURRENT_PLAYER",
	KeyClosedTiles:         "CLOSED_TILES",
	KeyPackedMove:          "PACKED_MOVE",
	KeyDice:                "DICE",
	KeyDealerDice:          "DEALER_DICE",
	KeyDoraIndicators:      "DORA_INDICATORS",
	KeyDealer:              "DEALER",
	KeyDiscards:            "DISCARDS",
	KeyEndCause:            "END_CAUSE",
	KeyFinalScore:          "FINAL_SCORE",
	KeyFu:                  "FU",
	KeyGameID:              "GAME_ID",
	KeyGameSettings:        "GAME_SETTINGS",
	KeyGameType:            "GAME_TYPE",
	KeyHonba:               "HONBA",
	KeyHan:                 "HAN",
	KeyHonbaBonus:          "HONBA_BONUS",
	KeyHeadBumpedSeats:     "HEAD_BUMPED_SEATS",
	KeyHandResult:          "HAND_RESULT",
	KeyKanType:             "KAN_TYPE",
	KeyLeftoverBonus:       "LEFTOVER_BONUS",
	KeyHandLimit:           "HAND_LIMIT",
	KeyLeftoverRiichi:      "LEFTOVER_RIICHI",
	KeyLoserSeat:           "LOSER_SEAT",
	KeyPackedMeld:          "PACKED_MELD",
	KeyMelds:               "MELDS",
	KeyRoundNumber:         "ROUND_NUMBER",
	KeyName:                "NAME",
	KeyRoundCount:          "ROUND_COUNT",
	KeyNotenSeats:          "NOTEN_SEATS",
	KeyPlayers:             "PLAYERS",
	KeyPaoLiability:        "PAO_LIABILITY",
	KeyPaoSeat:             "PAO_SEAT",
	KeyPoints:              "POINTS",
	KeyQualifyingRivers:    "QUALIFYING_RIVERS",
	KeyQualifyingSeats:     "QUALIFYING_SEATS",
	KeyRiichiSticks:        "RIICHI_STICKS",
	KeyRiichiCollected:     "RIICHI_COLLECTED",
	KeyRonCallers:          "RON_CALLERS",
	KeyRiichiDiscard:       "RIICHI_DISCARD",
	KeyRobbedKan:           "ROBBED_KAN",
	KeyAbortiveReason:      "ABORTIVE_REASON",
	KeyRiichiStickValue:    "RIICHI_STICK_VALUE",
	KeyResultType:          "RESULT_TYPE",
	KeyRNGVersion:          "RNG_VERSION",
	KeyRoundInWind:         "ROUND_IN_WIND",
	KeySeat:                "SEAT",
	KeyScore:               "SCORE",
	KeyScoreChanges:        "SCORE_CHANGES",
	KeyScores:              "SCORES",
	KeySeed:                "SEED",
	KeyPaoShare:            "PAO_SHARE",
	KeyStandings:           "STANDINGS",
	KeyTsumogiri:           "TSUMOGIRI",
	KeyTenpaiHands:         "TENPAI_HANDS",
	KeyTileID:              "TILE_ID",
	KeyTiles:               "TILES",
	KeyTilesRemaining:      "TILES_REMAINING",
	KeyTenpaiSeats:         "TENPAI_SEATS",
	KeyUraDora:             "URA_DORA",
	KeyWind:                "WIND",
	KeyWinners:             "WINNERS",
	KeyWinnerSeat:          "WINNER_SEAT",
	KeyWinningTile:         "WINNING_TILE",
	KeyYakumanCount:        "YAKUMAN_COUNT",
	KeyYakuID:              "YAKU_ID",
	KeyYaku:                "YAKU",
	KeyYakuYakumanCount:    "YAKU_YAKUMAN_COUNT",
	KeyAction:              "ACTION",
	KeyAvailableActions:    "AVAILABLE_ACTIONS",
	KeyAvailableCalls:      "AVAILABLE_CALLS",
	KeyRoundAdvanceSeconds: "ROUND_ADVANCE_SECONDS",
	KeyBankSeconds:         "BANK_SECONDS",
	KeyGameErrorCode:       "GAME_ERROR_CODE",
	KeyCallers:             "CALLERS",
	KeyCallType:            "CALL_TYPE",
	KeySessionErrorCode:    "SESSION_ERROR_CODE",
	KeyCallerSeat:          "CALLER_SEAT",
	KeyWaitElapsed:         "WAIT_ELAPSED",
	KeyFuriten:             "FURITEN",
	KeyFirstDealer:         "FIRST_DEALER",
	KeyFromSeat:            "FROM_SEAT",
	KeyGameTicket:          "GAME_TICKET",
	KeyGameStartConfirm:    "GAME_START_CONFIRM",
	KeyActionKanType:       "ACTION_KAN_TYPE",
	KeyKuikaeTiles:         "KUIKAE_TILES",
	KeyLatestDiscardSeat:   "LATEST_DISCARD_SEAT",
	KeyMaxBankSeconds:      "MAX_BANK_SECONDS",
	KeySessionErrorMessage: "SESSION_ERROR_MESSAGE",
	KeyGameErrorMessage:    "GAME_ERROR_MESSAGE",
	KeyMyTiles:             "MY_TILES",
	KeyConfirmationOwed:    "CONFIRMATION_OWED",
	KeyCallOptions:         "CALL_OPTIONS",
	KeyPlayerStates:        "PLAYER_STATES",
	KeyRoundAdvanceTimeout: "ROUND_ADVANCE_TIMEOUT",
	KeyRoundResult:         "ROUND_RESULT",
	KeyRoundHistory:        "ROUND_HISTORY",
	KeyIsRiichi:            "IS_RIICHI",
	KeyRiichiSeats:         "RIICHI_SEATS",
	KeySequenceTiles:       "SEQUENCE_TILES",
	KeyStandInReason:       "STAND_IN_REASON",
	KeyBaseTurnSeconds:     "BASE_TURN_SECONDS",
	KeyTileCount:           "TILE_COUNT",
	KeyTimerSettings:       "TIMER_SETTINGS",
	KeySessionType:         "SESSION_TYPE",
	KeyWaitID:              "WAIT_ID",
	KeyShownHands:          "SHOWN_HANDS",
}

func (k Key) String() string {
	if int(k) < keyCount {
		return keyNames[k]
	}

	return "Key(" + strconv.Itoa(int(k)) + ")"
}
