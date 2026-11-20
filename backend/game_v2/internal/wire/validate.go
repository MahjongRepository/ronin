package wire

import (
	"errors"
	"fmt"
	"strconv"
	"unicode/utf8"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

type profile struct {
	keys   *[keyCount]bool
	replay bool
	limits limits
}

func (p *profile) validate(v Value, depth int) error {
	if depth > maxNesting {
		return errNesting
	}

	switch v := v.(type) {
	case Nil, Bool, Int:
	case Str:
		if !utf8.ValidString(string(v)) {
			return errors.New("string is not valid UTF-8")
		}
	case Float:
		if p.replay {
			return errors.New("a replay holds no float")
		}
	case Bin:
		if p.replay {
			return errors.New("a replay holds binary data only as its seed")
		}
	case Array:
		for _, item := range v {
			err := p.validate(item, depth+1)
			if err != nil {
				return err
			}
		}
	case Map:
		return p.validateMap(v, depth)
	case StrMap:
		return errors.New("a string-keyed map belongs only under a score map or the rules envelope")
	}
	return nil
}

func (p *profile) validateMap(m Map, depth int) error {
	var seen [keyCount]bool
	for _, f := range m {
		if int(f.Key) >= keyCount || !p.keys[f.Key] {
			return unknownKeyError{raw: Int(f.Key)}
		}
		if seen[f.Key] {
			return fmt.Errorf("duplicate metadata key %s", f.Key)
		}
		seen[f.Key] = true

		err := p.validateField(f, depth+1)
		if err != nil {
			return err
		}
	}
	return nil
}

func (p *profile) validateField(f Field, depth int) error {
	if f.Key == KeyScores || f.Key == KeyScoreChanges {
		return validateScoreMap(f.Value)
	}
	if f.Key == KeyGameSettings {
		return validateSettings(f.Value)
	}
	if f.Key == KeySeed {
		return validateSeed(f.Value)
	}
	return p.validate(f.Value, depth)
}

func validateScoreMap(v Value) error {
	scores, ok := v.(StrMap)
	if !ok {
		return errors.New("a score map must be a string-keyed map")
	}

	var seen [tile.SeatCount]bool
	for _, f := range scores {
		seat, err := strconv.Atoi(f.Key)
		if err != nil || seat < 0 || seat >= tile.SeatCount || strconv.Itoa(seat) != f.Key {
			return fmt.Errorf("score map key %q is no seat", f.Key)
		}
		if seen[seat] {
			return fmt.Errorf("score map has seat %s twice", f.Key)
		}
		seen[seat] = true

		_, isInt := f.Value.(Int)
		if !isInt {
			return fmt.Errorf("score map value of seat %s is no integer", f.Key)
		}
	}
	return nil
}
