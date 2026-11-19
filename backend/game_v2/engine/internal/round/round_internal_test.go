package round

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func id(t *testing.T, n int) tile.TileID {
	t.Helper()
	got, ok := tile.NewTileID(n)
	if !ok {
		t.Fatalf("NewTileID(%d) refused", n)
	}
	return got
}

func seat(t *testing.T, n int) tile.Seat {
	t.Helper()
	got, ok := tile.NewSeat(n)
	if !ok {
		t.Fatalf("NewSeat(%d) refused", n)
	}
	return got
}

func copies(t *testing.T, first int, mpsz string) []tile.TileID {
	t.Helper()
	parsed, err := tile.ParseTiles(mpsz)
	if err != nil {
		t.Fatalf("ParseTiles(%q) error = %v", mpsz, err)
	}

	var seen [tile.KindCount]int
	ids := make([]tile.TileID, 0, len(parsed))
	for _, parsedTile := range parsed {
		kind := parsedTile.Kind()
		ids = append(ids, id(t, int(kind)*tile.CopiesPerKind+first+seen[kind]))
		seen[kind]++
	}
	return ids
}

func orderedRound(t *testing.T, dealer tile.Seat) Round {
	t.Helper()
	w, err := wall.FromTiles(tile.AllTileIDs())
	if err != nil {
		t.Fatalf("FromTiles error = %v", err)
	}
	return Deal(w, dealer, tile.East)
}

func TestSeatWind_WhenTheDealerIsSeatTwo_ShouldWrapTheWindsAroundTheTable(t *testing.T) {
	r := orderedRound(t, seat(t, 2))

	var winds [tile.SeatCount]tile.Wind
	for i, s := range tile.Seats() {
		winds[i] = r.seatWind(s)
	}

	if want := [tile.SeatCount]tile.Wind{tile.West, tile.North, tile.East, tile.South}; winds != want {
		t.Errorf("seat winds = %v, want %v", winds, want)
	}
}

func TestIsFourWinds_WhenAPlayerHasAnOpenPon_ShouldNotAbort(t *testing.T) {
	r := orderedRound(t, seat(t, 0))
	for i := range r.rivers {
		r.rivers[i] = []play.RiverTile{{Tile: copies(t, i, "1z")[0], Tsumogiri: true}}
	}
	if !r.isFourWinds() {
		t.Fatal("four East discards do not abort")
	}

	pinFives := copies(t, 0, "555p")
	r.melds[1].push(offer.NewMeldView(play.MeldPon, pinFives[0], pinFives[1:], seat(t, 0)))

	if r.isFourWinds() {
		t.Error("four East discards abort beside an open pon")
	}
}

func TestIsKeishikiTenpai_WhenTheHandIsStructurallyTenpai_ShouldBeTrue(t *testing.T) {
	closed := slices.Concat(copies(t, 0, "123456789m"), copies(t, 0, "12p"), copies(t, 0, "5p"), copies(t, 1, "5p"))

	if !isKeishikiTenpai(closed, nil) {
		t.Error("isKeishikiTenpai = false, want true")
	}
}

func TestIsKeishikiTenpai_WhenEveryCopyOfTheWaitIsInTheOwnHand_ShouldBeFalse(t *testing.T) {
	closed := slices.Concat(copies(t, 0, "123456789m"), copies(t, 3, "9p"))
	pon := slices.Concat(copies(t, 0, "9p"), copies(t, 1, "9p"), copies(t, 2, "9p"))

	if isKeishikiTenpai(closed, pon) {
		t.Error("isKeishikiTenpai = true, want false")
	}
}

func TestIsKeishikiTenpai_WhenCopiesOfTheWaitRemainElsewhere_ShouldBeTrue(t *testing.T) {
	closed := slices.Concat(
		copies(t, 0, "1m"), copies(t, 1, "1m"), copies(t, 2, "1m"), copies(t, 0, "234567m"),
		copies(t, 0, "5p"), copies(t, 1, "5p"), copies(t, 2, "5p"), copies(t, 0, "9s"),
	)

	if !isKeishikiTenpai(closed, nil) {
		t.Error("isKeishikiTenpai = false, want true")
	}
}

func TestNotenPayments_ShouldSplitThePenaltyBetweenNotenAndTenpaiSeats(t *testing.T) {
	for _, c := range []struct {
		tenpai [tile.SeatCount]bool
		want   [tile.SeatCount]int
	}{
		{[tile.SeatCount]bool{}, [tile.SeatCount]int{}},
		{[tile.SeatCount]bool{false, true, false, false}, [tile.SeatCount]int{-1000, 3000, -1000, -1000}},
		{[tile.SeatCount]bool{true, true, false, false}, [tile.SeatCount]int{1500, 1500, -1500, -1500}},
		{[tile.SeatCount]bool{true, true, true, false}, [tile.SeatCount]int{1000, 1000, 1000, -3000}},
		{[tile.SeatCount]bool{true, true, true, true}, [tile.SeatCount]int{}},
	} {
		if got := notenPayments(c.tenpai); got != c.want {
			t.Errorf("notenPayments(%v) = %v, want %v", c.tenpai, got, c.want)
		}
	}
}

func ronOnly(t *testing.T, from tile.Seat, ronCallers ...tile.Seat) CallPrompt {
	t.Helper()
	return newCallPrompt(id(t, 0), from, ronCallers, [tile.SeatCount][]play.Action{})
}

func TestNewCallPrompt_ShouldOrderRonCallersFromTheDiscarderAndAwaitThemInSeatOrder(t *testing.T) {
	prompt := ronOnly(t, seat(t, 2), seat(t, 0), seat(t, 3))

	if want := []tile.Seat{seat(t, 3), seat(t, 0)}; !slices.Equal(prompt.ronCallers, want) {
		t.Errorf("ron callers = %v, want %v", prompt.ronCallers, want)
	}
	if want := []tile.Seat{seat(t, 0), seat(t, 3)}; !slices.Equal(prompt.Pending(), want) {
		t.Errorf("pending = %v, want %v", prompt.Pending(), want)
	}
}

func TestDeclaredRons_ShouldListTheClosestCallerFirstWhateverTheAnswerOrder(t *testing.T) {
	prompt := ronOnly(t, seat(t, 2), seat(t, 0), seat(t, 1), seat(t, 3))

	prompt.declareRon(seat(t, 1))
	prompt.pass(seat(t, 0))
	prompt.declareRon(seat(t, 3))

	if !prompt.isSettled() {
		t.Error("the prompt is not settled")
	}
	if want := []tile.Seat{seat(t, 3), seat(t, 1)}; !slices.Equal(prompt.declaredRons(), want) {
		t.Errorf("declared rons = %v, want %v", prompt.declaredRons(), want)
	}
	if !prompt.hasAnswered(seat(t, 0)) || prompt.hasAnswered(seat(t, 2)) {
		t.Error("hasAnswered is wrong for the passing caller or the discarder")
	}
}

func TestOffers_ShouldListRonThenTheMeldsThenPassAndAwaitMeldCallersToo(t *testing.T) {
	chi := play.ChiAction([2]tile.TileID{id(t, 4), id(t, 8)})
	pon := play.PonAction([2]tile.TileID{id(t, 1), id(t, 2)})
	var meldOffers [tile.SeatCount][]play.Action
	meldOffers[1] = []play.Action{pon, chi}
	meldOffers[3] = []play.Action{pon}

	prompt := newCallPrompt(id(t, 0), seat(t, 0), []tile.Seat{seat(t, 1)}, meldOffers)

	if want := []tile.Seat{seat(t, 1), seat(t, 3)}; !slices.Equal(prompt.Pending(), want) {
		t.Errorf("pending = %v, want %v", prompt.Pending(), want)
	}
	for _, c := range []struct {
		seat tile.Seat
		want []play.Action
	}{
		{seat(t, 1), []play.Action{play.RonAction(), pon, chi, play.PassAction()}},
		{seat(t, 3), []play.Action{pon, play.PassAction()}},
		{seat(t, 2), nil},
	} {
		if got := prompt.Offers(c.seat); !slices.Equal(got, c.want) {
			t.Errorf("Offers(%d) = %v, want %v", c.seat.Index(), got, c.want)
		}
	}
}

func TestWinningMeld_WhenPonAndChiAreDeclared_ShouldPickThePon(t *testing.T) {
	chi := play.ChiCall{Held: [2]tile.TileID{id(t, 4), id(t, 8)}}
	prompt := ronOnly(t, seat(t, 0))

	prompt.declareMeld(seat(t, 1), chi)
	if got, ok := prompt.winningMeld(); !ok || got != (seatCall{seat(t, 1), chi}) {
		t.Errorf("winningMeld = %v, want seat 1's chi", got)
	}

	pon := play.PonCall{Held: [2]tile.TileID{id(t, 1), id(t, 2)}}
	prompt.declareMeld(seat(t, 2), pon)
	if got, ok := prompt.winningMeld(); !ok || got != (seatCall{seat(t, 2), pon}) {
		t.Errorf("winningMeld = %v, want seat 2's pon", got)
	}
}
