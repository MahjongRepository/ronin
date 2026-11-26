package replay

import (
	"errors"
	"fmt"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const gameStartPosition = 2

type Replay struct {
	Records []wire.Map
	Seed    engine.Seed
	Names   [tile.SeatCount]string
	AI      [tile.SeatCount]bool
	Actions []SeatAction
}

// SeatAction is one action of one seat.
type SeatAction struct {
	Seat   tile.Seat
	Action play.Action
}

// LoadError reports the record a replay cannot be played from, counted from 1 with the version
// record, and why.
type LoadError struct {
	Record int
	Err    error
}

func (e LoadError) Error() string {
	return "replay record " + strconv.Itoa(e.Record) + ": " + e.Err.Error()
}

func (e LoadError) Unwrap() error {
	return e.Err
}

func Load(content []byte) (Replay, error) {
	records, err := wire.DecodeReplay(content)
	if err != nil {
		return Replay{}, err
	}

	if len(records) < gameStartPosition {
		return Replay{}, LoadError{Record: gameStartPosition, Err: errors.New("the replay records no game start")}
	}

	r, err := readGameStart(records[gameStartPosition-1])
	if err != nil {
		return Replay{}, LoadError{Record: gameStartPosition, Err: err}
	}

	r.Records = records

	for i, record := range records[gameStartPosition:] {
		actions, actionsErr := recordActions(record)
		if actionsErr != nil {
			return Replay{}, LoadError{Record: gameStartPosition + 1 + i, Err: actionsErr}
		}

		r.Actions = append(namingRobbedClosedKan(r.Actions, record), actions...)
	}

	return r, nil
}

func namingRobbedClosedKan(actions []SeatAction, record wire.Map) []SeatAction {
	result, _ := record.Int(wire.KeyResultType)
	winTile, won := record.Int(wire.KeyWinningTile)
	robbed, valid := tile.NewTileID(winTile)
	if eventOf(record) != play.Some(wire.EventRoundEnd) || wire.ResultType(result) != wire.ResultRon || !won ||
		!valid || len(actions) == 0 {
		return actions
	}

	last := actions[len(actions)-1]
	kind, isKan := last.Action.Kan()
	named, _ := last.Action.Tile()
	if !isKan || kind != play.KanClosed || named.Kind() != robbed.Kind() {
		return actions
	}

	actions[len(actions)-1].Action = play.KanAction(play.KanClosed, robbed)
	return actions
}

func readGameStart(record wire.Map) (Replay, error) {
	var r Replay
	if eventOf(record) != play.Some(wire.EventGameStarted) {
		return r, errors.New("the second record is no game start")
	}

	gameType, _ := record.Get(wire.KeyGameType)
	if gameType != wire.Int(wire.GameHanchan) {
		return r, errors.New("the game is no hanchan")
	}

	scheme, _ := record.Get(wire.KeyRNGVersion)
	if scheme != wire.Str(engine.RNGVersion) {
		return r, fmt.Errorf("the game's randomness is not %s", engine.RNGVersion)
	}

	settings, _ := record.Get(wire.KeyGameSettings)
	envelope, _ := settings.(wire.StrMap)
	profile, _ := envelope.Get("id")
	if profile != wire.Int(wire.RulesProfileID) {
		return r, errors.New("the game was played under another rules profile")
	}

	raw, _ := record.Get(wire.KeySeed)
	bin, _ := raw.(wire.Bin)
	if len(bin) != len(r.Seed) {
		return r, errors.New("the game start holds no seed")
	}

	copy(r.Seed[:], bin)

	err := readPlayers(&r, record)
	return r, err
}

func readPlayers(r *Replay, record wire.Map) error {
	raw, _ := record.Get(wire.KeyPlayers)
	players, _ := raw.(wire.Array)
	if len(players) != tile.SeatCount {
		return fmt.Errorf("the game start names %d players", len(players))
	}

	for _, entry := range players {
		player, _ := entry.(wire.Map)
		s, ok := seatField(player, wire.KeySeat)
		name, _ := player.Str(wire.KeyName)
		if !ok || name == "" || r.Names[s.Index()] != "" {
			return errors.New("the game start does not name one player at each seat")
		}

		ai, _ := player.Int(wire.KeyAIPlayer)
		r.Names[s.Index()], r.AI[s.Index()] = name, ai == 1
	}

	return nil
}

func recordActions(record wire.Map) ([]SeatAction, error) {
	event := eventOf(record)
	switch event.Value {
	case wire.EventDiscard:
		return discardAction(record)
	case wire.EventMeld:
		return meldAction(record)
	case wire.EventRoundEnd:
		return roundEndActions(record)
	case wire.EventDraw, wire.EventRiichiDeclared, wire.EventDoraRevealed, wire.EventRoundStarted,
		wire.EventGameEnd, wire.EventPaoAssigned, wire.EventSeatControl:
		return nil, nil
	case wire.EventGameStarted, wire.EventCallPrompt, wire.EventError, wire.EventFuriten, wire.EventTurn,
		wire.EventDrawNotice:
	}

	return nil, errors.New("no replay of this server holds this record after its game start")
}

func discardAction(record wire.Map) ([]SeatAction, error) {
	packed, _ := record.Int(wire.KeyPackedMove)
	move, err := wire.UnpackDiscard(packed)
	if err != nil {
		return nil, err
	}

	if move.Riichi {
		return []SeatAction{{Seat: move.Seat, Action: play.RiichiAction(move.Tile)}}, nil
	}

	return []SeatAction{{Seat: move.Seat, Action: play.DiscardAction(move.Tile)}}, nil
}

func meldAction(record wire.Map) ([]SeatAction, error) {
	packed, _ := record.Int(wire.KeyPackedMeld)
	m, err := wire.UnpackMeld(packed)
	if err != nil {
		return nil, err
	}

	var action play.Action
	switch m.Kind {
	case play.MeldChi, play.MeldPon, play.MeldOpenKan:
		view := play.MeldView{Kind: m.Kind, Tiles: m.Tiles, Called: m.Called, From: m.From, Added: m.Added}
		call, _ := view.Call()
		switch c := call.(type) {
		case play.ChiCall:
			action = play.ChiAction(c.Held)
		case play.PonCall:
			action = play.PonAction(c.Held)
		case play.OpenKanCall:
			action = play.KanAction(play.KanOpen, m.Called.Value)
		}
	case play.MeldAddedKan:
		action = play.KanAction(play.KanAdded, m.Added.Value)
	case play.MeldClosedKan:
		action = play.KanAction(play.KanClosed, m.Tiles[0])
	}

	return []SeatAction{{Seat: m.Caller, Action: action}}, nil
}

func roundEndActions(record wire.Map) ([]SeatAction, error) {
	result, _ := record.Int(wire.KeyResultType)
	_, bumped := record.Get(wire.KeyHeadBumpedSeats)
	if bumped && wire.ResultType(result) != wire.ResultRon {
		return nil, errors.New("a round end that is no ron names head-bumped seats")
	}

	switch wire.ResultType(result) {
	case wire.ResultTsumo:
		return declarations(play.TsumoAction(), []wire.Value{fieldOf(record, wire.KeyWinnerSeat)})
	case wire.ResultRon:
		return ronActions(record)
	case wire.ResultAbortiveDraw:
		return abortActions(record)
	case wire.ResultExhaustiveDraw:
	}

	return nil, nil
}

func ronActions(record wire.Map) ([]SeatAction, error) {
	raw, _ := record.Get(wire.KeyWinners)
	winners, _ := raw.(wire.Array)
	seats := make([]wire.Value, 0, len(winners))
	for _, entry := range winners {
		winner, _ := entry.(wire.Map)
		seats = append(seats, fieldOf(winner, wire.KeyWinnerSeat))
	}

	bumped, _ := record.Get(wire.KeyHeadBumpedSeats)
	bumpedSeats, _ := bumped.(wire.Array)
	return declarations(play.RonAction(), append(seats, bumpedSeats...))
}

func abortActions(record wire.Map) ([]SeatAction, error) {
	reason, _ := record.Str(wire.KeyAbortiveReason)
	switch wire.AbortReason(reason) {
	case wire.AbortNineTerminals:
		return declarations(play.KyuushuAction(), []wire.Value{fieldOf(record, wire.KeySeat)})
	case wire.AbortTripleRon:
		callers, _ := record.Get(wire.KeyRonCallers)
		seats, _ := callers.(wire.Array)
		return declarations(play.RonAction(), seats)
	case wire.AbortFourWinds, wire.AbortFourRiichi, wire.AbortFourKans:
		return nil, nil
	}

	return nil, fmt.Errorf("unknown abort reason %q", reason)
}

func declarations(action play.Action, seats []wire.Value) ([]SeatAction, error) {
	actions := make([]SeatAction, 0, len(seats))
	for _, v := range seats {
		s, ok := seatOf(v)
		if !ok {
			return nil, errors.New("a round end names a seat that is none")
		}

		actions = append(actions, SeatAction{Seat: s, Action: action})
	}

	return actions, nil
}

func eventOf(record wire.Map) play.Option[wire.EventType] {
	code, ok := record.Int(wire.KeyEventType)
	if !ok || code < 0 || code != int(wire.EventType(code)) {
		return play.Option[wire.EventType]{}
	}

	return play.Some(wire.EventType(code))
}

func fieldOf(m wire.Map, k wire.Key) wire.Value {
	v, _ := m.Get(k)
	return v
}

func seatField(m wire.Map, k wire.Key) (tile.Seat, bool) {
	return seatOf(fieldOf(m, k))
}

func seatOf(v wire.Value) (tile.Seat, bool) {
	n, ok := v.(wire.Int)
	if !ok {
		return tile.Seat{}, false
	}

	return tile.NewSeat(int(n))
}
