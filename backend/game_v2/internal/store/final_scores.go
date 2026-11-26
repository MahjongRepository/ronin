package store

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
)

const FinalScoreFactor = 10

type ScoreMigration struct {
	Converted     int
	AlreadyTenths int
	Unscored      int
	Failed        []RowFailure
}

// RowFailure is a row MigrateFinalScores left as it was, and why.
type RowFailure struct {
	GameID string
	Err    error
}

func (f RowFailure) Error() string {
	return "played game " + f.GameID + ": " + f.Err.Error()
}

var (
	ErrRowData       = errors.New("data is not the played-game JSON this server writes")
	ErrUnknownMarker = errors.New("final_score_unit names no unit this server writes")
)

type rowOutcome uint8

const (
	rowConverted rowOutcome = iota
	rowInTenths
	rowUnscored
)

type storedRow struct {
	id   string
	data string
}

func (db *DB) MigrateFinalScores(ctx context.Context, apply bool) (migration ScoreMigration, err error) {
	tx, err := db.conn.BeginTx(ctx, nil)
	if err != nil {
		return ScoreMigration{}, fmt.Errorf("migrate final scores: %w", err)
	}

	committed := false
	defer func() {
		if !committed {
			err = errors.Join(err, ignoreDone(tx.Rollback()))
		}
	}()

	rows, err := storedRows(ctx, tx, "SELECT id, data FROM played_games ORDER BY id")
	if err != nil {
		return ScoreMigration{}, fmt.Errorf("migrate final scores: %w", err)
	}

	for _, row := range rows {
		data, outcome, rowErr := migratedRow(row.data)

		switch {
		case rowErr != nil:
			migration.Failed = append(migration.Failed, RowFailure{GameID: row.id, Err: rowErr})
		case outcome == rowInTenths:
			migration.AlreadyTenths++
		case outcome == rowUnscored:
			migration.Unscored++
		default:
			_, err = tx.ExecContext(ctx, "UPDATE played_games SET data = ? WHERE id = ?", data, row.id)
			if err != nil {
				return ScoreMigration{}, fmt.Errorf("migrate final scores of %s: %w", row.id, err)
			}
			migration.Converted++
		}
	}

	if !apply {
		return migration, nil
	}

	err = tx.Commit()
	if err != nil {
		return ScoreMigration{}, fmt.Errorf("migrate final scores: %w", err)
	}

	committed = true

	return migration, nil
}

func ignoreDone(err error) error {
	if errors.Is(err, sql.ErrTxDone) {
		return nil
	}

	return err
}

type rowQuerier interface {
	QueryContext(ctx context.Context, query string, args ...any) (*sql.Rows, error)
}

func storedRows(ctx context.Context, q rowQuerier, query string) (stored []storedRow, err error) {
	rows, err := q.QueryContext(ctx, query)
	if err != nil {
		return nil, err
	}
	defer func() { err = errors.Join(err, rows.Close()) }()

	for rows.Next() {
		var row storedRow
		err = rows.Scan(&row.id, &row.data)
		if err != nil {
			return nil, err
		}
		stored = append(stored, row)
	}

	return stored, rows.Err()
}

func migratedRow(data string) (string, rowOutcome, error) {
	game, err := decodeGame(data)
	if err != nil {
		return "", 0, err
	}

	switch game.FinalScoreUnit {
	case FinalScoreUnit:
		return "", rowInTenths, nil
	case "":
	default:
		return "", 0, ErrUnknownMarker
	}

	written, err := encodeGame(game)
	if err != nil || written != data {
		return "", 0, ErrRowData
	}

	scored := false
	for i, standing := range game.Standings {
		if standing.FinalScore != nil {
			game.Standings[i].FinalScore = new(*standing.FinalScore * FinalScoreFactor)
			scored = true
		}
	}

	if !scored {
		return "", rowUnscored, nil
	}

	game.FinalScoreUnit = FinalScoreUnit
	converted, err := encodeGame(game)
	return converted, rowConverted, err
}

func decodeGame(data string) (playedGameJSON, error) {
	decoder := json.NewDecoder(strings.NewReader(data))
	decoder.DisallowUnknownFields()

	var game playedGameJSON
	err := decoder.Decode(&game)
	if err != nil {
		return playedGameJSON{}, fmt.Errorf("%w: %w", ErrRowData, err)
	}

	if decoder.Decode(&struct{}{}) != io.EOF {
		return playedGameJSON{}, ErrRowData
	}

	return game, nil
}
