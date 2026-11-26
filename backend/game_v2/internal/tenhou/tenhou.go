package tenhou

import (
	"encoding/hex"
	"errors"
	"fmt"
	"slices"
	"strconv"
	"strings"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	mjlogVersion  = "2.3"
	goVsHuman     = 0x01
	goNoAkadora   = 0x02
	goHanchan     = 0x08
	drawLetters   = "TUVW"
	discardTags   = "DEFG"
	tagClose      = " />"
	dieFaceOffset = 1
)

var ErrNoGameEnd = errors.New("replay has no game end")

var errBeforeGameStart = errors.New("a record comes before the game start")

// RecordError reports the replay record a log cannot be written from, counted from 1 with the
// version record, as wire.ReplayError counts them.
type RecordError struct {
	Record int
	Err    error
}

func (e RecordError) Error() string {
	return "replay record " + strconv.Itoa(e.Record) + ": " + e.Err.Error()
}

func (e RecordError) Unwrap() error {
	return e.Err
}

func Convert(content []byte) (string, error) {
	records, err := wire.DecodeReplay(content)
	if err != nil {
		return "", err
	}
	events := records[1:]
	if !slices.ContainsFunc(events, isGameEnd) {
		return "", ErrNoGameEnd
	}
	return convertEvents(events)
}

func isGameEnd(record wire.Map) bool {
	code, _ := record.Get(wire.KeyEventType)
	return code == wire.Int(wire.EventGameEnd)
}

const firstEventRecord = 2

func convertEvents(events []wire.Map) (string, error) {
	var c converter
	for i, event := range events {
		c.convert(event)
		if c.r.err != nil {
			return "", RecordError{Record: i + firstEventRecord, Err: c.r.err}
		}
	}
	return strings.Join(c.tags, ""), nil
}

type converter struct {
	r           reader
	started     bool
	firstDealer tile.Seat
	tags        []string

	scores      [tile.SeatCount]int
	honba       int
	tableSticks int
	deposits    int
	hands       [tile.SeatCount][]int
}

func (c *converter) seat(s tile.Seat) int {
	return s.DistanceFrom(c.firstDealer)
}

func (c *converter) readSeat(m wire.Map, k wire.Key) int {
	return c.seat(c.r.seat(m, k))
}

func (c *converter) sticks() int {
	return c.tableSticks + c.deposits
}

func (c *converter) add(tag string) {
	c.tags = append(c.tags, tag)
}

func (c *converter) convert(event wire.Map) {
	code := wire.EventType(c.r.int(event, wire.KeyEventType))
	if !c.started && code != wire.EventGameStarted {
		c.r.fail(errBeforeGameStart)
		return
	}

	switch code {
	case wire.EventGameStarted:
		c.gameStarted(event)
	case wire.EventRoundStarted:
		c.roundStarted(event)
	case wire.EventDraw:
		c.drew(event)
	case wire.EventDiscard:
		c.discarded(event)
	case wire.EventRiichiDeclared:
		c.riichiDeclared(event)
	case wire.EventMeld:
		c.called(event)
	case wire.EventDoraRevealed:
		c.add(`<DORA hai="` + strconv.Itoa(c.r.tileID(event, wire.KeyTileID)) + `"/>`)
	case wire.EventRoundEnd:
		c.roundEnded(event)
	case wire.EventGameEnd:
		c.gameEnded(event)
	case wire.EventCallPrompt, wire.EventError, wire.EventFuriten, wire.EventTurn, wire.EventDrawNotice,
		wire.EventPaoAssigned, wire.EventSeatControl:
	}
}

func (c *converter) gameStarted(event wire.Map) {
	c.firstDealer = c.r.seat(event, wire.KeyDealer)
	c.started = true
	seed := c.r.bin(event, wire.KeySeed)
	rngVersion := c.r.str(event, wire.KeyRNGVersion)
	if c.r.int(event, wire.KeyGameType) != int(wire.GameHanchan) {
		c.r.fail(errors.New("only a hanchan has a Tenhou game type"))
	}
	goType := goVsHuman | goHanchan
	if !c.r.boolean(event, wire.KeyHasAkadora) {
		goType |= goNoAkadora
	}

	var names [tile.SeatCount]string
	for s, player := range c.bySeat(c.r.objects(event, wire.KeyPlayers)) {
		names[s] = escapeName(c.r.str(player, wire.KeyName))
	}

	c.add(`<mjloggm ver="` + mjlogVersion + `">`)
	c.add(`<SHUFFLE seed="` + hex.EncodeToString(seed) + `" ref="` + rngVersion + `"/>`)
	c.add(`<GO type="` + strconv.Itoa(goType) + `" lobby="0"/>`)
	c.add(`<UN n0="` + names[0] + `" n1="` + names[1] + `" n2="` + names[2] + `" n3="` + names[3] +
		`" dan="0,0,0,0" rate="1500.00,1500.00,1500.00,1500.00" sx="M,M,M,M"/>`)
	c.add(`<TAIKYOKU oya="` + strconv.Itoa(c.seat(c.firstDealer)) + `"/>`)
}

func (c *converter) bySeat(entries []wire.Map) [tile.SeatCount]wire.Map {
	var seated [tile.SeatCount]wire.Map
	for _, entry := range entries {
		s := c.readSeat(entry, wire.KeySeat)
		if seated[s] != nil {
			c.r.fail(errors.New("a seat is listed twice"))
		}
		seated[s] = entry
	}
	if len(entries) != tile.SeatCount {
		c.r.fail(errors.New("not every seat is listed"))
	}
	return seated
}

func (c *converter) roundStarted(event wire.Map) {
	dealer := c.readSeat(event, wire.KeyDealer)
	roundCounter := c.r.int(event, wire.KeyWind)*tile.SeatCount + dealer
	c.honba = c.r.int(event, wire.KeyHonba)
	c.tableSticks = c.r.int(event, wire.KeyRiichiSticks)
	c.deposits = 0
	dice := c.r.pair(event, wire.KeyDice)
	firstDora := 0
	if dora := c.r.ints(event, wire.KeyDoraIndicators); len(dora) > 0 {
		firstDora = dora[0]
	}

	var hands [tile.SeatCount]string
	for s, player := range c.bySeat(c.r.objects(event, wire.KeyPlayers)) {
		c.scores[s] = c.r.int(player, wire.KeyScore)
		c.hands[s] = c.r.ints(player, wire.KeyTiles)
		hands[s] = joinInts(c.hands[s])
	}

	header := []int{roundCounter, c.honba, c.tableSticks, dice[0] - dieFaceOffset, dice[1] - dieFaceOffset, firstDora}
	c.add(`<INIT seed="` + joinInts(header) + `" ten="` + joinInts(c.scores[:]) + `" oya="` +
		strconv.Itoa(dealer) + `" hai0="` + hands[0] + `" hai1="` + hands[1] + `" hai2="` + hands[2] +
		`" hai3="` + hands[3] + `"/>`)
}

func (c *converter) drew(event wire.Map) {
	seat, drawn, err := wire.UnpackDraw(c.r.int(event, wire.KeyPackedMove))
	if err != nil {
		c.r.fail(err)
		return
	}
	s := c.seat(seat)
	c.hands[s] = append(c.hands[s], drawn.Index())
	c.add("<" + drawLetters[s:s+1] + strconv.Itoa(drawn.Index()) + "/>")
}

func (c *converter) discarded(event wire.Map) {
	move, err := wire.UnpackDiscard(c.r.int(event, wire.KeyPackedMove))
	if err != nil {
		c.r.fail(err)
		return
	}
	s := c.seat(move.Seat)
	c.take(s, move.Tile.Index())
	if move.Riichi {
		c.add(`<REACH who="` + strconv.Itoa(s) + `" step="1"/>`)
	}
	c.add("<" + discardTags[s:s+1] + strconv.Itoa(move.Tile.Index()) + "/>")
}

func (c *converter) take(s, id int) {
	i := slices.Index(c.hands[s], id)
	if i < 0 {
		c.r.fail(fmt.Errorf("seat %d gives up tile %d it does not hold", s, id))
		return
	}
	c.hands[s] = slices.Delete(c.hands[s], i, i+1)
}

func (c *converter) riichiDeclared(event wire.Map) {
	s := c.readSeat(event, wire.KeySeat)
	c.deposits++
	c.scores[s] = c.r.int(event, wire.KeyScore)
	c.add(`<REACH who="` + strconv.Itoa(s) + `" ten="` + joinInts(c.scores[:]) + `" step="2"/>`)
}

func (c *converter) called(event wire.Map) {
	meld, err := wire.UnpackMeld(c.r.int(event, wire.KeyPackedMeld))
	if err != nil {
		c.r.fail(err)
		return
	}
	code, err := meldCode(meld)
	if err != nil {
		c.r.fail(err)
		return
	}

	s := c.seat(meld.Caller)
	if meld.Added.OK {
		c.take(s, meld.Added.Value.Index())
	} else {
		for _, held := range meld.Tiles {
			if !meld.Called.OK || held != meld.Called.Value {
				c.take(s, held.Index())
			}
		}
	}
	c.add(`<N who="` + strconv.Itoa(s) + `" m="` + strconv.Itoa(code) + `"` + tagClose)
}

func (c *converter) gameEnded(event wire.Map) {
	var owari []string
	for _, standing := range c.bySeat(c.r.objects(event, wire.KeyStandings)) {
		owari = append(owari, strconv.Itoa(c.r.int(standing, wire.KeyScore)),
			formatTenths(c.r.int(standing, wire.KeyFinalScore)))
	}

	last := len(c.tags) - 1
	if last < 0 || !strings.HasSuffix(c.tags[last], tagClose) {
		c.r.fail(errors.New("the game end follows no round end"))
		return
	}
	c.tags[last] = strings.TrimSuffix(c.tags[last], tagClose) + ` owari="` + strings.Join(owari, ",") + `"` + tagClose
	c.add("</mjloggm>")
}

func formatTenths(tenths int) string {
	sign := ""
	if tenths < 0 {
		sign, tenths = "-", -tenths
	}
	return sign + strconv.Itoa(tenths/10) + "." + strconv.Itoa(tenths%10)
}

func joinInts(values []int) string {
	parts := make([]string, len(values))
	for i, v := range values {
		parts[i] = strconv.Itoa(v)
	}
	return strings.Join(parts, ",")
}

func escapeName(name string) string {
	var escaped strings.Builder
	for _, b := range []byte(name) {
		switch {
		case 'a' <= b && b <= 'z', 'A' <= b && b <= 'Z', '0' <= b && b <= '9', b == '_', b == '-', b == '.', b == '~':
			escaped.WriteByte(b)
		default:
			escaped.WriteString("%" + strings.ToUpper(hex.EncodeToString([]byte{b})))
		}
	}
	return escaped.String()
}
