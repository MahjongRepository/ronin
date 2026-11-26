package messaging

import (
	"unicode/utf8"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

// A code is never renumbered or reused.
type ClientMessageType uint8

const (
	ClientGameAction ClientMessageType = 3
	ClientReconnect  ClientMessageType = 6
	ClientJoinGame   ClientMessageType = 7
	ClientResync     ClientMessageType = 8
	ClientPing       ClientMessageType = 9
)

// A code is never renumbered or reused.
type GameAction uint8

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

//sumtype:decl
type ClientMessage interface {
	isClientMessage()
}

type GameActionMessage struct {
	Action GameAction
	WaitID int
	Play   play.Option[play.Action]
	Called play.Option[tile.TileID]
}

type ReconnectMessage struct {
	Ticket string
}

type JoinGameMessage struct {
	Ticket string
}

type ResyncMessage struct{}

func (GameActionMessage) isClientMessage() {}
func (ReconnectMessage) isClientMessage()  {}
func (JoinGameMessage) isClientMessage()   {}
func (ResyncMessage) isClientMessage()     {}

type InvalidMessageError struct {
	Reason string
}

func (e InvalidMessageError) Error() string {
	return "invalid client message: " + e.Reason
}

func ParseClientMessage(m wire.Map) (ClientMessage, error) {
	typ, ok := m.Int(wire.KeyEventType)
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

func RefusedWaitID(m wire.Map) (int, bool) {
	typ, isInt := m.Int(wire.KeyEventType)
	waitID, ok := m.Int(wire.KeyWaitID)
	return waitID, isInt && typ == int(ClientGameAction) && ok && waitID >= 0
}

func parseTicket(m wire.Map) (string, error) {
	ticket, ok := m.Str(wire.KeyGameTicket)
	if !ok {
		return "", InvalidMessageError{Reason: "no game ticket"}
	}

	if length := utf8.RuneCountInString(ticket); length == 0 || length > maxTicketLength {
		return "", InvalidMessageError{Reason: "game ticket of the wrong length"}
	}

	return ticket, nil
}

func parseGameAction(m wire.Map) (ClientMessage, error) {
	waitID, ok := m.Int(wire.KeyWaitID)
	if !ok || waitID < 0 {
		return nil, InvalidMessageError{Reason: "no wait id"}
	}

	code, ok := m.Int(wire.KeyAction)
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

	name, _ := m.Str(wire.KeyActionKanType)
	kind, ok := kanKindOf(name)
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
