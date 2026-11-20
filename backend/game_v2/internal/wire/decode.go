package wire

import (
	"errors"
	"fmt"
	"math"
	"strconv"
	"unicode/utf8"
)

const maxNesting = 32

var errTruncated = errors.New("truncated MessagePack data")

type limits struct {
	str   int
	bin   int
	array int
	mapN  int
}

type decoder struct {
	data   []byte
	pos    int
	limits limits
}

func (d *decoder) take(n int) ([]byte, error) {
	if n > len(d.data)-d.pos {
		return nil, errTruncated
	}
	chunk := d.data[d.pos : d.pos+n]
	d.pos += n
	return chunk, nil
}

func (d *decoder) uint(size int) (uint64, error) {
	chunk, err := d.take(size)
	if err != nil {
		return 0, err
	}
	var n uint64
	for _, c := range chunk {
		n = n<<8 | uint64(c)
	}
	return n, nil
}

func (d *decoder) record() (Map, error) {
	if d.pos < len(d.data) && d.data[d.pos] >= fixMapBase && d.data[d.pos] < fixArrayBase {
		tag := d.data[d.pos]
		d.pos++
		return d.fields(int(tag-fixMapBase), 0)
	}
	v, err := d.value(0, false)
	if err != nil {
		return nil, err
	}
	m, ok := v.(Map)
	if !ok {
		return nil, errors.New("expected a map")
	}
	return m, nil
}

func (d *decoder) value(depth int, stringKeys bool) (Value, error) {
	if depth > maxNesting {
		return nil, errNesting
	}
	tag, err := d.uint(1)
	if err != nil {
		return nil, err
	}

	switch {
	case tag <= maxFixInt:
		return Int(tag), nil
	case tag >= fixMapBase && tag < fixArrayBase:
		return d.mapOf(int(tag-fixMapBase), depth, stringKeys)
	case tag >= fixArrayBase && tag < fixStrBase:
		return d.array(int(tag-fixArrayBase), depth, stringKeys)
	case tag >= fixStrBase && tag < tagNil:
		return d.str(int(tag - fixStrBase))
	case tag > tagBin32 && tag < tagFloat32, tag > tagInt64 && tag < tagStr8:
		return nil, errors.New("unsupported MessagePack extension type")
	case tag > tagMap32:
		return Int(int8(tag)), nil
	}
	return d.tagged(byte(tag), depth, stringKeys)
}

func (d *decoder) tagged(tag byte, depth int, stringKeys bool) (Value, error) {
	switch tag {
	case tagNil:
		return Nil{}, nil
	case tagFalse:
		return Bool(false), nil
	case tagTrue:
		return Bool(true), nil
	case tagFloat32:
		n, err := d.uint(4)
		return Float(math.Float32frombits(uint32(n))), err
	case tagFloat64:
		n, err := d.uint(8)
		return Float(math.Float64frombits(n)), err
	case tagUint8, tagUint16, tagUint32, tagUint64:
		return d.unsigned(1 << (tag - tagUint8))
	case tagInt8, tagInt16, tagInt32, tagInt64:
		return d.signed(1 << (tag - tagInt8))
	case tagStr8, tagStr16, tagStr32:
		return d.sized(1<<(tag-tagStr8), func(n int) (Value, error) { return d.str(n) })
	case tagBin8, tagBin16, tagBin32:
		return d.sized(1<<(tag-tagBin8), d.bin)
	case tagArray16, tagArray32:
		return d.sized(2<<(tag-tagArray16), func(n int) (Value, error) { return d.array(n, depth, stringKeys) })
	case tagMap16, tagMap32:
		return d.sized(2<<(tag-tagMap16), func(n int) (Value, error) { return d.mapOf(n, depth, stringKeys) })
	}
	return nil, errors.New("reserved MessagePack type 0xc1")
}

func (d *decoder) sized(size int, read func(int) (Value, error)) (Value, error) {
	n, err := d.uint(size)
	if err != nil {
		return nil, err
	}
	return read(int(n))
}

func (d *decoder) unsigned(size int) (Value, error) {
	n, err := d.uint(size)
	if err != nil {
		return nil, err
	}
	if n > math.MaxInt64 {
		return nil, fmt.Errorf("integer %d out of range", n)
	}
	return Int(n), nil
}

func (d *decoder) signed(size int) (Value, error) {
	n, err := d.uint(size)
	if err != nil {
		return nil, err
	}
	shift := 64 - 8*size
	return Int(int64(n<<shift) >> shift), nil
}

func (d *decoder) str(n int) (Value, error) {
	if n > d.limits.str {
		return nil, lengthError("string", n, d.limits.str)
	}
	chunk, err := d.take(n)
	if err != nil {
		return nil, err
	}
	if !utf8.Valid(chunk) {
		return nil, errors.New("string is not valid UTF-8")
	}
	return Str(chunk), nil
}

func (d *decoder) bin(n int) (Value, error) {
	if n > d.limits.bin {
		return nil, lengthError("binary", n, d.limits.bin)
	}
	chunk, err := d.take(n)
	if err != nil {
		return nil, err
	}
	return Bin(append([]byte(nil), chunk...)), nil
}

func (d *decoder) array(n int, depth int, stringKeys bool) (Value, error) {
	if n > d.limits.array {
		return nil, lengthError("array", n, d.limits.array)
	}

	items := make(Array, 0, min(n, len(d.data)-d.pos))
	for range n {
		item, err := d.value(depth+1, stringKeys)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, nil
}

func (d *decoder) mapOf(n int, depth int, stringKeys bool) (Value, error) {
	if stringKeys {
		return d.strMap(n, depth)
	}
	m, err := d.fields(n, depth)
	if err != nil {
		return nil, err
	}
	return m, nil
}

func (d *decoder) fields(n int, depth int) (Map, error) {
	if n > d.limits.mapN {
		return nil, lengthError("map", n, d.limits.mapN)
	}
	m := make(Map, 0, min(n, len(d.data)-d.pos))
	for range n {
		key, err := d.key(depth)
		if err != nil {
			return nil, err
		}
		item, err := d.value(depth+1, stringKeyed(key))
		if err != nil {
			return nil, err
		}
		m = append(m, Field{Key: key, Value: item})
	}
	return m, nil
}

func (d *decoder) key(depth int) (Key, error) {
	raw, err := d.value(depth+1, false)
	if err != nil {
		return 0, err
	}
	n, ok := raw.(Int)
	if !ok || n < 0 || n >= Int(keyCount) {
		return 0, unknownKeyError{raw: raw}
	}
	return Key(n), nil
}

func (d *decoder) strMap(n int, depth int) (Value, error) {
	if n > d.limits.mapN {
		return nil, lengthError("map", n, d.limits.mapN)
	}
	m := make(StrMap, 0, min(n, len(d.data)-d.pos))
	for range n {
		raw, err := d.value(depth+1, true)
		if err != nil {
			return nil, err
		}
		key, ok := raw.(Str)
		if !ok {
			return nil, errors.New("a data map requires string keys")
		}
		item, err := d.value(depth+1, true)
		if err != nil {
			return nil, err
		}
		m = append(m, StrField{Key: string(key), Value: item})
	}
	return m, nil
}

func stringKeyed(k Key) bool {
	return k == KeyScores || k == KeyScoreChanges || k == KeyGameSettings
}

var errNesting = errors.New("nesting limit exceeded")

func lengthError(what string, n, limit int) error {
	return fmt.Errorf("%s of %d exceeds %d", what, n, limit)
}

type unknownKeyError struct {
	raw Value
}

func (e unknownKeyError) Error() string {
	if n, ok := e.raw.(Int); ok {
		return "unknown metadata key " + strconv.FormatInt(int64(n), 10)
	}
	return "metadata keys must be integers"
}
