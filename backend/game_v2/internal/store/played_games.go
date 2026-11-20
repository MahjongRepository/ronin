package store

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"
)

// GameStart is what a game's row records from its start on.
type GameStart struct {
	GameID    string
	StartedAt time.Time
	GameType  string
	Seats     []Player
}

// Player is the one who sits at a seat; an AI seat has no UserID.
type Player struct {
	Name   string
	UserID string
}

// Placement is one seat's place at a completed game's end; FinalScore is in tenths of a point.
type Placement struct {
	Seat       int
	Score      int
	FinalScore int
}

// Result is how a completed game ended: its placements from first to last.
type Result struct {
	RoundsPlayed int
	Placements   []Placement
}

type endReason string

const (
	endCompleted endReason = "completed"
	endAbandoned endReason = "abandoned"
	endError     endReason = "error"
)

// ErrUnknownSeat is returned for a placement whose seat the game's start has no player for.
var ErrUnknownSeat = errors.New("placement seat has no player at the game's start")

const (
	insertStartSQL = "INSERT INTO played_games (id, started_at, ended_at, end_reason, data) VALUES (?, ?, ?, ?, ?) " +
		"ON CONFLICT (id) DO NOTHING"
	upsertFinishSQL = "INSERT INTO played_games (id, started_at, ended_at, end_reason, data) VALUES (?, ?, ?, ?, ?) " +
		"ON CONFLICT (id) DO UPDATE SET " +
		"ended_at = excluded.ended_at, end_reason = excluded.end_reason, data = excluded.data " +
		"WHERE played_games.ended_at IS NULL"
)

// FinalScoreUnit marks a row's `data` as holding final scores in tenths: every row this package
// writes ends with it, and a row without it holds the Python server's whole points.
const FinalScoreUnit = "tenths"

type playedGameJSON struct {
	GameID         string         `json:"game_id"`
	StartedAt      string         `json:"started_at"`
	EndedAt        *string        `json:"ended_at"`
	EndReason      *endReason     `json:"end_reason"`
	GameType       string         `json:"game_type"`
	RoundsPlayed   *int           `json:"num_rounds_played"`
	Standings      []standingJSON `json:"standings"`
	FinalScoreUnit string         `json:"final_score_unit,omitempty"`
}

type standingJSON struct {
	Name       string `json:"name"`
	Seat       int    `json:"seat"`
	UserID     string `json:"user_id"`
	Score      *int   `json:"score"`
	FinalScore *int   `json:"final_score"`
}

type finish struct {
	endedAt time.Time
	reason  endReason
}

// RecordStart inserts a game's row as it starts, its standings the players in seat order. A game
// already recorded keeps its row, and the start is logged at warning level and dropped.
func (db *DB) RecordStart(ctx context.Context, start GameStart) error {
	data, err := playedGameData(start, nil, nil, seatOrderStandings(start))
	if err != nil {
		return err
	}

	return db.write(ctx, insertStartSQL, start, nil, data, "game already recorded, ignoring its start")
}

// RecordCompleted finishes a completed game's row, its standings the result's placements with
// each seat's player from the start. It returns ErrUnknownSeat for a placement of no seated player.
func (db *DB) RecordCompleted(ctx context.Context, start GameStart, endedAt time.Time, result Result) error {
	standings := make([]standingJSON, 0, len(result.Placements))
	for _, p := range result.Placements {
		if p.Seat < 0 || p.Seat >= len(start.Seats) {
			return fmt.Errorf("record game %s: seat %d: %w", start.GameID, p.Seat, ErrUnknownSeat)
		}
		player := start.Seats[p.Seat]
		standings = append(standings, standingJSON{
			Name:       player.Name,
			Seat:       p.Seat,
			UserID:     player.UserID,
			Score:      new(p.Score),
			FinalScore: new(p.FinalScore),
		})
	}

	return db.recordFinish(ctx, start, finish{endedAt, endCompleted}, new(result.RoundsPlayed), standings)
}

// RecordAbandoned finishes the row of a game nobody connected stayed in, its standings kept in seat
// order without scores.
func (db *DB) RecordAbandoned(ctx context.Context, start GameStart, endedAt time.Time) error {
	return db.recordFinish(ctx, start, finish{endedAt, endAbandoned}, nil, seatOrderStandings(start))
}

// RecordFailed finishes the row of a game ended by a server fault, its standings kept in seat order
// without scores.
func (db *DB) RecordFailed(ctx context.Context, start GameStart, endedAt time.Time) error {
	return db.recordFinish(ctx, start, finish{endedAt, endError}, nil, seatOrderStandings(start))
}

func (db *DB) recordFinish(
	ctx context.Context, start GameStart, end finish, roundsPlayed *int, standings []standingJSON,
) error {
	data, err := playedGameData(start, &end, roundsPlayed, standings)
	if err != nil {
		return err
	}

	return db.write(ctx, upsertFinishSQL, start, &end, data, "game already finished, keeping its first finish")
}

func (db *DB) write(ctx context.Context, query string, start GameStart, end *finish, data, ignored string) error {
	var endedAt, reason any
	if end != nil {
		endedAt, reason = columnTime(end.endedAt), string(end.reason)
	}

	result, err := db.conn.ExecContext(ctx, query, start.GameID, columnTime(start.StartedAt), endedAt, reason, data)
	if err != nil {
		return fmt.Errorf("record game %s: %w", start.GameID, err)
	}

	written, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("record game %s: %w", start.GameID, err)
	}
	if written == 0 {
		db.logger.Warn(ignored, "game_id", start.GameID)
	}
	return nil
}

func seatOrderStandings(start GameStart) []standingJSON {
	standings := make([]standingJSON, 0, len(start.Seats))
	for seat, player := range start.Seats {
		standings = append(standings, standingJSON{Name: player.Name, Seat: seat, UserID: player.UserID})
	}
	return standings
}

func playedGameData(start GameStart, end *finish, roundsPlayed *int, standings []standingJSON) (string, error) {
	game := playedGameJSON{
		GameID:         start.GameID,
		StartedAt:      jsonTime(start.StartedAt),
		GameType:       start.GameType,
		RoundsPlayed:   roundsPlayed,
		Standings:      standings,
		FinalScoreUnit: FinalScoreUnit,
	}
	if end != nil {
		game.EndedAt, game.EndReason = new(jsonTime(end.endedAt)), &end.reason
	}
	return encodeGame(game)
}

func encodeGame(game playedGameJSON) (string, error) {
	var data bytes.Buffer
	encoder := json.NewEncoder(&data)
	encoder.SetEscapeHTML(false)
	err := encoder.Encode(game)
	if err != nil {
		return "", fmt.Errorf("encode game %s: %w", game.GameID, err)
	}
	return string(bytes.TrimSuffix(data.Bytes(), []byte("\n"))), nil
}

func columnTime(t time.Time) string {
	return isoformat(t, "+00:00")
}

func jsonTime(t time.Time) string {
	return isoformat(t, "Z")
}

func isoformat(t time.Time, utcSuffix string) string {
	utc := t.UTC()
	layout := "2006-01-02T15:04:05"
	if utc.Nanosecond()/int(time.Microsecond) != 0 {
		layout += ".000000"
	}
	return utc.Format(layout) + utcSuffix
}
