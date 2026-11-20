package tenhou

import (
	"errors"
	"slices"
	"strconv"
	"strings"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const nagashiManganType = "nm"

func (c *converter) seatScores(m wire.Map, k wire.Key) [tile.SeatCount]int {
	var moved [tile.SeatCount]int
	for i, score := range c.r.scoreMap(m, k) {
		s, _ := tile.NewSeat(i)
		moved[c.seat(s)] = score
	}
	return moved
}

func (c *converter) roundEnded(event wire.Map) {
	scores := c.seatScores(event, wire.KeyScores)
	changes := c.seatScores(event, wire.KeyScoreChanges)
	dora := c.r.ints(event, wire.KeyDoraIndicators)

	switch wire.ResultType(c.r.int(event, wire.KeyResultType)) {
	case wire.ResultTsumo:
		table := winTable{
			from: c.readSeat(event, wire.KeyWinnerSeat), tile: c.r.tileID(event, wire.KeyWinningTile),
			sticks: c.sticks(), dora: dora,
		}
		c.win(event, table, scores)
	case wire.ResultRon:
		table := winTable{
			from: c.readSeat(event, wire.KeyLoserSeat), tile: c.r.tileID(event, wire.KeyWinningTile), sticks: c.sticks(),
			dora: dora,
		}
		before := scores
		for _, win := range c.r.objects(event, wire.KeyWinners) {
			before = c.win(win, table, before)
			table.sticks = 0
		}
	case wire.ResultExhaustiveDraw:
		c.exhaustiveDraw(event, scores, changes)
	case wire.ResultAbortiveDraw:
		c.abortiveDraw(event, scores, changes)
	}
}

type winTable struct {
	from   int
	tile   int
	sticks int
	dora   []int
}

func (c *converter) win(win wire.Map, table winTable, before [tile.SeatCount]int) [tile.SeatCount]int {
	winner := c.readSeat(win, wire.KeyWinnerSeat)
	hand := c.r.object(win, wire.KeyHandResult)
	changes := c.seatScores(win, wire.KeyScoreChanges)
	held := c.r.ints(win, wire.KeyClosedTiles)
	held = append(held, table.tile)
	slices.Sort(held)

	var tag strings.Builder
	tag.WriteString(`<AGARI ba="` + strconv.Itoa(c.honba) + "," + strconv.Itoa(table.sticks) + `" hai="` +
		joinInts(held) + `"`)
	if melds := c.meldCodes(win); len(melds) > 0 {
		tag.WriteString(` m="` + joinInts(melds) + `"`)
	}
	tag.WriteString(` machi="` + strconv.Itoa(table.tile) + `" ten="` + c.ten(hand) + `"` + c.yakuAttribute(hand) +
		` doraHai="` + joinInts(table.dora) + `"`)
	if ura := c.optionalInts(win, wire.KeyUraDora); len(ura) > 0 {
		tag.WriteString(` doraHaiUra="` + joinInts(ura) + `"`)
	}
	tag.WriteString(` who="` + strconv.Itoa(winner) + `" fromWho="` + strconv.Itoa(table.from) + `"`)
	if _, ok := win.Get(wire.KeyPaoSeat); ok {
		tag.WriteString(` paoWho="` + strconv.Itoa(c.readSeat(win, wire.KeyPaoSeat)) + `"`)
	}
	tag.WriteString(` sc="` + scoreChanges(before, changes) + `"` + tagClose)
	c.add(tag.String())

	var after [tile.SeatCount]int
	for s := range after {
		after[s] = before[s] + changes[s]
	}
	return after
}

func (c *converter) optionalInts(m wire.Map, k wire.Key) []int {
	if _, ok := m.Get(k); !ok {
		return nil
	}
	return c.r.ints(m, k)
}

func (c *converter) meldCodes(win wire.Map) []int {
	packed := c.r.ints(win, wire.KeyMelds)
	codes := make([]int, 0, len(packed))
	for _, p := range slices.Backward(packed) {
		meld, err := wire.UnpackMeld(p)
		if err != nil {
			c.r.fail(err)
			return nil
		}
		code, err := meldCode(meld)
		if err != nil {
			c.r.fail(err)
			return nil
		}
		codes = append(codes, code)
	}
	return codes
}

func (c *converter) ten(hand wire.Map) string {
	points := c.r.int(hand, wire.KeyPoints) * wire.ScoreDivisor
	return strconv.Itoa(c.r.int(hand, wire.KeyFu)) + "," + strconv.Itoa(points) + "," +
		strconv.Itoa(c.limitCode(c.r.str(hand, wire.KeyHandLimit)))
}

func (c *converter) limitCode(name string) int {
	switch name {
	case wire.HandLimitNone:
		return 0
	case wire.HandLimitKazoeYakuman:
		return play.LimitYakuman.TenhouCode()
	}
	for limit := play.LimitMangan; limit <= play.LimitYakuman; limit++ {
		if limit.String() == name {
			return limit.TenhouCode()
		}
	}
	c.r.fail(errors.New("no Tenhou limit for hand limit " + strconv.Quote(name)))
	return 0
}

type tenhouYaku struct {
	id      int
	han     int
	yakuman bool
}

func (c *converter) yakuAttribute(hand wire.Map) string {
	var yaku []tenhouYaku
	for _, entry := range c.r.objects(hand, wire.KeyYaku) {
		id := c.r.int(entry, wire.KeyYakuID)
		tenhouID, yakuman, ok := tenhouYakuID(id)
		if !ok {
			c.r.fail(errors.New("yaku " + strconv.Itoa(id) + " has no Tenhou id"))
		}
		yaku = append(yaku, tenhouYaku{id: tenhouID, han: c.r.int(entry, wire.KeyHan), yakuman: yakuman})
	}

	if !slices.ContainsFunc(yaku, func(y tenhouYaku) bool { return y.yakuman }) {
		var pairs []int
		for _, y := range yaku {
			pairs = append(pairs, y.id, y.han)
		}
		return ` yaku="` + joinInts(pairs) + `"`
	}

	var yakuman []int
	for _, y := range yaku {
		if y.yakuman {
			yakuman = append(yakuman, y.id)
		}
	}
	return ` yakuman="` + joinInts(yakuman) + `"`
}

func tenhouYakuID(id int) (tenhouID int, yakuman, ok bool) {
	switch id {
	case wire.YakuIDDora:
		return play.Dora.TenhouID(), false, true
	case wire.YakuIDAkaDora:
		return play.AkaDora.TenhouID(), false, true
	case wire.YakuIDUraDora:
		return play.UraDora.TenhouID(), false, true
	}
	for _, y := range play.AllYaku() {
		if int(y) == id {
			return y.TenhouID(), y.IsYakuman(), true
		}
	}
	return 0, false, false
}

func (c *converter) exhaustiveDraw(event wire.Map, scores, changes [tile.SeatCount]int) {
	kind := ""
	if len(c.optionalInts(event, wire.KeyQualifyingSeats)) > 0 {
		kind = ` type="` + nagashiManganType + `"`
	}

	var shown [tile.SeatCount][]int
	var isShown [tile.SeatCount]bool
	for _, hand := range c.r.objects(event, wire.KeyTenpaiHands) {
		s := c.readSeat(hand, wire.KeySeat)
		shown[s], isShown[s] = c.r.ints(hand, wire.KeyClosedTiles), true
	}
	c.add(`<RYUUKYOKU` + kind + ` ba="` + strconv.Itoa(c.honba) + "," + strconv.Itoa(c.sticks()) + `" sc="` +
		scoreChanges(scores, changes) + `"` + revealedHands(shown, isShown) + tagClose)
}

func (c *converter) abortiveDraw(event wire.Map, scores, changes [tile.SeatCount]int) {
	reason := wire.AbortReason(c.r.str(event, wire.KeyAbortiveReason))
	var revealed []int
	var code string
	switch reason {
	case wire.AbortNineTerminals:
		code, revealed = "yao9", []int{c.readSeat(event, wire.KeySeat)}
	case wire.AbortFourWinds:
		code = "kaze4"
	case wire.AbortFourRiichi:
		code, revealed = "reach4", []int{0, 1, 2, 3}
	case wire.AbortFourKans:
		code = "kan4"
	case wire.AbortTripleRon:
		code = "ron3"
		for _, n := range c.r.ints(event, wire.KeyRonCallers) {
			s, ok := tile.NewSeat(n)
			if !ok {
				c.r.fail(errors.New("a ron caller is no seat"))
				return
			}
			revealed = append(revealed, c.seat(s))
		}
	default:
		c.r.fail(errors.New("unknown abort reason " + strconv.Quote(string(reason))))
		return
	}

	var shown [tile.SeatCount][]int
	var isShown [tile.SeatCount]bool
	for _, s := range revealed {
		shown[s], isShown[s] = c.hands[s], true
	}
	c.add(`<RYUUKYOKU type="` + code + `" ba="` + strconv.Itoa(c.honba) + "," + strconv.Itoa(c.sticks()) + `" sc="` +
		scoreChanges(scores, changes) + `"` + revealedHands(shown, isShown) + tagClose)
}

func revealedHands(hands [tile.SeatCount][]int, shown [tile.SeatCount]bool) string {
	var attributes strings.Builder
	for s, hand := range hands {
		if !shown[s] {
			continue
		}
		attributes.WriteString(` hai` + strconv.Itoa(s) + `="` + joinInts(slices.Sorted(slices.Values(hand))) + `"`)
	}
	return attributes.String()
}

func scoreChanges(scores, changes [tile.SeatCount]int) string {
	parts := make([]int, 0, 2*tile.SeatCount)
	for s := range scores {
		parts = append(parts, scores[s], changes[s])
	}
	return joinInts(parts)
}
