package messaging

import (
	"errors"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

// Roster is who plays a game, as its messages name them and the engine never does: the game's id,
// each seat's name, and the seats AI players hold from the start, where no participant sits.
type Roster struct {
	GameID string
	Names  [tile.SeatCount]string
	AI     [tile.SeatCount]bool
}

// Table is what the messages of an engine call's events name beyond the events: the game's roster,
// and a seat's record once the call's events are applied, from which a round end takes its round's
// dealer, honba and dora indicators, and a game end its count of rounds and the riichi sticks left
// over.
type Table struct {
	Roster Roster
	Record play.SeatRecord
}

// EventPayload returns the message of one engine event, for the socket and the replay alike. A
// draw carries no live wall count here (ReplayDrawPayload adds it for the replay); a game start
// names no recipient (StampViewerSeat), and a replay's game start record adds what only a replay
// keeps. table gives the Table after the event's call, and is asked for only by a game start, a
// round end and a game end. The error is a wire.InvalidMeldError for a meld the engine cannot have
// built.
func EventPayload(event play.Event, table func() Table) (wire.Map, error) {
	switch e := event.(type) {
	case play.GameStarted:
		return gameStartedPayload(e, table().Roster), nil
	case play.RoundStarted:
		return roundStartedPayload(e), nil
	case play.Drew:
		return eventMap(wire.EventDraw, wire.KeyPackedMove, wire.Int(wire.PackDraw(e.Seat, e.Tile))), nil
	case play.DrewNotice:
		return eventMap(wire.EventDrawNotice, wire.KeySeat, seatValue(e.Seat)), nil
	case play.Discarded:
		packed := wire.PackDiscard(wire.Move{Seat: e.Seat, Tile: e.Tile, Tsumogiri: e.Tsumogiri, Riichi: e.Riichi})
		return eventMap(wire.EventDiscard, wire.KeyPackedMove, wire.Int(packed)), nil
	case play.RiichiDeposited:
		return append(eventMap(wire.EventRiichiDeclared, wire.KeySeat, seatValue(e.Seat)),
			wire.Field{Key: wire.KeyScore, Value: scoreValue(e.Score)},
			wire.Field{Key: wire.KeyRiichiSticks, Value: wire.Int(e.RiichiSticks)}), nil
	case play.FuritenChanged:
		return eventMap(wire.EventFuriten, wire.KeyFuriten, wire.Bool(e.Furiten)), nil
	case play.Called:
		packed, err := packMeld(e.Seat, e.Meld)
		return eventMap(wire.EventMeld, wire.KeyPackedMeld, packed), err
	case play.PaoAssigned:
		return append(eventMap(wire.EventPaoAssigned, wire.KeySeat, seatValue(e.Seat)),
			wire.Field{Key: wire.KeyPaoSeat, Value: seatValue(e.Liable)}), nil
	case play.DoraRevealed:
		return eventMap(wire.EventDoraRevealed, wire.KeyTileID, tileValue(e.Indicator)), nil
	case play.RoundEnded:
		fields, err := roundEndFields(e.Result, e.Scores, e.RiichiSticks, table().Record)
		return append(wire.Map{{Key: wire.KeyEventType, Value: wire.Int(wire.EventRoundEnd)}}, fields...), err
	case play.GameEnded:
		return gameEndedPayload(e.Standings, table().Record), nil
	}
	return nil, errors.New("no event to shape")
}

// ReplayDrawPayload returns a draw's replay record: its message with the live tiles left after it.
func ReplayDrawPayload(drew play.Drew, liveTiles int) wire.Map {
	return wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventDraw)},
		{Key: wire.KeyPackedMove, Value: wire.Int(wire.PackDraw(drew.Seat, drew.Tile))},
		{Key: wire.KeyTilesRemaining, Value: wire.Int(liveTiles)},
	}
}

// ReplaySeatControlPayload returns the replay-only record of seat changing hands: an AI player
// standing in for its participant for reason, or, without one, the participant taking it back.
func ReplaySeatControlPayload(seat tile.Seat, reason play.Option[wire.SeatControlReason]) wire.Map {
	record := eventMap(wire.EventSeatControl, wire.KeySeat, seatValue(seat))
	if !reason.OK {
		return append(record, wire.Field{Key: wire.KeyAIPlayer, Value: wire.Int(0)})
	}
	return append(record,
		wire.Field{Key: wire.KeyAIPlayer, Value: wire.Int(1)},
		wire.Field{Key: wire.KeySeatControlReason, Value: wire.Int(reason.Value)})
}

func eventMap(event wire.EventType, k wire.Key, v wire.Value) wire.Map {
	return wire.Map{{Key: wire.KeyEventType, Value: wire.Int(event)}, {Key: k, Value: v}}
}

func rosterPlayers(roster Roster, standIns [tile.SeatCount]play.Option[wire.SeatControlReason]) wire.Array {
	players := make(wire.Array, 0, tile.SeatCount)
	for _, s := range tile.Seats() {
		ai := 0
		if roster.AI[s.Index()] {
			ai = 1
		}
		player := wire.Map{
			{Key: wire.KeySeat, Value: seatValue(s)},
			{Key: wire.KeyName, Value: wire.Str(roster.Names[s.Index()])},
			{Key: wire.KeyAIPlayer, Value: wire.Int(ai)},
		}
		players = append(players, optionField(player, wire.KeyStandInReason, standIns[s.Index()],
			func(r wire.SeatControlReason) wire.Value { return wire.Int(r) }))
	}
	return players
}

func dealerDice(dice [2]tile.Dice) wire.Array {
	return wire.Array{diceValue(dice[0]), diceValue(dice[1])}
}

func gameStartedPayload(e play.GameStarted, roster Roster) wire.Map {
	return wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventGameStarted)},
		{Key: wire.KeyGameID, Value: wire.Str(roster.GameID)},
		{Key: wire.KeyGameType, Value: wire.Int(wire.GameHanchan)},
		{Key: wire.KeyPlayers, Value: rosterPlayers(roster, [tile.SeatCount]play.Option[wire.SeatControlReason]{})},
		{Key: wire.KeyDealer, Value: seatValue(e.FirstDealer)},
		{Key: wire.KeyDealerDice, Value: dealerDice(e.Dice)},
		{Key: wire.KeyRiichiStickValue, Value: scoreValue(engine.RiichiStickValue)},
	}
}

func roundStartedPayload(e play.RoundStarted) wire.Map {
	var hands [tile.SeatCount]play.Option[[]tile.TileID]
	return dealPayload(e, play.Some(e), hands)
}

func dealPayload(
	e play.RoundStarted, own play.Option[play.RoundStarted], hands [tile.SeatCount]play.Option[[]tile.TileID],
) wire.Map {
	players := make(wire.Array, 0, tile.SeatCount)
	for _, s := range tile.Seats() {
		player := wire.Map{
			{Key: wire.KeySeat, Value: seatValue(s)},
			{Key: wire.KeyScore, Value: scoreValue(e.Scores[s.Index()])},
		}
		players = append(players, optionField(player, wire.KeyTiles, hands[s.Index()], func(ids []tile.TileID) wire.Value {
			return tilesValue(ids)
		}))
	}

	m := wire.Map{{Key: wire.KeyEventType, Value: wire.Int(wire.EventRoundStarted)}}
	m = optionField(m, wire.KeySeat, own, func(e play.RoundStarted) wire.Value { return seatValue(e.Seat) })
	m = append(m,
		wire.Field{Key: wire.KeyWind, Value: wire.Int(e.Header.Wind)},
		wire.Field{Key: wire.KeyRoundNumber, Value: wire.Int(e.Header.RoundNumber)},
		wire.Field{Key: wire.KeyRoundInWind, Value: wire.Int(e.Header.RoundInWind)},
		wire.Field{Key: wire.KeyDealer, Value: seatValue(e.Header.Dealer)},
		wire.Field{Key: wire.KeyCurrentPlayer, Value: seatValue(e.Header.Dealer)},
		wire.Field{Key: wire.KeyDoraIndicators, Value: tilesValue(e.DoraIndicators)},
		wire.Field{Key: wire.KeyHonba, Value: wire.Int(e.Header.Honba)},
		wire.Field{Key: wire.KeyRiichiSticks, Value: wire.Int(e.Header.RiichiSticks)})
	m = optionField(m, wire.KeyMyTiles, own, func(e play.RoundStarted) wire.Value { return tilesValue(e.Hand) })
	return append(m,
		wire.Field{Key: wire.KeyPlayers, Value: players},
		wire.Field{Key: wire.KeyDice, Value: diceValue(e.Header.Dice)},
		wire.Field{Key: wire.KeyTilesRemaining, Value: wire.Int(e.LiveTiles)})
}

func gameEndedPayload(standings play.Standings, record play.SeatRecord) wire.Map {
	placed := make(wire.Array, tile.SeatCount)
	winner := tile.Seat{}
	for _, s := range tile.Seats() {
		place := standings.Placements[s.Index()]
		if place < 1 || place > tile.SeatCount {
			continue
		}
		if place == 1 {
			winner = s
		}
		placed[place-1] = wire.Map{
			{Key: wire.KeySeat, Value: seatValue(s)},
			{Key: wire.KeyScore, Value: scoreValue(standings.Scores[s.Index()])},
			{Key: wire.KeyFinalScore, Value: wire.Int(standings.Points[s.Index()])},
		}
	}

	leftover := leftoverSticks(record)
	return wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventGameEnd)},
		{Key: wire.KeyWinnerSeat, Value: seatValue(winner)},
		{Key: wire.KeyStandings, Value: placed},
		{Key: wire.KeyLeftoverBonus, Value: scoreValue(leftover * engine.RiichiStickValue)},
		{Key: wire.KeyLeftoverRiichi, Value: wire.Int(leftover)},
		{Key: wire.KeyRoundCount, Value: wire.Int(record.Header.RoundNumber + 1)},
		{Key: wire.KeyEndCause, Value: wire.Str(endCauseName(standings.Cause))},
	}
}

func leftoverSticks(record play.SeatRecord) int {
	if len(record.History) == 0 {
		return 0
	}
	last := record.History[len(record.History)-1]
	switch last.Result.(type) {
	case play.Tsumo, play.Ron:
		return 0
	case play.ExhaustiveDraw, play.Abortive:
	}
	return last.Header.RiichiSticks + len(last.RiichiSeats)
}

func endCauseName(cause play.GameEndCause) string {
	switch cause {
	case play.EndTobi:
		return "tobi"
	case play.EndLength:
		return "length"
	case play.EndTargetReached:
		return "target_reached"
	case play.EndExtensionLimit:
		return "extension_limit"
	case play.EndFixedWallsDealt:
		return "fixed_walls_dealt"
	}
	return ""
}

func packMeld(caller tile.Seat, view play.MeldView) (wire.Int, error) {
	packed, err := wire.PackMeld(wire.Meld{
		Caller: caller, Kind: view.Kind, Tiles: view.Tiles, Called: view.Called, From: view.From, Added: view.Added,
	})
	return wire.Int(packed), err
}

func packMelds(caller tile.Seat, views []play.MeldView) (wire.Array, error) {
	packed := make(wire.Array, 0, len(views))
	for _, view := range views {
		meld, err := packMeld(caller, view)
		if err != nil {
			return nil, err
		}
		packed = append(packed, meld)
	}
	return packed, nil
}

// ReplayGameStartedPayload returns the game start's replay record: its message plus what only a
// replay keeps of the start, the aka dora flag, the seed, the randomness scheme and the rules
// envelope.
func ReplayGameStartedPayload(e play.GameStarted, roster Roster, seed engine.Seed) wire.Map {
	return append(gameStartedPayload(e, roster),
		wire.Field{Key: wire.KeyHasAkadora, Value: wire.Bool(true)},
		wire.Field{Key: wire.KeySeed, Value: wire.Bin(seed[:])},
		wire.Field{Key: wire.KeyRNGVersion, Value: wire.Str(engine.RNGVersion)},
		wire.Field{Key: wire.KeyGameSettings, Value: wire.ReplaySettings()})
}

// ReplayRoundStartedPayload returns the one replay record of a deal from its per-seat events: the
// first event's message with every seat's hand beside its score (wire.KeyTiles), naming no seat
// and no hand of its own. A seat without an event shows no hand.
func ReplayRoundStartedPayload(dealt []play.RoundStarted) wire.Map {
	if len(dealt) == 0 {
		return nil
	}
	var hands [tile.SeatCount]play.Option[[]tile.TileID]
	for _, e := range dealt {
		hands[e.Seat.Index()] = play.Some(e.Hand)
	}

	return dealPayload(dealt[0], play.Option[play.RoundStarted]{}, hands)
}
