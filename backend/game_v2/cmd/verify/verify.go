package main

import (
	"bytes"
	"errors"
	"fmt"
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

var errNoGameEnd = errors.New("replay records no game end")

func verifyGame(replays store.Replays, gameID string) error {
	compressed, err := replays.Read(gameID)
	if err != nil {
		return err
	}
	content, err := store.DecompressReplay(compressed, wire.MaxReplayBytes)
	if err != nil {
		return fmt.Errorf("read replay %s: %w", gameID, err)
	}
	loaded, err := replay.Load(content)
	if err != nil {
		return fmt.Errorf("load replay: %w", err)
	}

	recorded := recordedOutcomes(loaded.Records)
	if !slices.ContainsFunc(recorded, isGameEnd) {
		return errNoGameEnd
	}

	steps, err := replay.Run(engine.Setup{Walls: play.Seeded{Seed: loaded.Seed}}, loaded.Actions)
	if err != nil {
		return fmt.Errorf("replay failed: %w", err)
	}
	replayed, err := replayedOutcomes(steps)
	if err != nil {
		return fmt.Errorf("replay failed: %w", err)
	}
	return outcomeMismatch(recorded, replayed)
}

func isOutcome(record wire.Map) bool {
	event, _ := record.Get(wire.KeyEventType)
	return event == wire.Int(wire.EventRoundEnd) || event == wire.Int(wire.EventGameEnd)
}

func isGameEnd(record wire.Map) bool {
	event, _ := record.Get(wire.KeyEventType)
	return event == wire.Int(wire.EventGameEnd)
}

func recordedOutcomes(records []wire.Map) []wire.Map {
	var outcomes []wire.Map
	for _, record := range records {
		if isOutcome(record) {
			outcomes = append(outcomes, record)
		}
	}
	return outcomes
}

func replayedOutcomes(steps []replay.Step) ([]wire.Map, error) {
	var outcomes []wire.Map
	for _, step := range steps {
		table := messaging.Table{Record: step.Game.View(tile.Seats()[0]).Record}
		for _, emitted := range step.Events {
			switch emitted.Event.(type) {
			case play.RoundEnded, play.GameEnded:
			case play.GameStarted, play.RoundStarted, play.Drew, play.DrewNotice, play.Discarded, play.RiichiDeposited,
				play.FuritenChanged, play.Called, play.PaoAssigned, play.DoraRevealed:
				continue
			}
			outcome, err := messaging.EventPayload(emitted.Event, table)
			if err != nil {
				return nil, err
			}
			outcomes = append(outcomes, outcome)
		}
	}
	return outcomes, nil
}

func outcomeMismatch(recorded, replayed []wire.Map) error {
	for i := range min(len(recorded), len(replayed)) {
		same, err := sameRecord(recorded[i], replayed[i])
		if err != nil {
			return fmt.Errorf("outcome %d: %w", i, err)
		}
		if !same {
			return fmt.Errorf("outcome %d differs:\n    recorded: %v\n    replayed: %v", i, recorded[i], replayed[i])
		}
	}
	if len(recorded) != len(replayed) {
		return errors.New("recorded " + strconv.Itoa(len(recorded)) + " outcomes, replay emitted " +
			strconv.Itoa(len(replayed)))
	}
	return nil
}

func sameRecord(recorded, replayed wire.Map) (bool, error) {
	want, err := wire.Encode(recorded)
	if err != nil {
		return false, err
	}
	got, err := wire.Encode(replayed)
	if err != nil {
		return false, err
	}
	return bytes.Equal(want, got), nil
}
