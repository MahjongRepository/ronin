package wire

//sumtype:decl
type Value interface {
	isValue()
}

type Nil struct{}

type Bool bool

type Int int64

type Float float64

type Str string

type Bin []byte

type Array []Value

type Map []Field

type Field struct {
	Key   Key
	Value Value
}

type StrMap []StrField

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

func (m Map) Get(k Key) (Value, bool) {
	for _, f := range m {
		if f.Key == k {
			return f.Value, true
		}
	}
	return nil, false
}

func (m Map) Int(k Key) (int, bool) {
	v, _ := m.Get(k)
	n, ok := v.(Int)
	return int(n), ok
}

func (m Map) Str(k Key) (string, bool) {
	v, _ := m.Get(k)
	s, ok := v.(Str)
	return string(s), ok
}

func (m StrMap) Get(key string) (Value, bool) {
	for _, f := range m {
		if f.Key == key {
			return f.Value, true
		}
	}
	return nil, false
}
