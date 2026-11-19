package wire

import (
	"encoding/binary"
	"math"
)

const (
	maxFixInt    = 0x7f
	minFixInt    = -32
	maxFixStr    = 31
	maxFixLen    = 15
	maxUint8Len  = math.MaxUint8
	maxUint16Len = math.MaxUint16
	fixMapBase   = 0x80
	fixArrayBase = 0x90
	fixStrBase   = 0xa0
)

const (
	tagNil     = 0xc0
	tagFalse   = 0xc2
	tagTrue    = 0xc3
	tagBin8    = 0xc4
	tagBin16   = 0xc5
	tagBin32   = 0xc6
	tagFloat32 = 0xca
	tagFloat64 = 0xcb
	tagUint8   = 0xcc
	tagUint16  = 0xcd
	tagUint32  = 0xce
	tagUint64  = 0xcf
	tagInt8    = 0xd0
	tagInt16   = 0xd1
	tagInt32   = 0xd2
	tagInt64   = 0xd3
	tagStr8    = 0xd9
	tagStr16   = 0xda
	tagStr32   = 0xdb
	tagArray16 = 0xdc
	tagArray32 = 0xdd
	tagMap16   = 0xde
	tagMap32   = 0xdf
)

func appendValue(b []byte, v Value) []byte {
	switch v := v.(type) {
	case Nil:
	case Bool:
		if v {
			return append(b, tagTrue)
		}
		return append(b, tagFalse)
	case Int:
		return appendInt(b, int64(v))
	case Float:
		return binary.BigEndian.AppendUint64(append(b, tagFloat64), math.Float64bits(float64(v)))
	case Str:
		return append(appendLength(b, len(v), fixStrBase, maxFixStr, tagStr8, tagStr16, tagStr32), v...)
	case Bin:
		return append(appendLength(b, len(v), 0, -1, tagBin8, tagBin16, tagBin32), v...)
	case Array:
		b = appendLength(b, len(v), fixArrayBase, maxFixLen, 0, tagArray16, tagArray32)
		for _, item := range v {
			b = appendValue(b, item)
		}
		return b
	case Map:
		b = appendLength(b, len(v), fixMapBase, maxFixLen, 0, tagMap16, tagMap32)
		for _, f := range v {
			b = appendValue(appendInt(b, int64(f.Key)), f.Value)
		}
		return b
	case StrMap:
		b = appendLength(b, len(v), fixMapBase, maxFixLen, 0, tagMap16, tagMap32)
		for _, f := range v {
			b = appendValue(appendValue(b, Str(f.Key)), f.Value)
		}
		return b
	}
	return append(b, tagNil)
}

func appendInt(b []byte, n int64) []byte {
	switch {
	case n >= 0 && n <= maxFixInt:
		return append(b, byte(n))
	case n > 0 && n <= math.MaxUint8:
		return append(b, tagUint8, byte(n))
	case n > 0 && n <= math.MaxUint16:
		return binary.BigEndian.AppendUint16(append(b, tagUint16), uint16(n))
	case n > 0 && n <= math.MaxUint32:
		return binary.BigEndian.AppendUint32(append(b, tagUint32), uint32(n))
	case n > 0:
		return binary.BigEndian.AppendUint64(append(b, tagUint64), uint64(n))
	case n >= minFixInt:
		return append(b, byte(int8(n)))
	case n >= math.MinInt8:
		return append(b, tagInt8, byte(int8(n)))
	case n >= math.MinInt16:
		return binary.BigEndian.AppendUint16(append(b, tagInt16), uint16(int16(n)))
	case n >= math.MinInt32:
		return binary.BigEndian.AppendUint32(append(b, tagInt32), uint32(int32(n)))
	default:
		return binary.BigEndian.AppendUint64(append(b, tagInt64), uint64(n))
	}
}

func appendLength(b []byte, n int, fixBase byte, maxFix int, tag8, tag16, tag32 byte) []byte {
	switch {
	case n <= maxFix:
		return append(b, fixBase|byte(n))
	case tag8 != 0 && n <= maxUint8Len:
		return append(b, tag8, byte(n))
	case n <= maxUint16Len:
		return binary.BigEndian.AppendUint16(append(b, tag16), uint16(n))
	default:
		return binary.BigEndian.AppendUint32(append(b, tag32), uint32(n))
	}
}
