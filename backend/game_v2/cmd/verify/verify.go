package main

import (
	"bytes"
	"errors"
	"fmt"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

var errNoGameEnd = errors.New("replay records no game end")

type storedRecord struct {
	position int
	record   wire.Map
}

func verifyGame(replays replayfile.Dir, gameID string) error {
	compressed, err := replays.Read(gameID)
	if err != nil {
		return err
	}

	content, err := replayfile.Decompress(compressed, wire.MaxReplayBytes)
	if err != nil {
		return fmt.Errorf("read replay %s: %w", gameID, err)
	}

	loaded, err := replay.Load(content)
	if err != nil {
		return fmt.Errorf("load replay %s: %w", gameID, err)
	}

	if !slices.ContainsFunc(loaded.Records, isGameEnd) {
		return errNoGameEnd
	}

	steps, err := replay.Run(engine.Setup{Ruleset: loaded.Ruleset, Walls: play.Seeded{Seed: loaded.Seed}}, loaded.Actions)
	if err != nil {
		return fmt.Errorf("run replay %s: %w", gameID, err)
	}

	roster := messaging.Roster{GameID: gameID, Names: loaded.Names, AI: loaded.AI}
	replayed, err := replayedRecords(loaded.Seed, roster, steps)
	if err != nil {
		return fmt.Errorf("record replay %s: %w", gameID, err)
	}

	return recordMismatch(playedRecords(loaded.Records), replayed)
}

func isGameEnd(record wire.Map) bool {
	event, _ := record.Get(wire.KeyEventType)
	return event == wire.Int(wire.EventGameEnd)
}

func playedRecords(records []wire.Map) []storedRecord {
	var played []storedRecord
	for i, record := range records[1:] {
		event, _ := record.Get(wire.KeyEventType)
		if event != wire.Int(wire.EventSeatControl) {
			played = append(played, storedRecord{position: i + 2, record: record})
		}
	}

	return played
}

func replayedRecords(seed engine.Seed, roster messaging.Roster, steps []replay.Step) ([]wire.Map, error) {
	log := messaging.NewReplayLog(seed, roster)
	for _, step := range steps {
		table := func() messaging.Table {
			return messaging.Table{Roster: roster, Record: step.Game.View(tile.Seats()[0]).Record}
		}
		if err := log.Collect(step.Events, table); err != nil {
			return nil, err
		}
	}

	return log.Records(), nil
}

func recordMismatch(recorded []storedRecord, replayed []wire.Map) error {
	for i := range min(len(recorded), len(replayed)) {
		stored := recorded[i]
		same, err := sameRecord(stored.record, replayed[i])
		if err != nil {
			return fmt.Errorf("record %d: %w", stored.position, err)
		}

		if !same {
			return fmt.Errorf("record %d differs:\n    recorded: %v\n    replayed: %v", stored.position, stored.record,
				replayed[i])
		}
	}

	if len(recorded) != len(replayed) {
		return fmt.Errorf("recorded %d records besides seat control, replay emitted %d", len(recorded), len(replayed))
	}

	return nil
}

func sameRecord(recorded, replayed wire.Map) (bool, error) {
	want, err := messaging.EncodeReplayRecords([]wire.Map{recorded})
	if err != nil {
		return false, err
	}

	got, err := messaging.EncodeReplayRecords([]wire.Map{replayed})
	if err != nil {
		return false, err
	}

	return bytes.Equal(want, got), nil
}
