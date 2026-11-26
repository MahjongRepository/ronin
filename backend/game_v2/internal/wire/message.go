package wire

import (
	"errors"
	"fmt"
)

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

type DecodeError struct {
	Err error
}

func (e DecodeError) Error() string {
	return "decode message: " + e.Err.Error()
}

func (e DecodeError) Unwrap() error {
	return e.Err
}

func Encode(m Map) ([]byte, error) {
	err := liveProfile.validate(m, 0)
	if err != nil {
		return nil, err
	}
	return appendValue(nil, m), nil
}

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
