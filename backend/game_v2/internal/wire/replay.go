package wire

import (
	"errors"
	"strconv"
)

// ReplayVersion is the replay format a replay's first record names. It follows 0.4-dev, whose
// files a one-off rewrite brings to this version.
const ReplayVersion = "0.5-dev"

// ReplaySeedBytes is the size of the seed a replay's game start records, as binary data.
const ReplaySeedBytes = 96

// MaxReplayBytes is the largest replay DecodeReplay reads.
const MaxReplayBytes = 16 * 1024 * 1024

// MigratedRulesProfileID is the rules profile every replay rewritten from 0.4-dev was played under.
const MigratedRulesProfileID = 1

// RulesProfileID is the rules profile this server plays, the only other a rules envelope may name.
const RulesProfileID = 2

var replayKeys = keySet(func(k Key) bool {
	return k <= KeyYakuYakumanCount || k == KeyShownHands
})

var replayProfile = profile{
	keys:   &replayKeys,
	replay: true,
	limits: limits{str: 4096, bin: ReplaySeedBytes, array: 4096, mapN: 128},
}

var (
	// ErrNoVersionRecord reports a replay without records, so without its version record.
	ErrNoVersionRecord = errors.New("replay is missing its version record")
	// ErrReplayTooLarge reports content above MaxReplayBytes.
	ErrReplayTooLarge = errors.New("replay exceeds " + strconv.Itoa(MaxReplayBytes) + " bytes")
)

// ReplayError reports the record a replay breaks at, counted from 1, and the byte offset it starts
// at; Incomplete when the content ends inside it.
type ReplayError struct {
	Record     int
	Offset     int
	Incomplete bool
	Err        error
}

func (e ReplayError) Error() string {
	position := "replay record " + strconv.Itoa(e.Record) + " at byte " + strconv.Itoa(e.Offset)
	if e.Incomplete {
		return "incomplete " + position
	}
	return position + ": " + e.Err.Error()
}

func (e ReplayError) Unwrap() error {
	return e.Err
}

// UnsupportedVersionError reports a first record that is not the version record of ReplayVersion;
// Version is the value it holds under KeyReplayVersion, nil when it holds none.
type UnsupportedVersionError struct {
	Version Value
}

func (e UnsupportedVersionError) Error() string {
	if s, ok := e.Version.(Str); ok {
		return "unsupported replay version " + strconv.Quote(string(s))
	}
	return "the first record is no version record"
}

// ReplaySettings returns the rules envelope a replay of this server records: RulesProfileID with
// no overrides.
func ReplaySettings() StrMap {
	return StrMap{{Key: "id", Value: Int(RulesProfileID)}, {Key: "overrides", Value: StrMap{}}}
}

// VersionRecord returns a replay's first record, naming ReplayVersion.
func VersionRecord() Map {
	return Map{{Key: KeyReplayVersion, Value: Str(ReplayVersion)}}
}

// EncodeReplay returns records as a replay: each record one MessagePack map, back to back, the
// first the VersionRecord. Every other record must be an event a replay records, holding the
// fields its type requires, each of its type; no float, no binary data but a seed of
// ReplaySeedBytes and no key outside the replay's. A refused record comes back as a ReplayError
// whose Offset is where it would have started.
func EncodeReplay(records []Map) ([]byte, error) {
	if len(records) == 0 {
		return nil, ErrNoVersionRecord
	}

	var content []byte
	for i, record := range records {
		err := validateRecord(record, i+1)
		if err != nil {
			return nil, ReplayError{Record: i + 1, Offset: len(content), Err: err}
		}
		content = appendValue(content, record)
	}
	return content, nil
}

// DecodeReplay reads a replay EncodeReplay wrote, refusing what it refuses, any extension type, a
// string or array over 4096, a map over 128 entries, binary data over ReplaySeedBytes, and content
// above MaxReplayBytes (ErrReplayTooLarge) or with no record (ErrNoVersionRecord); EncodeReplay
// applies none of these limits. A
// record it cannot read comes back as a ReplayError; a first record of another version as one
// wrapping an UnsupportedVersionError.
func DecodeReplay(content []byte) ([]Map, error) {
	records, err := decodeRecords(content, validateRecord)
	if err != nil {
		return nil, err
	}
	return records, nil
}

// DecodeRecords reads the records of a replay of any version, 0.4-dev included: each a map of
// replay keys, read with DecodeReplay's limits, holding no float and binary data only as a seed,
// with neither the version record nor the record schema checked. A record it cannot read ends the
// read, and the records before it come back with the ReplayError; content above MaxReplayBytes is
// ErrReplayTooLarge, and content with no record ErrNoVersionRecord.
func DecodeRecords(content []byte) ([]Map, error) {
	return decodeRecords(content, func(record Map, _ int) error {
		return replayProfile.validate(record, 0)
	})
}

func decodeRecords(content []byte, check func(record Map, position int) error) ([]Map, error) {
	if len(content) > MaxReplayBytes {
		return nil, ErrReplayTooLarge
	}

	var records []Map
	d := decoder{data: content, limits: replayProfile.limits}
	for d.pos < len(content) {
		start := d.pos
		record, err := d.record()
		if err == nil {
			err = check(record, len(records)+1)
		}
		if err != nil {
			return records, ReplayError{
				Record:     len(records) + 1,
				Offset:     start,
				Incomplete: errors.Is(err, errTruncated),
				Err:        err,
			}
		}
		records = append(records, record)
	}

	if len(records) == 0 {
		return nil, ErrNoVersionRecord
	}
	return records, nil
}

func validateRecord(record Map, position int) error {
	if position == 1 {
		return validateVersionRecord(record)
	}

	err := replayProfile.validate(record, 0)
	if err != nil {
		return err
	}
	return validateReplayEvent(record)
}

func validateVersionRecord(record Map) error {
	version, _ := record.Get(KeyReplayVersion)
	if len(record) != 1 || version != Str(ReplayVersion) {
		return UnsupportedVersionError{Version: version}
	}
	return nil
}

func validateSeed(v Value) error {
	seed, ok := v.(Bin)
	if !ok || len(seed) != ReplaySeedBytes {
		return errors.New("a seed must be " + strconv.Itoa(ReplaySeedBytes) + " bytes of binary data")
	}
	return nil
}

func validateSettings(v Value) error {
	settings, ok := v.(StrMap)
	id, hasID := settings.Get("id")
	overrides, hasOverrides := settings.Get("overrides")
	if !ok || len(settings) != 2 || !hasID || !hasOverrides {
		return errors.New("the rules envelope must hold an id and its overrides, nothing else")
	}
	if id != Int(RulesProfileID) && id != Int(MigratedRulesProfileID) {
		return errors.New("unknown rules profile")
	}

	empty, ok := overrides.(StrMap)
	if !ok || len(empty) != 0 {
		return errors.New("unsupported rules overrides")
	}
	return nil
}
