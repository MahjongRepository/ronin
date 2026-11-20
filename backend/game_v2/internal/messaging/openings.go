package messaging

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

// Opening is the message that opens one seat's decision, built from the decision alone
// (BuildOpening), for the live wait and its re-send on a reconnect alike; the session stamps it
// with the seat's wait id and bank (StampOpening). ReplacesDraw marks a turn after a draw, whose
// opening is the seat's draw itself, with its offers.
type Opening struct {
	Seat         tile.Seat
	Payload      wire.Map
	ReplacesDraw bool
}

// BuildOpening returns the opening of a decision: for a turn after a draw the seat's draw, naming
// what it offers besides a discard (wire.KeyAvailableActions, only when it offers any); for a turn
// after the seat's own chi or pon the kinds kuikae forbids it to discard; for a call its prompt.
func BuildOpening(decision play.Decision) Opening {
	switch context := decision.Context.(type) {
	case play.TurnAfterDraw:
		payload := wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(wire.EventDraw)},
			{Key: wire.KeyPackedMove, Value: wire.Int(wire.PackDraw(decision.Seat, context.Drawn))},
		}
		if offers := drawOffers(decision.Legal); len(offers) > 0 {
			payload = append(payload, wire.Field{Key: wire.KeyAvailableActions, Value: offers})
		}
		return Opening{Seat: decision.Seat, Payload: payload, ReplacesDraw: true}
	case play.TurnAfterCall:
		return Opening{Seat: decision.Seat, Payload: wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(wire.EventTurn)},
			{Key: wire.KeyKuikaeTiles, Value: kindsValue(context.Kuikae)},
		}}
	case play.Call:
		return Opening{Seat: decision.Seat, Payload: callPrompt(decision, context)}
	}
	return Opening{Seat: decision.Seat}
}

func callPrompt(decision play.Decision, context play.Call) wire.Map {
	callType := wire.CallMeld
	switch {
	case context.Source != play.SourceDiscard:
		callType = wire.CallChankan
	case slices.Contains(decision.Legal, play.RonAction()):
		callType = wire.CallRon
	}

	payload := wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventCallPrompt)},
		{Key: wire.KeyCallType, Value: wire.Int(callType)},
		{Key: wire.KeyTileID, Value: tileValue(context.Tile)},
		{Key: wire.KeyFromSeat, Value: seatValue(context.From)},
	}
	switch context.Source {
	case play.SourceAddedKan:
		payload = append(payload, wire.Field{Key: wire.KeyKanType, Value: wire.Str(kanName(play.KanAdded))})
	case play.SourceClosedKan:
		payload = append(payload, wire.Field{Key: wire.KeyKanType, Value: wire.Str(kanName(play.KanClosed))})
	case play.SourceDiscard:
	}

	payload = append(payload, wire.Field{Key: wire.KeyCallerSeat, Value: seatValue(decision.Seat)})
	if calls := availableCalls(decision.Legal); len(calls) > 0 {
		payload = append(payload, wire.Field{Key: wire.KeyAvailableCalls, Value: calls})
	}
	return payload
}

func drawOffers(legal []play.Action) wire.Array {
	var riichi []tile.TileID
	for _, action := range legal {
		if id, ok := action.Tile(); ok && action.Kind() == play.ActionRiichi {
			riichi = append(riichi, id)
		}
	}

	var offers wire.Array
	if len(riichi) > 0 {
		offers = append(offers, offer(wire.ActionRiichi, tilesValue(riichi)))
	}
	if slices.Contains(legal, play.TsumoAction()) {
		offers = append(offers, offer(wire.ActionTsumo, nil))
	}
	if kinds := kanKinds(legal, play.KanClosed); len(kinds) > 0 {
		offers = append(offers, offer(wire.ActionKan, kinds))
	}
	if kinds := kanKinds(legal, play.KanAdded); len(kinds) > 0 {
		offers = append(offers, offer(wire.ActionAddedKan, kinds))
	}
	if slices.Contains(legal, play.KyuushuAction()) {
		offers = append(offers, offer(wire.ActionKyuushu, nil))
	}
	return offers
}

func offer(action wire.PlayerAction, tiles wire.Array) wire.Map {
	m := wire.Map{{Key: wire.KeyAction, Value: wire.Int(action)}}
	if tiles != nil {
		m = append(m, wire.Field{Key: wire.KeyTiles, Value: tiles})
	}
	return m
}

func kanKinds(legal []play.Action, kind play.KanKind) wire.Array {
	var kinds wire.Array
	for _, action := range legal {
		declared, isKan := action.Kan()
		id, _ := action.Tile()
		if isKan && declared == kind {
			kinds = append(kinds, wire.Int(id.Kind()))
		}
	}
	return kinds
}

func availableCalls(legal []play.Action) wire.Array {
	var pons, chis wire.Array
	for _, action := range legal {
		held, ok := action.Held()
		switch {
		case ok && action.Kind() == play.ActionPon:
			pons = append(pons, tilesValue(held[:]))
		case ok && action.Kind() == play.ActionChi:
			chis = append(chis, tilesValue(held[:]))
		}
	}

	var calls wire.Array
	if len(kanKinds(legal, play.KanOpen)) > 0 {
		calls = append(calls, wire.Map{{Key: wire.KeyCallType, Value: wire.Int(wire.MeldCallOpenKan)}})
	}
	for _, option := range []struct {
		call    wire.MeldCallType
		options wire.Array
	}{{wire.MeldCallPon, pons}, {wire.MeldCallChi, chis}} {
		if len(option.options) > 0 {
			calls = append(calls, wire.Map{
				{Key: wire.KeyCallType, Value: wire.Int(option.call)},
				{Key: wire.KeyCallOptions, Value: option.options},
			})
		}
	}
	return calls
}

// Placed is one item of an engine call's output in the order each seat gets it: PlacedEvent or
// Opening.
//
//sumtype:decl
type Placed interface {
	isPlaced()
}

// PlacedEvent is an engine event in its place.
type PlacedEvent struct {
	Emitted play.Emitted
}

func (PlacedEvent) isPlaced() {}
func (Opening) isPlaced()     {}

// PlaceOpenings returns an engine call's events with the openings of the decisions it opened in
// place, so each seat gets its messages in the engine's order: a turn after a draw opens on the
// seat's draw, which its opening replaces, and on nothing when the events hold no draw to that
// seat; every other opening goes after the call's gameplay facts and ahead of its furiten changes,
// in the order given.
func PlaceOpenings(events []play.Emitted, openings []Opening) []Placed {
	var draws [tile.SeatCount]play.Option[Opening]
	var inserted []Placed
	for _, o := range openings {
		if o.ReplacesDraw {
			draws[o.Seat.Index()] = play.Some(o)
		} else {
			inserted = append(inserted, o)
		}
	}

	furitenAt := slices.IndexFunc(events, func(e play.Emitted) bool {
		_, furiten := e.Event.(play.FuritenChanged)
		return furiten
	})
	if furitenAt < 0 {
		furitenAt = len(events)
	}

	placed := make([]Placed, 0, len(events)+len(openings))
	for i, e := range events {
		if i == furitenAt {
			placed = append(placed, inserted...)
		}
		if drew, ok := e.Event.(play.Drew); ok && draws[drew.Seat.Index()].OK {
			placed = append(placed, draws[drew.Seat.Index()].Value)
			continue
		}
		placed = append(placed, PlacedEvent{Emitted: e})
	}
	if furitenAt == len(events) {
		placed = append(placed, inserted...)
	}
	return placed
}

// StampOpening returns a copy of an opening's payload stamped for its recipient: how long, in
// seconds, its timer has run when it is re-sent, its wait id, and the bank its timer starts with.
// The replay never sees these.
func StampOpening(payload wire.Map, waitID int, bank Seconds, elapsed play.Option[float64]) wire.Map {
	stamps := []wire.Field{
		{Key: wire.KeyWaitElapsed, Value: wire.Float(elapsed.Value)},
		{Key: wire.KeyWaitID, Value: wire.Int(waitID)},
		{Key: wire.KeyBankSeconds, Value: bank.value()},
	}
	if !elapsed.OK {
		stamps = stamps[1:]
	}
	return withAll(payload, stamps...)
}
