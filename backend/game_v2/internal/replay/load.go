// Package replay plays a replay this server wrote again through the engine: Load reads the seed,
// the names and every seat's action out of its records, and Run plays those actions from a game
// setup, so a caller can compare what the run emits with what the replay recorded.
//
// A replay records the engine's events, not the actions behind them. A discard and a declared meld
// are their seat's actions; a round end names the winners, the seats whose ron lost to head bump,
// the kyuushu declarer and the triple ron's declarers; every other answer to a call prompt was a
// pass, which Run answers itself. A closed kan's record holds its four tiles but not the copy its
// declarer named, which only a robbing ron's winning tile shows: Load names that copy for a
// robbed closed kan and the lowest one for any other. A replay holds its seed and no wall, so a game dealt from fixed
// walls plays again only from the same setup. Only a replay of this server's rules profile loads:
// a game rewritten from an older format was scored under other rules and does not reproduce.
//
// Ported from ronin's Python replay loader and runner.
package replay

import (
	"errors"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const gameStartPosition = 2

// Replay is a replay read for a run: its records as wire.DecodeReplay returned them, the version
// record first; the seed its game start records; the name at each seat; and every seat action its
// records imply, in play order, the passes left out.
type Replay struct {
	Records []wire.Map
	Seed    engine.Seed
	Names   [tile.SeatCount]string
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

// Load reads a replay's content, uncompressed. It returns what wire.DecodeReplay refuses as that
// error, and a LoadError for a replay whose second record is not the game start of this server's
// rules (the hanchan, the shake256-v1 scheme, wire.RulesProfileID and a name at every seat), or
// for a record after it that no replay of this server holds there.
func Load(content []byte) (Replay, error) {
	records, err := wire.DecodeReplay(content)
	if err != nil {
		return Replay{}, err
	}
	if len(records) < gameStartPosition {
		return Replay{}, LoadError{Record: gameStartPosition, Err: errors.New("the replay records no game start")}
	}

	r := Replay{Records: records}
	r.Seed, r.Names, err = readGameStart(records[gameStartPosition-1])
	if err != nil {
		return Replay{}, LoadError{Record: gameStartPosition, Err: err}
	}

	for i, record := range records[gameStartPosition:] {
		actions, err := recordActions(record)
		if err != nil {
			return Replay{}, LoadError{Record: gameStartPosition + 1 + i, Err: err}
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

func readGameStart(record wire.Map) (engine.Seed, [tile.SeatCount]string, error) {
	var seed engine.Seed
	var names [tile.SeatCount]string
	if eventOf(record) != play.Some(wire.EventGameStarted) {
		return seed, names, errors.New("the second record is no game start")
	}

	gameType, _ := record.Get(wire.KeyGameType)
	if gameType != wire.Int(wire.GameHanchan) {
		return seed, names, errors.New("the game is no hanchan")
	}
	scheme, _ := record.Get(wire.KeyRNGVersion)
	if scheme != wire.Str(engine.RNGVersion) {
		return seed, names, errors.New("the game's randomness is not " + engine.RNGVersion)
	}
	settings, _ := record.Get(wire.KeyGameSettings)
	envelope, _ := settings.(wire.StrMap)
	profile, _ := envelope.Get("id")
	if profile != wire.Int(wire.RulesProfileID) {
		return seed, names, errors.New("the game was played under another rules profile")
	}

	raw, _ := record.Get(wire.KeySeed)
	bin, _ := raw.(wire.Bin)
	if len(bin) != len(seed) {
		return seed, names, errors.New("the game start holds no seed")
	}
	copy(seed[:], bin)

	names, err := readNames(record)
	return seed, names, err
}

func readNames(record wire.Map) ([tile.SeatCount]string, error) {
	var names [tile.SeatCount]string
	raw, _ := record.Get(wire.KeyPlayers)
	players, _ := raw.(wire.Array)
	if len(players) != tile.SeatCount {
		return names, errors.New("the game start names " + strconv.Itoa(len(players)) + " players")
	}

	for _, entry := range players {
		player, _ := entry.(wire.Map)
		s, ok := seatField(player, wire.KeySeat)
		name, _ := player.Str(wire.KeyName)
		if !ok || name == "" || names[s.Index()] != "" {
			return names, errors.New("the game start does not name one player at each seat")
		}
		names[s.Index()] = name
	}
	return names, nil
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
	return nil, errors.New("unknown abort reason " + strconv.Quote(reason))
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
