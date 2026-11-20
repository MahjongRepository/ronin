package wire

import (
	"bytes"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"strconv"
	"strings"
	"testing"
)

type jsonObject []jsonEntry

type jsonEntry struct {
	Key   string
	Value any
}

func (o jsonObject) get(key string) any {
	for _, e := range o {
		if e.Key == key {
			return e.Value
		}
	}
	return nil
}

func (o jsonObject) with(key string, value any) jsonObject {
	out := make(jsonObject, 0, len(o))
	for _, e := range o {
		if e.Key == key {
			e.Value = value
		}
		out = append(out, e)
	}
	return out
}

func (o jsonObject) MarshalJSON() ([]byte, error) {
	var b bytes.Buffer
	b.WriteByte('{')
	for i, e := range o {
		if i > 0 {
			b.WriteByte(',')
		}
		key, err := json.Marshal(e.Key)
		if err != nil {
			return nil, err
		}
		value, err := json.Marshal(e.Value)
		if err != nil {
			return nil, err
		}
		b.Write(key)
		b.WriteByte(':')
		b.Write(value)
	}
	b.WriteByte('}')
	return b.Bytes(), nil
}

func readJSONFile(tb testing.TB, path string) jsonObject {
	tb.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		tb.Fatalf("read %s: %v", path, err)
	}
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.UseNumber()
	root, err := readJSON(decoder)
	if err != nil {
		tb.Fatalf("parse %s: %v", path, err)
	}
	object, ok := root.(jsonObject)
	if !ok {
		tb.Fatalf("%s holds no object", path)
	}
	return object
}

func writeJSONFile(t *testing.T, path string, root jsonObject) {
	t.Helper()
	compact, err := json.Marshal(root)
	if err != nil {
		t.Fatalf("marshal %s: %v", path, err)
	}
	var indented bytes.Buffer
	err = json.Indent(&indented, compact, "", "  ")
	if err != nil {
		t.Fatalf("indent %s: %v", path, err)
	}
	indented.WriteByte('\n')
	err = os.WriteFile(path, indented.Bytes(), 0o600)
	if err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}

func readJSON(decoder *json.Decoder) (any, error) {
	token, err := decoder.Token()
	if err != nil {
		return nil, err
	}
	delimiter, isDelimiter := token.(json.Delim)
	if !isDelimiter {
		return token, nil
	}

	switch delimiter {
	case '{':
		var object jsonObject
		for decoder.More() {
			keyToken, keyErr := decoder.Token()
			if keyErr != nil {
				return nil, keyErr
			}
			value, valueErr := readJSON(decoder)
			if valueErr != nil {
				return nil, valueErr
			}
			object = append(object, jsonEntry{Key: keyToken.(string), Value: value})
		}
		_, err = decoder.Token()
		return object, err
	case '[':
		array := []any{}
		for decoder.More() {
			value, valueErr := readJSON(decoder)
			if valueErr != nil {
				return nil, valueErr
			}
			array = append(array, value)
		}
		_, err = decoder.Token()
		return array, err
	default:
		return nil, errors.New("unexpected delimiter " + delimiter.String())
	}
}

func wireValueOf(t *testing.T, node any, field Key, stringKeys bool) Value {
	t.Helper()
	switch node := node.(type) {
	case nil:
		return Nil{}
	case bool:
		return Bool(node)
	case json.Number:
		if strings.ContainsAny(node.String(), ".eE") {
			f, err := node.Float64()
			if err != nil {
				t.Fatalf("float %s: %v", node, err)
			}
			return Float(f)
		}
		n, err := node.Int64()
		if err != nil {
			t.Fatalf("integer %s: %v", node, err)
		}
		return Int(n)
	case string:
		if field == KeySeed && !stringKeys {
			seed, err := hex.DecodeString(node)
			if err != nil {
				t.Fatalf("seed %q: %v", node, err)
			}
			return Bin(seed)
		}
		return Str(node)
	case []any:
		array := Array{}
		for _, item := range node {
			array = append(array, wireValueOf(t, item, noField, stringKeys))
		}
		return array
	case jsonObject:
		return wireMapOf(t, node, stringKeys || stringKeyed(field))
	default:
		t.Fatalf("unexpected JSON node %T", node)
		return nil
	}
}

const noField = Key(keyCount)

func wireMapOf(t *testing.T, object jsonObject, stringKeys bool) Value {
	t.Helper()
	if stringKeys {
		m := StrMap{}
		for _, e := range object {
			m = append(m, StrField{Key: e.Key, Value: wireValueOf(t, e.Value, noField, true)})
		}
		return m
	}
	m := Map{}
	for _, e := range object {
		n, err := strconv.Atoi(e.Key)
		if err != nil {
			t.Fatalf("metadata key %q: %v", e.Key, err)
		}
		key := Key(n)
		m = append(m, Field{Key: key, Value: wireValueOf(t, e.Value, key, false)})
	}
	return m
}

func wireRecordOf(t *testing.T, node any) Map {
	t.Helper()
	object, ok := node.(jsonObject)
	if !ok {
		t.Fatalf("record %v is no object", node)
	}
	m, _ := wireMapOf(t, object, false).(Map)
	return m
}

var keyAliases = [...]struct {
	name string
	key  Key
}{
	{"PENDING_GAME_TIMEOUT", KeyPendingGameTimeout},
	{"SEAT_CONTROL_REASON", KeySeatControlReason},
	{"PAYS_HONBA", KeyPaysHonba},
}

func namedKeys(includes *[keyCount]bool) jsonObject {
	var names jsonObject
	for k, name := range keyNames {
		if includes[k] {
			names = append(names, jsonEntry{Key: name, Value: json.Number(strconv.Itoa(k))})
		}
	}
	for _, alias := range keyAliases {
		names = append(names, jsonEntry{Key: alias.name, Value: json.Number(strconv.Itoa(int(alias.key)))})
	}
	return names
}
