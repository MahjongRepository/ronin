package wire

// Value is one MessagePack value of a message or replay record: Nil, Bool, Int, Float, Str, Bin,
// Array, Map or StrMap. An Int and a Float of the same number encode differently, and a Map keeps
// its entries in the order they encode.
//
//sumtype:decl
type Value interface {
	isValue()
}

// Nil is MessagePack nil.
type Nil struct{}

// Bool is a MessagePack boolean.
type Bool bool

// Int is a MessagePack integer, encoded in the fewest bytes that hold it.
type Int int64

// Float is a MessagePack float, always encoded as a float64.
type Float float64

// Str is a MessagePack string of valid UTF-8.
type Str string

// Bin is MessagePack binary data; a replay holds it only as its seed.
type Bin []byte

// Array is a MessagePack array.
type Array []Value

// Map is a metadata map: its entries in encoding order, each keyed by a Key.
type Map []Field

// Field is one entry of a Map.
type Field struct {
	Key   Key
	Value Value
}

// StrMap is a map with string keys, in encoding order: a score map, keyed "0" to "3" by seat, or a
// replay's rules envelope.
type StrMap []StrField

// StrField is one entry of a StrMap.
type StrField struct {
	Key   string
	Value Value
}

func (Nil) isValue()    {}
func (Bool) isValue()   {}
func (Int) isValue()    {}
func (Float) isValue()  {}
func (Str) isValue()    {}
func (Bin) isValue()    {}
func (Array) isValue()  {}
func (Map) isValue()    {}
func (StrMap) isValue() {}

// Get returns the value of k's first entry; false when m has none.
func (m Map) Get(k Key) (Value, bool) {
	for _, f := range m {
		if f.Key == k {
			return f.Value, true
		}
	}
	return nil, false
}

// Get returns the value of key's first entry; false when m has none.
func (m StrMap) Get(key string) (Value, bool) {
	for _, f := range m {
		if f.Key == key {
			return f.Value, true
		}
	}
	return nil, false
}
