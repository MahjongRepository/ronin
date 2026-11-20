package wire

import (
	"errors"
	"fmt"
)

// MaxMessageBytes is the largest live message Decode reads.
const MaxMessageBytes = 256 * 1024

var liveKeys = keySet(func(k Key) bool {
	return k != KeyReplayVersion && k != KeyHasAkadora && k != KeyGameSettings && k != KeyRNGVersion &&
		k != KeySeed
})

var liveProfile = profile{
	keys:   &liveKeys,
	limits: limits{str: 64 * 1024, bin: 64 * 1024, array: 1024, mapN: 256},
}

func keySet(includes func(Key) bool) [keyCount]bool {
	var set [keyCount]bool
	for k := range keyCount {
		set[k] = includes(Key(k))
	}
	return set
}

// DecodeError reports a live message that is too large, is no valid MessagePack, or breaks the
// message rules Encode holds.
type DecodeError struct {
	Err error
}

func (e DecodeError) Error() string {
	return "decode message: " + e.Err.Error()
}

func (e DecodeError) Unwrap() error {
	return e.Err
}

// Encode returns m as one live message. It refuses a key the live wire does not carry (the
// replay-only ones), a key twice in one map, a score map not keyed "0" to "3" with integer
// scores, a string-keyed map anywhere else, invalid UTF-8 and nesting deeper than 32.
func Encode(m Map) ([]byte, error) {
	err := liveProfile.validate(m, 0)
	if err != nil {
		return nil, err
	}
	return appendValue(nil, m), nil
}

// Decode reads one live message, a map, refusing what Encode refuses, data past the message, any
// extension type and what breaks the decode limits (MaxMessageBytes in all, a string or binary of
// 64 KiB, an array of 1024, a map of 256), with a DecodeError.
func Decode(data []byte) (Map, error) {
	m, err := decodeMessage(data)
	if err != nil {
		return nil, DecodeError{Err: err}
	}
	return m, nil
}

func decodeMessage(data []byte) (Map, error) {
	if len(data) > MaxMessageBytes {
		return nil, fmt.Errorf("payload of %d bytes is too large", len(data))
	}

	d := decoder{data: data, limits: liveProfile.limits}
	m, err := d.record()
	if err != nil {
		return nil, err
	}
	if d.pos != len(data) {
		return nil, errors.New("data past the message")
	}

	err = liveProfile.validate(m, 0)
	if err != nil {
		return nil, err
	}
	return m, nil
}
