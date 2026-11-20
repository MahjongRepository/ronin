package server

import (
	"encoding/json"
	"regexp"
	"strconv"
	"unicode/utf8"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
)

const (
	defaultAIPlayers = 3
	maxNameLength    = 50
	maxUserIDLength  = 100
	maxTicketLength  = 2000
)

var strictInteger = regexp.MustCompile(`^-?[0-9]+$`)

type createGameRequest struct {
	gameID  string
	players []session.PlayerSpec
}

// parseCreateGame reads the lobby's game creation body as the Python server's model did: exactly
// its keys, no field of another JSON type, lengths in characters, and the players unique.
func parseCreateGame(body []byte) (createGameRequest, bool) {
	fields, ok := objectOf(body, "game_id", "num_ai_players", "players")
	if !ok {
		return createGameRequest{}, false
	}

	gameID, ok := stringOf(fields["game_id"], 0, 0)
	if !ok || !store.IsValidGameID(gameID) {
		return createGameRequest{}, false
	}
	aiPlayers, ok := aiPlayersOf(fields)
	if !ok {
		return createGameRequest{}, false
	}
	players, ok := playersOf(fields["players"])
	if !ok || len(players) != tile.SeatCount-aiPlayers || !unique(players) {
		return createGameRequest{}, false
	}
	return createGameRequest{gameID: gameID, players: players}, true
}

func objectOf(data []byte, keys ...string) (map[string]json.RawMessage, bool) {
	if !utf8.Valid(data) {
		return nil, false
	}
	var fields map[string]json.RawMessage
	err := json.Unmarshal(data, &fields)
	if err != nil || fields == nil {
		return nil, false
	}

	allowed := make(map[string]bool, len(keys))
	for _, k := range keys {
		allowed[k] = true
	}
	for k := range fields {
		if !allowed[k] {
			return nil, false
		}
	}
	return fields, true
}

func stringOf(raw json.RawMessage, minLength, maxLength int) (string, bool) {
	if len(raw) == 0 || raw[0] != '"' {
		return "", false
	}
	var s string
	err := json.Unmarshal(raw, &s)
	if err != nil {
		return "", false
	}

	length := utf8.RuneCountInString(s)
	if length < minLength || (maxLength > 0 && length > maxLength) {
		return "", false
	}
	return s, true
}

func aiPlayersOf(fields map[string]json.RawMessage) (int, bool) {
	raw, present := fields["num_ai_players"]
	if !present {
		return defaultAIPlayers, true
	}
	if !strictInteger.Match(raw) {
		return 0, false
	}
	n, err := strconv.Atoi(string(raw))
	if err != nil || n < 0 || n > defaultAIPlayers {
		return 0, false
	}
	return n, true
}

func playersOf(raw json.RawMessage) ([]session.PlayerSpec, bool) {
	if len(raw) == 0 || raw[0] != '[' {
		return nil, false
	}
	var items []json.RawMessage
	err := json.Unmarshal(raw, &items)
	if err != nil || len(items) == 0 || len(items) > tile.SeatCount {
		return nil, false
	}

	players := make([]session.PlayerSpec, 0, len(items))
	for _, item := range items {
		player, ok := playerOf(item)
		if !ok {
			return nil, false
		}
		players = append(players, player)
	}
	return players, true
}

func playerOf(raw json.RawMessage) (session.PlayerSpec, bool) {
	fields, ok := objectOf(raw, "name", "user_id", "game_ticket")
	if !ok {
		return session.PlayerSpec{}, false
	}
	name, nameOK := stringOf(fields["name"], 1, maxNameLength)
	userID, userOK := stringOf(fields["user_id"], 1, maxUserIDLength)
	ticket, ticketOK := stringOf(fields["game_ticket"], 1, maxTicketLength)
	if !nameOK || !userOK || !ticketOK {
		return session.PlayerSpec{}, false
	}
	return session.PlayerSpec{Name: name, UserID: userID, Ticket: ticket}, true
}

func unique(players []session.PlayerSpec) bool {
	names := map[string]bool{}
	userIDs := map[string]bool{}
	tickets := map[string]bool{}
	for _, p := range players {
		if names[p.Name] || userIDs[p.UserID] || tickets[p.Ticket] {
			return false
		}
		names[p.Name], userIDs[p.UserID], tickets[p.Ticket] = true, true, true
	}
	return true
}
