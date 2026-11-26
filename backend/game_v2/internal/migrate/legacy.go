package migrate

import (
	"errors"
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	legacyVersion   = "0.4-dev"
	legacyDoubleRon = wire.ResultType(2)
	legacyNagashi   = wire.ResultType(5)
	legacyAddedKan  = "added"
	legacyClosedKan = "closed"
)

var roundEndCommon = []wire.Key{
	wire.KeyEventType, wire.KeyResultType, wire.KeyRiichiSticks, wire.KeyDealer, wire.KeyDoraIndicators,
}

var legacyEventKeys = map[wire.EventType][]wire.Key{
	wire.EventMeld:           {wire.KeyEventType, wire.KeyPackedMeld},
	wire.EventDraw:           {wire.KeyEventType, wire.KeyPackedMove, wire.KeyTilesRemaining},
	wire.EventDiscard:        {wire.KeyEventType, wire.KeyPackedMove},
	wire.EventRiichiDeclared: {wire.KeyEventType, wire.KeySeat, wire.KeyScore, wire.KeyRiichiSticks},
	wire.EventDoraRevealed:   {wire.KeyEventType, wire.KeyTileID},
	wire.EventGameStarted: {
		wire.KeyEventType, wire.KeyGameID, wire.KeyGameType, wire.KeyPlayers, wire.KeyDealer, wire.KeyDealerDice,
		wire.KeyRiichiStickValue, wire.KeyHasAkadora, wire.KeySeed, wire.KeyRNGVersion, wire.KeyGameSettings,
	},
	wire.EventRoundStarted: {
		wire.KeyEventType, wire.KeyWind, wire.KeyRoundNumber, wire.KeyRoundInWind, wire.KeyDealer,
		wire.KeyCurrentPlayer, wire.KeyDoraIndicators, wire.KeyHonba, wire.KeyRiichiSticks, wire.KeyPlayers,
		wire.KeyDice, wire.KeyTilesRemaining,
	},
	wire.EventGameEnd: {
		wire.KeyEventType, wire.KeyWinnerSeat, wire.KeyStandings, wire.KeyLeftoverBonus, wire.KeyLeftoverRiichi,
		wire.KeyRoundCount, wire.KeyEndCause,
	},
	wire.EventSeatControl: {wire.KeyEventType, wire.KeySeat, wire.KeyAIPlayer, wire.KeySeatControlReason},
}

var legacyWinKeys = []wire.Key{
	wire.KeyWinnerSeat, wire.KeyHandResult, wire.KeyScoreChanges, wire.KeyRiichiCollected, wire.KeyClosedTiles,
	wire.KeyMelds, wire.KeyHonbaBonus, wire.KeyPaoSeat, wire.KeyPaoLiability, wire.KeyUraDora,
}

var legacyResultKeys = map[wire.ResultType][]wire.Key{
	wire.ResultTsumo: {
		wire.KeyWinnerSeat, wire.KeyHandResult, wire.KeyScores, wire.KeyScoreChanges, wire.KeyRiichiCollected,
		wire.KeyClosedTiles, wire.KeyMelds, wire.KeyWinningTile, wire.KeyHonbaBonus, wire.KeyPaoSeat,
		wire.KeyPaoLiability, wire.KeyUraDora,
	},
	wire.ResultRon: append(slices.Clone(legacyWinKeys),
		wire.KeyLoserSeat, wire.KeyWinningTile, wire.KeyScores, wire.KeyRobbedKan, wire.KeyHeadBumpedSeats),
	legacyDoubleRon: {
		wire.KeyLoserSeat, wire.KeyWinningTile, wire.KeyWinners, wire.KeyScores, wire.KeyScoreChanges,
		wire.KeyRobbedKan, wire.KeyHeadBumpedSeats,
	},
	wire.ResultExhaustiveDraw: {
		wire.KeyTenpaiSeats, wire.KeyNotenSeats, wire.KeyTenpaiHands, wire.KeyScores, wire.KeyScoreChanges,
	},
	wire.ResultAbortiveDraw: {
		wire.KeyAbortiveReason, wire.KeyScores, wire.KeyScoreChanges, wire.KeySeat, wire.KeyRonCallers,
		wire.KeyRobbedKan,
	},
	legacyNagashi: {
		wire.KeyQualifyingSeats, wire.KeyQualifyingRivers, wire.KeyTenpaiSeats, wire.KeyNotenSeats,
		wire.KeyTenpaiHands, wire.KeyScores, wire.KeyScoreChanges,
	},
}

var legacyNestedKeys = map[wire.Key][]wire.Key{
	wire.KeyHandResult: {
		wire.KeyHan, wire.KeyFu, wire.KeyYaku, wire.KeyPoints, wire.KeyHandLimit, wire.KeyYakumanCount,
	},
	wire.KeyYaku:             {wire.KeyYakuID, wire.KeyHan, wire.KeyYakuYakumanCount},
	wire.KeyPaoLiability:     {wire.KeyYaku, wire.KeyPaoShare, wire.KeyPaysHonba},
	wire.KeyRobbedKan:        {wire.KeySeat, wire.KeyTileID, wire.KeyKanType},
	wire.KeyWinners:          legacyWinKeys,
	wire.KeyStandings:        {wire.KeySeat, wire.KeyScore, wire.KeyFinalScore},
	wire.KeyTenpaiHands:      {wire.KeySeat, wire.KeyClosedTiles, wire.KeyMelds},
	wire.KeyQualifyingRivers: {wire.KeySeat, wire.KeyDiscards},
	wire.KeyDiscards:         {wire.KeyTileID, wire.KeyTsumogiri, wire.KeyRiichiDiscard},
}

var legacyPlayerKeys = map[wire.EventType][]wire.Key{
	wire.EventGameStarted:  {wire.KeySeat, wire.KeyName, wire.KeyAIPlayer},
	wire.EventRoundStarted: {wire.KeySeat, wire.KeyScore, wire.KeyTiles},
}

var errUnknownEvent = errors.New("a record of an event type replay version 0.4-dev never held")

func checkLegacyShape(record wire.Map) error {
	event, ok := intOf(record, wire.KeyEventType)
	keys, known := legacyEventKeys[wire.EventType(event)]
	switch {
	case !ok || event < 0 || event > int(wire.EventSeatControl):
		return errUnknownEvent
	case wire.EventType(event) == wire.EventRoundEnd:
		result, _ := intOf(record, wire.KeyResultType)
		resultKeys, isResult := legacyResultKeys[wire.ResultType(result)]
		if !isResult || result < 0 || result > int(legacyNagashi) {
			return errors.New("a round end of a result type replay version 0.4-dev never held")
		}

		keys = append(slices.Clone(roundEndCommon), resultKeys...)
	case !known:
		return errUnknownEvent
	}

	return checkFields(record, keys, wire.EventType(event))
}

func checkFields(m wire.Map, allowed []wire.Key, event wire.EventType) error {
	for _, f := range m {
		if !slices.Contains(allowed, f.Key) {
			return errors.New("a field replay version 0.4-dev never held there: " + f.Key.String())
		}

		nested, isNested := legacyNestedKeys[f.Key]
		if f.Key == wire.KeyPlayers {
			nested, isNested = legacyPlayerKeys[event], true
		}

		if !isNested {
			continue
		}

		err := checkNested(f.Value, nested, event)
		if err != nil {
			return errors.New(f.Key.String() + ": " + err.Error())
		}
	}

	return nil
}

func checkNested(v wire.Value, allowed []wire.Key, event wire.EventType) error {
	if object, isMap := v.(wire.Map); isMap {
		return checkFields(object, allowed, event)
	}

	items, _ := v.(wire.Array)
	for i, item := range items {
		object, isMap := item.(wire.Map)
		if !isMap {
			continue
		}

		err := checkFields(object, allowed, event)
		if err != nil {
			return errors.New("item " + strconv.Itoa(i) + ": " + err.Error())
		}
	}

	return nil
}

func intOf(m wire.Map, k wire.Key) (int, bool) {
	v, _ := m.Get(k)
	n, ok := v.(wire.Int)
	return int(n), ok
}
