package migrate

import (
	"errors"
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/store"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/tenhou"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

// Transform is a kind of change the rewrite makes to a replay of version 0.4-dev, beyond its
// version record, which every rewrite replaces.
type Transform uint8

// The transforms, each named by its String.
const (
	TransformRon Transform = iota
	TransformDoubleRon
	TransformNagashi
	TransformRobbedKan
	TransformPao
	TransformFinalScores
	transformCount
)

var transformNames = [transformCount]string{
	TransformRon:         "ron with its win under WINNERS",
	TransformDoubleRon:   "double ron as a ron of two wins",
	TransformNagashi:     "nagashi mangan as an exhaustive draw",
	TransformRobbedKan:   "robbed kan declared before the ron",
	TransformPao:         "pao assigned after its call",
	TransformFinalScores: "final scores in tenths",
}

func (t Transform) String() string {
	return transformNames[t]
}

// FailureKind is why a replay was left as it was.
type FailureKind uint8

// The failure kinds, each named by its String.
const (
	FailureUnreadable FailureKind = iota
	FailureVersion
	FailureShape
	FailureInconsistent
	FailureEncode
	FailureExport
	FailureWrite
	failureKindCount
)

var failureNames = [failureKindCount]string{
	FailureUnreadable:   "unreadable",
	FailureVersion:      "unknown version",
	FailureShape:        "unknown shape",
	FailureInconsistent: "inconsistent records",
	FailureEncode:       "refused by the codec",
	FailureExport:       "no Tenhou log",
	FailureWrite:        "not written",
}

func (k FailureKind) String() string {
	return failureNames[k]
}

// RewriteError reports why a replay cannot be rewritten without loss: its Kind, and the record it
// fails at, counted from 1, or 0 for the replay as a whole.
type RewriteError struct {
	Kind   FailureKind
	Record int
	Err    error
}

func (e RewriteError) Error() string {
	if e.Record == 0 {
		return e.Kind.String() + ": " + e.Err.Error()
	}
	return e.Kind.String() + " at record " + strconv.Itoa(e.Record) + ": " + e.Err.Error()
}

func (e RewriteError) Unwrap() error {
	return e.Err
}

// Rewritten is a replay of version 0.4-dev rewritten into the current version: its Content, the
// Transforms it took, in Transform order, whether it holds the game's end, and whether the old file
// ended inside a record, so only the records before it were rewritten.
type Rewritten struct {
	Content    []byte
	Transforms []Transform
	GameEnded  bool
	Cut        bool
}

// Rewrite rewrites the content of a replay of version 0.4-dev into the current version, the bytes
// the Go server would have written for the game as it was played and scored. Every record it does
// not change keeps its bytes. A replay with no game end is rewritten whole, and one that ends
// inside a record up to that record. A replay it cannot rewrite without loss comes back as a
// RewriteError: a record or field the old format never held, records whose robbed kan or pao it
// cannot place, a rewrite the current codec refuses or, for a game with its end, a rewrite that
// converts to no Tenhou log.
func Rewrite(content []byte) (Rewritten, error) {
	records, err := wire.DecodeRecords(content)
	replayErr, isReplayErr := errors.AsType[wire.ReplayError](err)
	cut := isReplayErr && replayErr.Incomplete && len(records) > 0
	if err != nil && !cut {
		return Rewritten{}, RewriteError{Kind: FailureUnreadable, Err: err}
	}
	version, _ := records[0].Get(wire.KeyReplayVersion)
	if len(records[0]) != 1 || version != wire.Str(legacyVersion) {
		return Rewritten{}, RewriteError{Kind: FailureVersion, Record: 1, Err: errors.New("not a 0.4-dev version record")}
	}

	r := rewriter{out: []wire.Map{wire.VersionRecord()}}
	for i, record := range records[1:] {
		kind, recordErr := r.add(record)
		if recordErr != nil {
			return Rewritten{}, RewriteError{Kind: kind, Record: i + 2, Err: recordErr}
		}
	}

	rewritten, err := wire.EncodeReplay(r.out)
	if err != nil {
		return Rewritten{}, RewriteError{Kind: FailureEncode, Err: err}
	}
	if r.gameEnded {
		_, err = tenhou.Convert(rewritten)
		if err != nil {
			return Rewritten{}, RewriteError{Kind: FailureExport, Err: err}
		}
	}
	return Rewritten{Content: rewritten, Transforms: r.transforms(), GameEnded: r.gameEnded, Cut: cut}, nil
}

type rewriter struct {
	out       []wire.Map
	applied   [transformCount]bool
	melds     [tile.SeatCount][]wire.Meld
	pao       [tile.SeatCount]play.Option[tile.Seat]
	drawer    play.Option[tile.Seat]
	gameEnded bool
}

func (r *rewriter) transforms() []Transform {
	var applied []Transform
	for t := range transformCount {
		if r.applied[t] {
			applied = append(applied, t)
		}
	}
	return applied
}

func (r *rewriter) add(record wire.Map) (FailureKind, error) {
	if r.gameEnded {
		return FailureShape, errors.New("a record after the game end")
	}
	err := checkLegacyShape(record)
	if err != nil {
		return FailureShape, err
	}

	event, _ := intOf(record, wire.KeyEventType)
	switch wire.EventType(event) {
	case wire.EventRoundStarted:
		r.melds, r.pao, r.drawer = [tile.SeatCount][]wire.Meld{}, [tile.SeatCount]play.Option[tile.Seat]{}, play.Option[tile.Seat]{}
	case wire.EventDraw:
		err = r.drew(record)
	case wire.EventMeld:
		return FailureInconsistent, r.called(record)
	case wire.EventRoundEnd:
		return FailureInconsistent, r.roundEnded(record)
	case wire.EventGameEnd:
		return FailureInconsistent, r.gameEnd(record)
	case wire.EventDiscard, wire.EventRiichiDeclared, wire.EventDoraRevealed, wire.EventGameStarted,
		wire.EventSeatControl, wire.EventCallPrompt, wire.EventError, wire.EventFuriten, wire.EventTurn,
		wire.EventDrawNotice, wire.EventPaoAssigned:
	}
	if err != nil {
		return FailureInconsistent, err
	}
	r.out = append(r.out, record)
	return 0, nil
}

func (r *rewriter) drew(record wire.Map) error {
	packed, _ := intOf(record, wire.KeyPackedMove)
	seat, _, err := wire.UnpackDraw(packed)
	r.drawer = play.Some(seat)
	return err
}

func (r *rewriter) called(record wire.Map) error {
	packed, _ := intOf(record, wire.KeyPackedMeld)
	meld, err := wire.UnpackMeld(packed)
	if err != nil {
		return err
	}

	seat := meld.Caller.Index()
	earlier := r.melds[seat]
	if meld.Kind == play.MeldAddedKan {
		i := slices.IndexFunc(earlier, func(m wire.Meld) bool { return isPonOf(m, meld.Tiles[0].Kind()) })
		if i < 0 {
			return errors.New("an added kan of no pon of its seat")
		}
		r.melds[seat] = slices.Concat(earlier[:i], []wire.Meld{meld}, earlier[i+1:])
	} else {
		r.melds[seat] = append(slices.Clone(earlier), meld)
	}
	r.out = append(r.out, record)

	liable := paoOf(earlier, meld)
	if liable.OK {
		r.pao[seat] = liable
		r.applied[TransformPao] = true
		r.out = append(r.out, wire.Map{
			{Key: wire.KeyEventType, Value: wire.Int(wire.EventPaoAssigned)},
			{Key: wire.KeySeat, Value: wire.Int(seat)},
			{Key: wire.KeyPaoSeat, Value: wire.Int(liable.Value.Index())},
		})
	}
	return nil
}

func isPonOf(m wire.Meld, kind tile.Kind) bool {
	return m.Kind == play.MeldPon && m.Tiles[0].Kind() == kind
}

func paoOf(earlier []wire.Meld, meld wire.Meld) play.Option[tile.Seat] {
	if (meld.Kind != play.MeldPon && meld.Kind != play.MeldOpenKan) || !meld.From.OK {
		return play.Option[tile.Seat]{}
	}

	dragons, winds := tile.DragonKinds(), tile.WindKinds()
	var set []tile.Kind
	switch kind := meld.Tiles[0].Kind(); {
	case slices.Contains(dragons[:], kind):
		set = dragons[:]
	case slices.Contains(winds[:], kind):
		set = winds[:]
	default:
		return play.Option[tile.Seat]{}
	}

	held := 0
	for _, m := range earlier {
		if slices.Contains(set, m.Tiles[0].Kind()) {
			held++
		}
	}
	if held != len(set)-1 {
		return play.Option[tile.Seat]{}
	}
	return meld.From
}

func (r *rewriter) roundEnded(record wire.Map) error {
	if robbed, ok := record.Get(wire.KeyRobbedKan); ok {
		kan, err := r.robbedKan(robbed, record)
		if err != nil {
			return err
		}
		r.declareRobbedKan(kan)
		record = without(record, wire.KeyRobbedKan)
	}

	result, _ := intOf(record, wire.KeyResultType)
	switch wire.ResultType(result) {
	case wire.ResultTsumo:
		err := r.checkPao(record)
		if err != nil {
			return err
		}
	case wire.ResultRon:
		err := r.checkPao(record)
		if err != nil {
			return err
		}
		record = ronOfOneWin(record)
		r.applied[TransformRon] = true
	case legacyDoubleRon:
		winners, _ := record.Get(wire.KeyWinners)
		for _, win := range asArray(winners) {
			err := r.checkPao(asMap(win))
			if err != nil {
				return err
			}
		}
		record = withResult(record, wire.ResultRon)
		r.applied[TransformDoubleRon] = true
	case legacyNagashi:
		record = withResult(record, wire.ResultExhaustiveDraw)
		r.applied[TransformNagashi] = true
	case wire.ResultExhaustiveDraw, wire.ResultAbortiveDraw:
	}
	r.out = append(r.out, record)
	return nil
}

func (r *rewriter) robbedKan(robbed wire.Value, roundEnd wire.Map) (wire.Map, error) {
	kan := asMap(robbed)
	seatN, _ := intOf(kan, wire.KeySeat)
	tileN, _ := intOf(kan, wire.KeyTileID)
	seat, seatOK := tile.NewSeat(seatN)
	id, idOK := tile.NewTileID(tileN)
	winning, hasWinning := intOf(roundEnd, wire.KeyWinningTile)
	switch {
	case !seatOK || !idOK:
		return nil, errors.New("a robbed kan of no seat or tile")
	case hasWinning && winning != tileN:
		return nil, errors.New("a robbed kan of another tile than the one won")
	case r.drawer != play.Some(seat):
		return nil, errors.New("a robbed kan declared by a seat that did not draw last")
	}

	var meld wire.Meld
	kanType, _ := kan.Get(wire.KeyKanType)
	switch kanType {
	case wire.Str(legacyAddedKan):
		i := slices.IndexFunc(r.melds[seat.Index()], func(m wire.Meld) bool { return isPonOf(m, id.Kind()) })
		if i < 0 {
			return nil, errors.New("a robbed added kan of no pon of its seat")
		}
		meld = r.melds[seat.Index()][i]
		meld.Kind, meld.Tiles, meld.Added = play.MeldAddedKan, append(slices.Clone(meld.Tiles), id), play.Some(id)
	case wire.Str(legacyClosedKan):
		meld = wire.Meld{Caller: seat, Kind: play.MeldClosedKan, Tiles: copiesOf(id.Kind())}
	default:
		return nil, errors.New("a robbed kan of an unknown kan type")
	}

	packed, err := wire.PackMeld(meld)
	if err != nil {
		return nil, err
	}
	return wire.Map{
		{Key: wire.KeyEventType, Value: wire.Int(wire.EventMeld)},
		{Key: wire.KeyPackedMeld, Value: wire.Int(packed)},
	}, nil
}

func copiesOf(kind tile.Kind) []tile.TileID {
	ids := make([]tile.TileID, 0, tile.CopiesPerKind)
	for _, id := range tile.AllTileIDs() {
		if id.Kind() == kind {
			ids = append(ids, id)
		}
	}
	return ids
}

func (r *rewriter) declareRobbedKan(kan wire.Map) {
	at := len(r.out)
	for at > 0 {
		event, _ := intOf(r.out[at-1], wire.KeyEventType)
		if wire.EventType(event) != wire.EventSeatControl {
			break
		}
		at--
	}
	r.out = slices.Insert(r.out, at, kan)
	r.applied[TransformRobbedKan] = true
}

func (r *rewriter) checkPao(win wire.Map) error {
	winnerN, _ := intOf(win, wire.KeyWinnerSeat)
	winner, ok := tile.NewSeat(winnerN)
	if !ok {
		return errors.New("a win of no seat")
	}
	liable, hasPao := intOf(win, wire.KeyPaoSeat)
	derived := r.pao[winner.Index()]
	if derived.OK != hasPao || (hasPao && derived.Value.Index() != liable) {
		return errors.New("a win's pao seat differs from the one its calls set")
	}
	return nil
}

func (r *rewriter) gameEnd(record wire.Map) error {
	standings, _ := record.Get(wire.KeyStandings)
	var scored wire.Array
	for _, item := range asArray(standings) {
		standing := asMap(item)
		final, ok := intOf(standing, wire.KeyFinalScore)
		if !ok {
			return errors.New("a standing with no final score")
		}
		scored = append(scored, replaced(standing, wire.KeyFinalScore, wire.Int(final*store.FinalScoreFactor)))
	}

	r.out = append(r.out, replaced(record, wire.KeyStandings, scored))
	r.applied[TransformFinalScores] = true
	r.gameEnded = true
	return nil
}

func ronOfOneWin(record wire.Map) wire.Map {
	ron := picked(record, slices.Concat(roundEndCommon, []wire.Key{wire.KeyLoserSeat, wire.KeyWinningTile}))
	ron = append(ron, wire.Field{Key: wire.KeyWinners, Value: wire.Array{picked(record, legacyWinKeys)}})
	return append(ron, picked(record, []wire.Key{wire.KeyScores, wire.KeyScoreChanges, wire.KeyHeadBumpedSeats})...)
}

func withResult(record wire.Map, result wire.ResultType) wire.Map {
	return replaced(record, wire.KeyResultType, wire.Int(result))
}

func picked(m wire.Map, keys []wire.Key) wire.Map {
	var out wire.Map
	for _, k := range keys {
		if v, ok := m.Get(k); ok {
			out = append(out, wire.Field{Key: k, Value: v})
		}
	}
	return out
}

func replaced(m wire.Map, k wire.Key, v wire.Value) wire.Map {
	out := slices.Clone(m)
	for i, f := range out {
		if f.Key == k {
			out[i].Value = v
		}
	}
	return out
}

func without(m wire.Map, k wire.Key) wire.Map {
	return slices.DeleteFunc(slices.Clone(m), func(f wire.Field) bool { return f.Key == k })
}

func asArray(v wire.Value) wire.Array {
	array, _ := v.(wire.Array)
	return array
}

func asMap(v wire.Value) wire.Map {
	m, _ := v.(wire.Map)
	return m
}
