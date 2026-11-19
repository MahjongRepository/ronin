package record_test

import (
	"encoding/binary"
	"reflect"
	"slices"
	"strconv"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/record"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rng"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/shanten"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	parityGames         = 32
	maxSteps            = 50_000
	viewStartEvery      = 23
	viewRecordBatches   = 160
	callOdds            = 6
	kanOdds             = 2
	greedyStartsModulus = 14
	seedFill            = 0xa5
)

func paritySeed(gameNumber uint64) play.WallSource {
	var seed rng.Seed
	for i := range seed {
		seed[i] = seedFill
	}
	binary.LittleEndian.PutUint64(seed[:8], gameNumber)
	return play.Seeded{Seed: seed}
}

type xorshift struct {
	state uint64
}

func (x *xorshift) next() uint64 {
	x.state ^= x.state << 13
	x.state ^= x.state >> 7
	x.state ^= x.state << 17
	return x.state
}

type playerKind uint8

const (
	greedyPlayer playerKind = iota
	randomPlayer
	tsumogiriPlayer
)

type player struct {
	kind playerKind
	word xorshift
}

func seatedPlayer(gameNumber uint64, s tile.Seat) player {
	index := uint64(s.Index())
	word := xorshift{state: gameNumber*4 + index + 1}
	switch {
	case (gameNumber+index)%6 == 0:
		return player{kind: randomPlayer, word: word}
	case (gameNumber+index)%6 == 1 && gameNumber%2 == 0:
		return player{kind: tsumogiriPlayer}
	default:
		return player{kind: greedyPlayer, word: word}
	}
}

func (p *player) decide(t *testing.T, decision play.Decision, hand []tile.TileID) play.Action {
	t.Helper()
	switch p.kind {
	case randomPlayer:
		return decision.Legal[p.word.next()%uint64(len(decision.Legal))]
	case tsumogiriPlayer:
		for _, win := range []play.Action{play.TsumoAction(), play.RonAction()} {
			if slices.Contains(decision.Legal, win) {
				return win
			}
		}
		return decision.Default
	case greedyPlayer:
	}
	return greedy(t, decision, hand, p.word.next())
}

func firstOfKinds(legal []play.Action, kinds ...play.ActionKind) (play.Action, bool) {
	at := slices.IndexFunc(legal, func(a play.Action) bool { return slices.Contains(kinds, a.Kind()) })
	if at < 0 {
		return play.Action{}, false
	}
	return legal[at], true
}

func greedy(t *testing.T, decision play.Decision, hand []tile.TileID, word uint64) play.Action {
	t.Helper()
	legal := decision.Legal
	if win, ok := firstOfKinds(legal, play.ActionTsumo, play.ActionRon); ok {
		return win
	}
	if riichi, ok := firstOfKinds(legal, play.ActionRiichi); ok {
		return riichi
	}
	if kan, ok := firstOfKinds(legal, play.ActionKan, play.ActionKyuushu); ok && word%kanOdds == 0 {
		return kan
	}
	if meld, ok := firstOfKinds(legal, play.ActionPon, play.ActionChi); ok && word%callOdds == 0 {
		return meld
	}

	var discards []tile.TileID
	for _, a := range legal {
		if id, ok := a.Tile(); ok && a.Kind() == play.ActionDiscard {
			discards = append(discards, id)
		}
	}
	if len(discards) == 0 {
		return decision.Default
	}

	start := int(word%greedyStartsModulus) % len(discards)
	discards = slices.Concat(discards[start:], discards[:start])
	best, bestShanten := discards[0], shantenWithout(t, hand, discards[0])
	for _, id := range discards[1:] {
		if s := shantenWithout(t, hand, id); s < bestShanten {
			best, bestShanten = id, s
		}
	}
	return play.DiscardAction(best)
}

func shantenWithout(t *testing.T, hand []tile.TileID, discard tile.TileID) int {
	t.Helper()
	kept := slices.DeleteFunc(slices.Clone(hand), func(id tile.TileID) bool { return id == discard })
	counts, err := tile.KindCounts(slices.Values(kept))
	if err != nil {
		t.Fatalf("KindCounts error = %v", err)
	}
	lowest, err := shanten.Lowest(counts)
	if err != nil {
		t.Fatalf("Lowest error = %v", err)
	}
	return lowest
}

type fact uint8

const (
	factChi fact = iota
	factPon
	factOpenKan
	factAddedKan
	factClosedKan
	factRinshanDraw
	factRiichi
	factIppatsuWin
	factChankanWin
	factFuriten
	factTsumo
	factRon
	factExhaustiveDraw
	factAbortive
	factRecordFromView
	factCount
)

func (f fact) String() string {
	return [factCount]string{
		"chi", "pon", "open kan", "added kan", "closed kan", "rinshan draw", "riichi", "ippatsu win",
		"chankan win", "furiten", "tsumo", "ron", "exhaustive draw", "abortive", "record from view",
	}[f]
}

type followedRecord struct {
	fromViewAt int
	fromView   bool
	record     play.SeatRecord
}

type follower struct {
	gameNumber uint64
	game       game.Game
	records    []followedRecord
	batches    int
	facts      [factCount]int
}

func newFollower(t *testing.T, gameNumber uint64) *follower {
	t.Helper()
	g, initial, err := game.New(paritySeed(gameNumber), play.Option[play.StartPosition]{})
	if err != nil {
		t.Fatalf("New error = %v", err)
	}
	f := &follower{gameNumber: gameNumber, game: g}
	for _, s := range tile.Seats() {
		r, ok := record.FromStart(s, initial)
		if !ok {
			t.Fatalf("game %d: FromStart found no start for seat %d", gameNumber, s.Index())
		}
		f.records = append(f.records, followedRecord{record: r})
	}
	f.assertRecordsAgree(t)
	return f
}

func (f *follower) follow(t *testing.T, batch []play.Emitted) {
	t.Helper()
	for i := range f.records {
		for _, e := range batch {
			f.records[i].record = record.Apply(f.records[i].record, e)
		}
	}

	f.batches++
	f.countFacts(batch)
	f.assertRecordsAgree(t)
	f.records = slices.DeleteFunc(f.records, func(r followedRecord) bool {
		return r.fromView && f.batches-r.fromViewAt >= viewRecordBatches
	})
	if f.batches%viewStartEvery == 0 {
		s := tile.Seats()[f.batches/viewStartEvery%tile.SeatCount]
		f.records = append(f.records, followedRecord{fromViewAt: f.batches, fromView: true, record: f.game.SeatView(s).Record})
		f.facts[factRecordFromView]++
	}
}

func (f *follower) assertRecordsAgree(t *testing.T) {
	t.Helper()
	var views [tile.SeatCount]play.SeatRecord
	for _, s := range tile.Seats() {
		views[s.Index()] = f.game.SeatView(s).Record
	}
	for _, r := range f.records {
		view := views[r.record.Seat.Index()]
		if reflect.DeepEqual(r.record, view) {
			continue
		}
		if diff := cmp.Diff(view, r.record, everyField()); diff != "" {
			t.Fatalf("game %d, batch %d, seat %d, record from the view of batch %d (%t) differs (-view +record):\n%s",
				f.gameNumber, f.batches, r.record.Seat.Index(), r.fromViewAt, r.fromView, diff)
		}
	}
}

func (f *follower) countFacts(batch []play.Emitted) {
	meldFacts := map[play.MeldKind]fact{
		play.MeldChi: factChi, play.MeldPon: factPon, play.MeldOpenKan: factOpenKan,
		play.MeldAddedKan: factAddedKan, play.MeldClosedKan: factClosedKan,
	}
	for _, e := range batch {
		switch event := e.Event.(type) {
		case play.Called:
			f.facts[meldFacts[event.Meld.Kind]]++
		case play.Drew:
			if event.Rinshan {
				f.facts[factRinshanDraw]++
			}
		case play.RiichiDeposited:
			f.facts[factRiichi]++
		case play.FuritenChanged:
			if event.Furiten {
				f.facts[factFuriten]++
			}
		case play.RoundEnded:
			f.countResult(event.Result)
		case play.GameStarted, play.RoundStarted, play.DrewNotice, play.Discarded, play.PaoAssigned,
			play.DoraRevealed, play.GameEnded:
		}
	}
}

func (f *follower) countResult(result play.RoundResult) {
	var wins []play.WinResult
	switch r := result.(type) {
	case play.Tsumo:
		f.facts[factTsumo]++
		wins = []play.WinResult{r.Win}
	case play.Ron:
		f.facts[factRon]++
		wins = r.Wins
	case play.ExhaustiveDraw:
		f.facts[factExhaustiveDraw]++
	case play.Abortive:
		f.facts[factAbortive]++
	}
	for _, y := range []struct {
		yaku play.YakuID
		won  fact
	}{{play.YakuIppatsu, factIppatsuWin}, {play.YakuChankan, factChankanWin}} {
		if slices.ContainsFunc(wins, func(win play.WinResult) bool { return slices.Contains(win.Yaku, y.yaku) }) {
			f.facts[y.won]++
		}
	}
}

func (f *follower) play(t *testing.T) {
	t.Helper()
	var players [tile.SeatCount]player
	for _, s := range tile.Seats() {
		players[s.Index()] = seatedPlayer(f.gameNumber, s)
	}
	for range maxSteps {
		var seats []tile.Seat
		switch awaiting := f.game.Awaiting().(type) {
		case play.AwaitingRoundOver:
			next, batch, refusal := f.game.DealNextRound()
			if refusal.OK {
				t.Fatalf("game %d: DealNextRound refused: %+v", f.gameNumber, refusal.Value)
			}
			f.game = next
			f.follow(t, batch)
			continue
		case play.AwaitingTurn:
			seats = []tile.Seat{awaiting.Seat}
		case play.AwaitingCall:
			seats = slices.SortedFunc(slices.Values(awaiting.Seats), func(a, b tile.Seat) int { return a.Index() - b.Index() })
		case play.AwaitingGameOver:
			return
		}

		for _, s := range seats {
			decision, ok := f.game.Decision(s)
			if !ok {
				t.Fatalf("game %d: awaited seat %d has no decision", f.gameNumber, s.Index())
			}
			action := players[s.Index()].decide(t, decision, f.game.Hand(s))
			next, batch, refusal := f.game.Act(s, action)
			if refusal.OK {
				t.Fatalf("game %d: legal action %v refused: %+v", f.gameNumber, action, refusal.Value)
			}
			f.game = next
			f.follow(t, batch)
		}
	}
	t.Fatalf("game %d does not end within %d steps", f.gameNumber, maxSteps)
}

func TestSeatRecord_WhenFedItsSeatsEvents_ShouldEqualEverySeatViewAfterEveryBatch(t *testing.T) {
	var played [parityGames]*follower
	t.Run("games", func(t *testing.T) {
		for gameNumber := range uint64(parityGames) {
			t.Run(strconv.FormatUint(gameNumber, 10), func(t *testing.T) {
				t.Parallel()
				f := newFollower(t, gameNumber)
				f.play(t)
				played[gameNumber] = f
			})
		}
	})
	if t.Failed() {
		return
	}

	var facts [factCount]int
	batches := 0
	for _, f := range played {
		batches += f.batches
		for i, count := range f.facts {
			facts[i] += count
		}
	}

	for _, required := range []fact{
		factChi, factPon, factOpenKan, factAddedKan, factClosedKan, factRinshanDraw, factRiichi,
		factIppatsuWin, factFuriten, factTsumo, factRon, factExhaustiveDraw, factRecordFromView,
	} {
		if facts[required] == 0 {
			t.Errorf("no %s in %d games of %d batches: %v", required, parityGames, batches, facts)
		}
	}
}
