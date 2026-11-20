package replay_test

import (
	"errors"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

func replaced(m wire.Map, k wire.Key, v wire.Value) wire.Map {
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
	twiceSeated[1] = replaced(twiceSeated[1].(wire.Map), wire.KeySeat, wire.Int(0))

	cases := []struct {
		name  string
		start wire.Map
	}{
		{"a migrated game's rules profile", replaced(start, wire.KeyGameSettings, wire.StrMap{
			{Key: "id", Value: wire.Int(wire.MigratedRulesProfileID)}, {Key: "overrides", Value: wire.StrMap{}},
		})},
		{"another randomness scheme", replaced(start, wire.KeyRNGVersion, wire.Str("mt19937"))},
		{"a seat named twice", replaced(start, wire.KeyPlayers, twiceSeated)},
		{"a draw in its place", messaging.ReplayDrawPayload(play.Drew{}, 0)},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			_, err := replay.Load(encodeRecords(t, []wire.Map{wire.VersionRecord(), c.start}))

			if got, ok := errors.AsType[replay.LoadError](err); !ok || got.Record != 2 {
				t.Errorf("Load error = %v, want a LoadError at record 2", err)
			}
		})
	}
}
