package main

import (
	"errors"
	"fmt"
	"reflect"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replay"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

type recording struct {
	records  []wire.Map
	callEnds []int
	setup    engine.Setup
}

func (r recording) content() ([]byte, error) {
	return wire.EncodeReplay(append([]wire.Map{wire.VersionRecord()}, r.records...))
}

func (r recording) run() (engine.Game, error) {
	content, err := r.content()
	if err != nil {
		return engine.Game{}, fmt.Errorf("encode the replay: %w", err)
	}
	loaded, err := replay.Load(content)
	if err != nil {
		return engine.Game{}, fmt.Errorf("load the replay: %w", err)
	}
	steps, err := replay.Run(r.setup, loaded.Actions)
	if err != nil {
		return engine.Game{}, fmt.Errorf("run the replay: %w", err)
	}
	return steps[len(steps)-1].Game, nil
}

func requireReproduces(name string, r recording, final engine.Game) error {
	replayed, err := r.run()
	if err != nil {
		return fmt.Errorf("%s: %w", name, err)
	}
	if !reflect.DeepEqual(replayed, final) {
		return fmt.Errorf("%s: the replay does not reproduce the game", name)
	}
	return nil
}

type expectedRecord struct {
	event  wire.EventType
	fields wire.Map
}

type outcome struct {
	roundEnd wire.Map
	then     play.Option[expectedRecord]
}

func endsInGame(roundEnd wire.Map) outcome {
	return outcome{roundEnd: roundEnd, then: play.Some(expectedRecord{event: wire.EventGameEnd})}
}

func thenRecord(roundEnd wire.Map, event wire.EventType, fields wire.Map) outcome {
	return outcome{roundEnd: roundEnd, then: play.Some(expectedRecord{event: event, fields: fields})}
}

func requireOutcome(name string, r recording, want outcome) error {
	content, err := r.content()
	if err != nil {
		return fmt.Errorf("%s: encode the replay: %w", name, err)
	}
	records, err := wire.DecodeReplay(content)
	if err != nil {
		return fmt.Errorf("%s: decode the replay: %w", name, err)
	}
	lines := records[1:]
	last := -1
	for i, line := range lines {
		if isEvent(line, wire.EventRoundEnd) {
			last = i
		}
	}
	if last < 0 {
		return fmt.Errorf("%s: the replay has no round end", name)
	}

	roundEnd, after := lines[last], lines[last+1:]
	if !holds(roundEnd, want.roundEnd) {
		return fmt.Errorf("%s: the last round end %v does not hold %v", name, roundEnd, want.roundEnd)
	}
	switch {
	case !want.then.OK && len(after) > 0:
		return fmt.Errorf("%s: the replay goes on after its last round end with %v", name, after[0])
	case !want.then.OK:
		return nil
	case len(after) == 0 || !isEvent(after[0], want.then.Value.event) || !holds(after[0], want.then.Value.fields):
		return fmt.Errorf("%s: the record after the last round end is not an event %d with %v",
			name, want.then.Value.event, want.then.Value.fields)
	}
	return nil
}

func holds(actual, expected wire.Value) bool {
	switch e := expected.(type) {
	case wire.Map:
		a, ok := actual.(wire.Map)
		return ok && !slices.ContainsFunc(e, func(f wire.Field) bool {
			v, present := a.Get(f.Key)
			return !present || !holds(v, f.Value)
		})
	case wire.StrMap:
		a, ok := actual.(wire.StrMap)
		return ok && !slices.ContainsFunc(e, func(f wire.StrField) bool {
			v, present := a.Get(f.Key)
			return !present || !holds(v, f.Value)
		})
	case wire.Array:
		a, ok := actual.(wire.Array)
		if !ok || len(a) != len(e) {
			return false
		}
		for i := range e {
			if !holds(a[i], e[i]) {
				return false
			}
		}
		return true
	case wire.Nil, wire.Bool, wire.Int, wire.Float, wire.Str, wire.Bin:
	}
	return reflect.DeepEqual(actual, expected)
}

func cutAfter(name string, r recording, event wire.EventType, occurrence int) (recording, error) {
	var matches []int
	for i, record := range r.records {
		if isEvent(record, event) {
			matches = append(matches, i)
		}
	}
	if occurrence < 0 {
		occurrence += len(matches)
	}
	if occurrence < 0 || occurrence >= len(matches) {
		return recording{}, fmt.Errorf("%s: no event %d at occurrence %d of %d", name, event, occurrence, len(matches))
	}
	at := slices.IndexFunc(r.callEnds, func(end int) bool { return end > matches[occurrence] })
	if at < 0 {
		return recording{}, fmt.Errorf("%s: event %d at record %d ends no call", name, event, matches[occurrence])
	}

	end := r.callEnds[at]
	callEnds := slices.DeleteFunc(slices.Clone(r.callEnds), func(callEnd int) bool { return callEnd > end })
	cut := recording{records: r.records[:end], callEnds: callEnds, setup: r.setup}
	_, err := cut.run()
	if err != nil {
		return recording{}, fmt.Errorf("%s: the cut replay: %w", name, err)
	}
	return cut, nil
}

type replayFixture struct {
	name  string
	build func() (recording, error)
}

func generateReplayFixtures() (map[string][]byte, error) {
	generated := map[string][]byte{}
	var failures []error
	for _, fixture := range replayFixtures() {
		r, err := fixture.build()
		if err != nil {
			failures = append(failures, err)
			continue
		}
		content, err := r.content()
		if err != nil {
			failures = append(failures, fmt.Errorf("%s: %w", fixture.name, err))
			continue
		}
		generated[fixture.name] = content
	}
	return generated, errors.Join(failures...)
}
