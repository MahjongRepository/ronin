package wire

import (
	"errors"
	"fmt"
	"strings"
)

type fieldKind uint8

const (
	fieldInt fieldKind = iota
	fieldStr
	fieldBool
	fieldIntArray
	fieldObjectArray
	fieldDealerDice
	fieldYaku
	fieldObject
	fieldScoreMap
	fieldIntOrBool
	fieldCheckedApart
)

const (
	dealerRolls = 2
	diceInRoll  = 2
	maxRonWins  = 2
)

var fieldKinds = func() [keyCount]fieldKind {
	var kinds [keyCount]fieldKind
	set := func(kind fieldKind, keys ...Key) {
		for _, k := range keys {
			kinds[k] = kind
		}
	}
	set(fieldStr, KeyGameID, KeyName, KeyRNGVersion, KeyEndCause, KeyHandLimit, KeyKanType, KeyPaoShare,
		KeyAbortiveReason)
	set(fieldBool, KeyHasAkadora, KeyRiichiDiscard, KeyTsumogiri)
	set(fieldIntArray, KeyClosedTiles, KeyDice, KeyDoraIndicators, KeyHeadBumpedSeats, KeyMelds,
		KeyNotenSeats, KeyQualifyingSeats, KeyRonCallers, KeyTiles, KeyTenpaiSeats, KeyUraDora)
	set(fieldObjectArray, KeyDiscards, KeyPlayers, KeyQualifyingRivers, KeyStandings, KeyTenpaiHands,
		KeyWinners, KeyShownHands)
	set(fieldDealerDice, KeyDealerDice)
	set(fieldYaku, KeyYaku)
	set(fieldObject, KeyHandResult, KeyPaoLiability, KeyRobbedKan)
	set(fieldScoreMap, KeyScores, KeyScoreChanges)
	set(fieldIntOrBool, KeyHonbaBonus)
	set(fieldCheckedApart, KeySeed, KeyGameSettings)
	return kinds
}()

var eventFields = map[EventType][]Key{
	EventMeld:           {KeyEventType, KeyPackedMeld},
	EventDraw:           {KeyEventType, KeyPackedMove, KeyTilesRemaining},
	EventDiscard:        {KeyEventType, KeyPackedMove},
	EventRoundEnd:       {KeyEventType, KeyResultType, KeyRiichiSticks, KeyDealer, KeyDoraIndicators},
	EventRiichiDeclared: {KeyEventType, KeySeat, KeyScore, KeyRiichiSticks},
	EventDoraRevealed:   {KeyEventType, KeyTileID},
	EventGameStarted: {
		KeyEventType, KeyGameID, KeyGameType, KeyPlayers, KeyDealer, KeyDealerDice, KeyRiichiStickValue,
		KeyHasAkadora, KeySeed, KeyRNGVersion, KeyGameSettings,
	},
	EventRoundStarted: {
		KeyEventType, KeyWind, KeyRoundNumber, KeyRoundInWind, KeyDealer, KeyCurrentPlayer,
		KeyDoraIndicators, KeyHonba, KeyRiichiSticks, KeyPlayers, KeyDice, KeyTilesRemaining,
	},
	EventGameEnd: {
		KeyEventType, KeyWinnerSeat, KeyStandings, KeyLeftoverBonus, KeyLeftoverRiichi, KeyRoundCount,
		KeyEndCause,
	},
	EventPaoAssigned: {KeyEventType, KeySeat, KeyPaoSeat},
	EventSeatControl: {KeyEventType, KeySeat, KeyAIPlayer},
}

var resultFields = map[ResultType][]Key{
	ResultTsumo: {
		KeyWinnerSeat, KeyHandResult, KeyScores, KeyScoreChanges, KeyRiichiCollected, KeyClosedTiles,
		KeyMelds, KeyWinningTile, KeyHonbaBonus,
	},
	ResultRon:            {KeyLoserSeat, KeyWinningTile, KeyWinners, KeyScores, KeyScoreChanges},
	ResultExhaustiveDraw: {KeyTenpaiSeats, KeyNotenSeats, KeyTenpaiHands, KeyScores, KeyScoreChanges},
	ResultAbortiveDraw:   {KeyAbortiveReason, KeyScores, KeyScoreChanges},
}

var playerFields = map[EventType][]Key{
	EventGameStarted:  {KeySeat, KeyName, KeyAIPlayer},
	EventRoundStarted: {KeySeat, KeyScore, KeyTiles},
}

var shownHandFields = []Key{KeySeat, KeyClosedTiles, KeyMelds}

var nestedFields = map[Key][]Key{
	KeyHandResult:       {KeyHan, KeyFu, KeyYaku, KeyPoints, KeyHandLimit},
	KeyPaoLiability:     {KeyYaku, KeyPaoShare, KeyPaysHonba},
	KeyRobbedKan:        {KeySeat, KeyTileID, KeyKanType},
	KeyStandings:        {KeySeat, KeyScore, KeyFinalScore},
	KeyTenpaiHands:      shownHandFields,
	KeyShownHands:       shownHandFields,
	KeyQualifyingRivers: {KeySeat, KeyDiscards},
	KeyDiscards:         {KeyTileID, KeyTsumogiri, KeyRiichiDiscard},
	KeyWinners: {
		KeyWinnerSeat, KeyHandResult, KeyScoreChanges, KeyRiichiCollected, KeyClosedTiles, KeyMelds,
		KeyHonbaBonus,
	},
	KeyYaku: {KeyYakuID, KeyHan, KeyYakuYakumanCount},
}

type schemaContext struct {
	event  EventType
	parent Key
	top    bool
}

func validateReplayEvent(record Map) error {
	raw, _ := record.Get(KeyEventType)
	code, ok := raw.(Int)
	event := EventType(code)
	fields, known := eventFields[event]
	if !ok || code < 0 || Int(event) != code || !known {
		return errors.New("unsupported replay event type")
	}

	err := requireFields(record, fields)
	if err != nil {
		return err
	}
	err = validateFields(record, schemaContext{event: event, top: true})
	if err != nil {
		return err
	}

	if event == EventRoundEnd {
		return validateRoundEnd(record)
	}
	standIn, _ := record.Get(KeyAIPlayer)
	if event == EventSeatControl && standIn == Int(1) {
		return requireFields(record, []Key{KeySeatControlReason})
	}
	return nil
}

func validateRoundEnd(record Map) error {
	raw, _ := record.Get(KeyResultType)
	code := raw.(Int)
	result := ResultType(code)
	fields, known := resultFields[result]
	if code < 0 || Int(result) != code || !known {
		return errors.New("unsupported replay result type")
	}

	err := requireFields(record, fields)
	if err != nil {
		return err
	}
	if result != ResultRon {
		return nil
	}

	winners, _ := record.Get(KeyWinners)
	if wins := len(winners.(Array)); wins == 0 || wins > maxRonWins {
		return fmt.Errorf("a ron holds one win or %d", maxRonWins)
	}
	return nil
}

func requireFields(m Map, fields []Key) error {
	var missing []string
	for _, k := range fields {
		_, ok := m.Get(k)
		if !ok {
			missing = append(missing, k.String())
		}
	}
	if len(missing) > 0 {
		return fmt.Errorf("missing %s", strings.Join(missing, ", "))
	}
	return nil
}

func validateFields(m Map, ctx schemaContext) error {
	for _, f := range m {
		err := validateField(f, ctx)
		if err != nil {
			return fmt.Errorf("replay field %s: %w", f.Key, err)
		}
	}
	return nil
}

func validateField(f Field, ctx schemaContext) error {
	switch fieldKinds[f.Key] {
	case fieldInt:
		return expect[Int](f.Value, "an integer")
	case fieldStr:
		return expect[Str](f.Value, "a string")
	case fieldBool:
		return expect[Bool](f.Value, "a boolean")
	case fieldIntOrBool:
		if _, ok := f.Value.(Bool); ok {
			return nil
		}
		return expect[Int](f.Value, "an integer or a boolean")
	case fieldIntArray:
		return validateIntArray(f.Value)
	case fieldYaku:
		if ctx.parent == KeyPaoLiability {
			return validateIntArray(f.Value)
		}
		return validateObjects(f, nestedFields[f.Key], ctx)
	case fieldObjectArray:
		required := nestedFields[f.Key]
		if f.Key == KeyPlayers {
			required = nil
			if ctx.top {
				required = playerFields[ctx.event]
			}
		}
		return validateObjects(f, required, ctx)
	case fieldDealerDice:
		return validateDealerDice(f.Value)
	case fieldObject:
		return validateObject(f.Value, f.Key, ctx)
	case fieldScoreMap, fieldCheckedApart:
	}
	return nil
}

func expect[T Value](v Value, what string) error {
	if _, ok := v.(T); !ok {
		return fmt.Errorf("expected %s", what)
	}
	return nil
}

func validateIntArray(v Value) error {
	items, ok := v.(Array)
	if !ok {
		return errors.New("expected an array")
	}
	for _, item := range items {
		err := expect[Int](item, "an array of integers")
		if err != nil {
			return err
		}
	}
	return nil
}

func validateDealerDice(v Value) error {
	rolls, ok := v.(Array)
	if !ok || len(rolls) != dealerRolls {
		return errors.New("expected two rolls of dice")
	}
	for _, roll := range rolls {
		dice, isArray := roll.(Array)
		if !isArray || len(dice) != diceInRoll {
			return errors.New("expected two rolls of two dice")
		}
		err := validateIntArray(dice)
		if err != nil {
			return err
		}
	}
	return nil
}

func validateObjects(f Field, required []Key, ctx schemaContext) error {
	items, ok := f.Value.(Array)
	if !ok {
		return errors.New("expected an array")
	}
	for _, item := range items {
		object, isMap := item.(Map)
		if !isMap {
			return errors.New("expected an array of objects")
		}
		err := requireFields(object, required)
		if err != nil {
			return err
		}
		err = validateFields(object, schemaContext{event: ctx.event, parent: f.Key})
		if err != nil {
			return err
		}
	}
	return nil
}

func validateObject(v Value, k Key, ctx schemaContext) error {
	object, ok := v.(Map)
	if !ok {
		return errors.New("expected an object")
	}
	err := requireFields(object, nestedFields[k])
	if err != nil {
		return err
	}
	return validateFields(object, schemaContext{event: ctx.event, parent: k})
}
