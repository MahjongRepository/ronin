package seam_test

import (
	"encoding/binary"
	"strconv"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	selfPlayGames     = 32
	tracedSeededGames = 16
	selfPlayMaxSteps  = 50000
)

func selfPlaySeed(game uint64) engine.Seed {
	var seed engine.Seed
	for i := range seed {
		seed[i] = 0x5a
	}
	binary.LittleEndian.PutUint64(seed[:8], game)
	return seed
}

func selfPlayAgents(game uint64) agents {
	var seated agents
	for i := range seated {
		at := uint64(i)
		if game>>at&1 == 0 {
			seated[i] = newRandomLegal(game*tile.SeatCount + at)
		} else {
			seated[i] = tsumogiri{}
		}
	}
	return seated
}

func TestPlayGameChecked_WhenRandomAndTsumogiriAgentsPlaySeededHanchans_ShouldKeepEveryInvariantToTheEnd(t *testing.T) {
	for game := uint64(tracedSeededGames); game < selfPlayGames; game++ {
		t.Run(strconv.FormatUint(game, 10), func(t *testing.T) {
			t.Parallel()
			seed := selfPlaySeed(game)
			g, initial := newGame(t, engine.Setup{Walls: play.Seeded{Seed: seed}})

			standings, err := playGameChecked(&g, initial, selfPlayAgents(game), noSink{}, selfPlayMaxSteps)
			if err != nil {
				t.Fatalf("seed %v: %v", seed, err)
			}

			assertEqual[play.Awaiting](t, "awaiting", g.Awaiting(), play.AwaitingGameOver{})
			assertEqual(t, "final score total", scoreTotal(standings.Scores), tablePoints)
		})
	}
}
