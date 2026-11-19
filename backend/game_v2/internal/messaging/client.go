package messaging

import (
	"unicode/utf8"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

// ClientMessageType is what a client's message asks, the value of wire.KeyEventType in it. A code
// is never renumbered or reused.
type ClientMessageType uint8

// The client message types. A ping is answered before any routing, so ParseClientMessage refuses
// it as it refuses any other unknown type.
const (
	ClientGameAction ClientMessageType = 3
	ClientReconnect  ClientMessageType = 6
	ClientJoinGame   ClientMessageType = 7
	ClientResync     ClientMessageType = 8
	ClientPing       ClientMessageType = 9
)

// GameAction is a game action's code, the value of wire.KeyAction. A code is never renumbered or
// reused.
type GameAction uint8

// The game actions.
const (
	GameActionDiscard      GameAction = 0
	GameActionRiichi       GameAction = 1
	GameActionTsumo        GameAction = 2
	GameActionRon          GameAction = 3
	GameActionPon          GameAction = 4
	GameActionChi          GameAction = 5
	GameActionKan          GameAction = 6
	GameActionKyuushu      GameAction = 7
	GameActionPass         GameAction = 8
	GameActionConfirmRound GameAction = 9
)

const maxTicketLength = 2000

// ClientMessage is a message a client sent, parsed: GameActionMessage, ReconnectMessage,
// JoinGameMessage or ResyncMessage.
//
//sumtype:decl
type ClientMessage interface {
	isClientMessage()
}

// GameActionMessage is a game action, echoing the id of the wait it answers. Play is the engine
// action it asks for, absent for a round confirmation, which is the session's. Called is the tile
// a pon, chi or open kan names as the one it calls, which the engine action does not carry.
type GameActionMessage struct {
	Action GameAction
	WaitID int
	Play   play.Option[play.Action]
	Called play.Option[tile.TileID]
}

// ReconnectMessage asks to take back the seat its game ticket names.
type ReconnectMessage struct {
	Ticket string
}

// JoinGameMessage asks to join the game its game ticket names.
type JoinGameMessage struct {
	Ticket string
}

// ResyncMessage asks, on the connection that holds a seat, for the seat's snapshot and its pending
// wait again.
type ResyncMessage struct{}

func (GameActionMessage) isClientMessage() {}
func (ReconnectMessage) isClientMessage()  {}
func (JoinGameMessage) isClientMessage()   {}
func (ResyncMessage) isClientMessage()     {}

// InvalidMessageError reports a client message that names no known type or action, or lacks a
// field its action needs, or holds one of the wrong type or out of range.
type InvalidMessageError struct {
	Reason string
}

func (e InvalidMessageError) Error() string {
	return "invalid client message: " + e.Reason
}

// ParseClientMessage reads a decoded client message. A game action needs a wait id of 0 or more;
// a discard, riichi, pon, chi or kan a tile id; a pon or chi its two held tiles
// (wire.KeySequenceTiles); a kan its kan type ("open", "closed" or "added"); a reconnect or join
// a game ticket of 1 to 2000 characters. Fields an action does not use are ignored. A boolean or a
// float is never an integer. An InvalidMessageError otherwise.
func ParseClientMessage(m wire.Map) (ClientMessage, error) {
	typ, ok := intField(m, wire.KeyEventType)
	switch {
	case !ok:
		return nil, InvalidMessageError{Reason: "no message type"}
	case typ == int(ClientGameAction):
		return parseGameAction(m)
	case typ == int(ClientReconnect):
		ticket, err := parseTicket(m)
		return ReconnectMessage{Ticket: ticket}, err
	case typ == int(ClientJoinGame):
		ticket, err := parseTicket(m)
		return JoinGameMessage{Ticket: ticket}, err
	case typ == int(ClientResync):
		return ResyncMessage{}, nil
	}
	return nil, InvalidMessageError{Reason: "unknown message type"}
}

// RefusedWaitID returns the wait id a decoded game action echoes; false for any other message, or
// an id that is not an integer of 0 or more.
func RefusedWaitID(m wire.Map) (int, bool) {
	typ, isInt := intField(m, wire.KeyEventType)
	waitID, ok := intField(m, wire.KeyWaitID)
	return waitID, isInt && typ == int(ClientGameAction) && ok && waitID >= 0
}

func intField(m wire.Map, k wire.Key) (int, bool) {
	v, _ := m.Get(k)
	n, ok := v.(wire.Int)
	return int(n), ok
}

func parseTicket(m wire.Map) (string, error) {
	v, _ := m.Get(wire.KeyGameTicket)
	ticket, ok := v.(wire.Str)
	if !ok {
		return "", InvalidMessageError{Reason: "no game ticket"}
	}
	if length := utf8.RuneCountInString(string(ticket)); length == 0 || length > maxTicketLength {
		return "", InvalidMessageError{Reason: "game ticket of the wrong length"}
	}
	return string(ticket), nil
}

func parseGameAction(m wire.Map) (ClientMessage, error) {
	waitID, ok := intField(m, wire.KeyWaitID)
	if !ok || waitID < 0 {
		return nil, InvalidMessageError{Reason: "no wait id"}
	}
	code, ok := intField(m, wire.KeyAction)
	if !ok || code < int(GameActionDiscard) || code > int(GameActionConfirmRound) {
		return nil, InvalidMessageError{Reason: "unknown game action"}
	}

	return parseAction(m, GameActionMessage{Action: GameAction(code), WaitID: waitID})
}

func parseAction(m wire.Map, message GameActionMessage) (ClientMessage, error) {
	switch message.Action {
	case GameActionTsumo:
		message.Play = play.Some(play.TsumoAction())
	case GameActionRon:
		message.Play = play.Some(play.RonAction())
	case GameActionKyuushu:
		message.Play = play.Some(play.KyuushuAction())
	case GameActionPass:
		message.Play = play.Some(play.PassAction())
	case GameActionConfirmRound:
	case GameActionDiscard, GameActionRiichi:
		return parseDiscard(m, message)
	case GameActionPon, GameActionChi:
		return parseCall(m, message)
	case GameActionKan:
		return parseKan(m, message)
	}
	return message, nil
}

func parseDiscard(m wire.Map, message GameActionMessage) (ClientMessage, error) {
	id, err := tileField(m)
	if err != nil {
		return nil, err
	}
	message.Play = play.Some(play.DiscardAction(id))
	if message.Action == GameActionRiichi {
		message.Play = play.Some(play.RiichiAction(id))
	}
	return message, nil
}

func parseCall(m wire.Map, message GameActionMessage) (ClientMessage, error) {
	id, err := tileField(m)
	if err != nil {
		return nil, err
	}
	held, err := heldTiles(m)
	if err != nil {
		return nil, err
	}

	message.Called = play.Some(id)
	message.Play = play.Some(play.PonAction(held))
	if message.Action == GameActionChi {
		message.Play = play.Some(play.ChiAction(held))
	}
	return message, nil
}

func tileOf(v wire.Value) (tile.TileID, bool) {
	n, ok := v.(wire.Int)
	if !ok {
		return tile.TileID{}, false
	}
	return tile.NewTileID(int(n))
}

func tileField(m wire.Map) (tile.TileID, error) {
	v, _ := m.Get(wire.KeyTileID)
	id, ok := tileOf(v)
	if !ok {
		return tile.TileID{}, InvalidMessageError{Reason: "no tile id from 0 to 135"}
	}
	return id, nil
}

func heldTiles(m wire.Map) ([2]tile.TileID, error) {
	var held [2]tile.TileID
	v, _ := m.Get(wire.KeySequenceTiles)
	tiles, ok := v.(wire.Array)
	if !ok || len(tiles) != len(held) {
		return held, InvalidMessageError{Reason: "no two held tiles"}
	}
	for i, t := range tiles {
		held[i], ok = tileOf(t)
		if !ok {
			return held, InvalidMessageError{Reason: "a held tile is no tile id from 0 to 135"}
		}
	}
	return held, nil
}

func parseKan(m wire.Map, message GameActionMessage) (ClientMessage, error) {
	id, err := tileField(m)
	if err != nil {
		return nil, err
	}
	v, _ := m.Get(wire.KeyActionKanType)
	name, _ := v.(wire.Str)
	kind, ok := kanKindOf(string(name))
	if !ok {
		return nil, InvalidMessageError{Reason: "no kan type"}
	}

	message.Play = play.Some(play.KanAction(kind, id))
	if kind == play.KanOpen {
		message.Called = play.Some(id)
	}
	return message, nil
}

const (
	kanOpenName   = "open"
	kanClosedName = "closed"
	kanAddedName  = "added"
)

func kanKindOf(name string) (play.KanKind, bool) {
	switch name {
	case kanOpenName:
		return play.KanOpen, true
	case kanClosedName:
		return play.KanClosed, true
	case kanAddedName:
		return play.KanAdded, true
	}
	return play.KanOpen, false
}

func kanName(kind play.KanKind) string {
	switch kind {
	case play.KanOpen:
		return kanOpenName
	case play.KanClosed:
		return kanClosedName
	case play.KanAdded:
		return kanAddedName
	}
	return ""
}
