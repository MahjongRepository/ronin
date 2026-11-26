package wire

import (
	"errors"
	"fmt"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
)

const ReplayVersion = "0.5-dev"

const ReplaySeedBytes = 96

const MaxReplayBytes = 16 * 1024 * 1024

const MigratedRulesProfileID = 1

const TenhouRulesProfileID = 2

const RRCRulesProfileID = 3

const noRulesProfile = 0

// RulesProfileOf returns the rules profile a replay records for ruleset: 0, which no replay
// accepts, for a ruleset with no profile.
func RulesProfileOf(ruleset play.Ruleset) Int {
	switch ruleset {
	case play.RulesetTenhou:
		return TenhouRulesProfileID
	case play.RulesetRRC:
		return RRCRulesProfileID
	}

	return noRulesProfile
}

// RulesetOfProfile returns the ruleset a replay of rules profile id plays again under; false for
// the migrated profile, which no ruleset reproduces, and for any unknown one.
func RulesetOfProfile(id Value) (play.Ruleset, bool) {
	switch id {
	case Int(TenhouRulesProfileID):
		return play.RulesetTenhou, true
	case Int(RRCRulesProfileID):
		return play.RulesetRRC, true
	}

	return 0, false
}

var replayKeys = keySet(func(k Key) bool {
	return k <= KeyYakuYakumanCount || k == KeyShownHands || k == KeyPlace
})

var replayProfile = profile{
	keys:   &replayKeys,
	replay: true,
	limits: limits{str: 4096, bin: ReplaySeedBytes, array: 4096, mapN: 128},
}

var (
	ErrNoVersionRecord = errors.New("replay is missing its version record")
	ErrReplayTooLarge  = errors.New("replay exceeds " + strconv.Itoa(MaxReplayBytes) + " bytes")
)

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

type UnsupportedVersionError struct {
	Version Value
}

func (e UnsupportedVersionError) Error() string {
	if s, ok := e.Version.(Str); ok {
		return "unsupported replay version " + strconv.Quote(string(s))
	}

	return "the first record is no version record"
}

func ReplaySettings(ruleset play.Ruleset) StrMap {
	return StrMap{{Key: "id", Value: RulesProfileOf(ruleset)}, {Key: "overrides", Value: StrMap{}}}
}

func VersionRecord() Map {
	return Map{{Key: KeyReplayVersion, Value: Str(ReplayVersion)}}
}

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

type ObserverVersion bool

const (
	WithoutVersionRecord ObserverVersion = false
	WithVersionRecord    ObserverVersion = true
)

func EncodeObserverRecords(records []Map, version ObserverVersion) ([]byte, error) {
	var content []byte
	if version == WithVersionRecord {
		content = appendValue(content, VersionRecord())
	}

	for i, record := range records {
		err := validateObserverRecord(record)
		if err != nil {
			return nil, ReplayError{Record: i + 1, Offset: len(content), Err: err}
		}

		content = appendValue(content, record)
	}

	return content, nil
}

func EncodeStrMap(m StrMap) []byte {
	return appendValue(nil, m)
}

func DecodeStrMap(content []byte) (StrMap, error) {
	d := decoder{data: content, limits: limits{
		str:   replayProfile.limits.str,
		bin:   MaxReplayBytes,
		array: replayProfile.limits.array,
		mapN:  replayProfile.limits.mapN,
	}}
	v, err := d.value(0, strKeys)
	if err != nil {
		return nil, err
	}

	m, ok := v.(StrMap)
	if !ok || d.pos != len(content) {
		return nil, errors.New("expected one map with string keys")
	}

	return m, nil
}

func DecodeReplay(content []byte) ([]Map, error) {
	records, err := decodeRecords(content, validateRecord)
	if err != nil {
		return nil, err
	}

	return records, nil
}

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

	return validateReplayEvent(record, eventFields)
}

func validateObserverRecord(record Map) error {
	if _, seeded := record.Get(KeySeed); seeded {
		return errors.New("an observer record holds no seed")
	}

	err := replayProfile.validate(record, 0)
	if err != nil {
		return err
	}

	return validateReplayEvent(record, observerEventFields)
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
		return fmt.Errorf("a seed must be %d bytes of binary data", ReplaySeedBytes)
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

	if _, known := RulesetOfProfile(id); !known && id != Int(MigratedRulesProfileID) {
		return errors.New("unknown rules profile")
	}

	empty, ok := overrides.(StrMap)
	if !ok || len(empty) != 0 {
		return errors.New("unsupported rules overrides")
	}

	return nil
}
