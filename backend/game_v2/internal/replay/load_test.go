package replay_test

import (
	"errors"
	"reflect"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func with(m wire.Map, k wire.Key, v wire.Value) wire.Map {
	edited := make(wire.Map, 0, len(m))
	for _, f := range m {
		if f.Key == k {
			f.Value = v
		}

		edited = append(edited, f)
	}

	return edited
}

func TestLoad_WhenTheGameStartIsNotOfThisServersRules_ShouldRefuseItsRecord(t *testing.T) {
	start := messaging.ReplayGameStartedPayload(play.GameStarted{}, testRoster, engine.Seed{7})
	players, _ := start.Get(wire.KeyPlayers)
	twiceSeated := append(wire.Array{}, players.(wire.Array)...)
	twiceSeated[1] = with(twiceSeated[1].(wire.Map), wire.KeySeat, wire.Int(0))

	cases := []struct {
		name  string
		start wire.Map
	}{
		{"a migrated game's rules profile", with(start, wire.KeyGameSettings, wire.StrMap{
			{Key: "id", Value: wire.Int(wire.MigratedRulesProfileID)}, {Key: "overrides", Value: wire.StrMap{}},
		})},
		{"another randomness scheme", with(start, wire.KeyRNGVersion, wire.Str("mt19937"))},
		{"a seat named twice", with(start, wire.KeyPlayers, twiceSeated)},
		{"a draw in its place", messaging.ReplayDrawPayload(play.Drew{}, 0)},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			content, err := messaging.EncodeReplayRecords([]wire.Map{c.start})
			if err != nil {
				t.Fatalf("EncodeReplayRecords error = %v", err)
			}

			_, err = replay.Load(content)
			if got, ok := errors.AsType[replay.LoadError](err); !ok || got.Record != 2 {
				t.Errorf("Load error = %v, want a LoadError at record 2", err)
			}
		})
	}
}

func TestLoad_WhenARonRobsAClosedKan_ShouldNameTheKanByTheRobbedCopy(t *testing.T) {
	robbedCopy := id(t, 35)
	kan := play.Called{Seat: seat(t, 1), Meld: play.MeldView{
		Kind: play.MeldClosedKan, Tiles: []tile.TileID{id(t, 32), id(t, 33), id(t, 34), robbedCopy},
	}}
	robbed := play.RoundEnded{Result: play.Ron{Discarder: seat(t, 1), Wins: []play.WinResult{{
		Winner: seat(t, 2), Loser: play.Some(seat(t, 1)), WinTile: robbedCopy, Value: play.Yakuman{Count: 1},
	}}}}
	table := func() messaging.Table { return messaging.Table{Roster: testRoster} }
	records := []wire.Map{messaging.ReplayGameStartedPayload(play.GameStarted{}, testRoster, engine.Seed{7})}
	for _, event := range []play.Event{kan, robbed} {
		record, err := messaging.EventPayload(event, table)
		if err != nil {
			t.Fatalf("EventPayload(%T) error = %v", event, err)
		}

		records = append(records, record)
	}

	loaded := loadRecords(t, records)

	want := []replay.SeatAction{
		{Seat: seat(t, 1), Action: play.KanAction(play.KanClosed, robbedCopy)},
		{Seat: seat(t, 2), Action: play.RonAction()},
	}
	if diff := cmp.Diff(want, loaded.Actions, cmp.Exporter(func(reflect.Type) bool { return true })); diff != "" {
		t.Errorf("Load actions (-want +got):\n%s", diff)
	}
}
