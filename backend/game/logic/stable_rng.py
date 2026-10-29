import base64
import hashlib
import secrets
import struct

"""
    Based on tenhou generator blog.tenhou.net/article/30503297.html
"""
class MT19937:
    def __init__(self, seed_array):
        self.mt = [0] * 624
        self.index = 624
        self.init_by_array(seed_array)

    def init_by_array(self, init_key):
        mt = self.mt
        mt[0] = 19650218
        for i in range(1, 624):
            mt[i] = (1812433253 * (mt[i-1] ^ (mt[i-1] >> 30)) + i) & 0xFFFFFFFF

        i = 1
        j = 0
        key_length = len(init_key)
        k = max(624, key_length)

        for _ in range(k):
            mt[i] = (mt[i] ^ ((mt[i-1] ^ (mt[i-1] >> 30)) * 1664525)) + init_key[j] + j
            mt[i] &= 0xFFFFFFFF
            i += 1
            j += 1
            if i >= 624:
                mt[0] = mt[623]
                i = 1
            if j >= key_length:
                j = 0

        for _ in range(623):
            mt[i] = (mt[i] ^ ((mt[i-1] ^ (mt[i-1] >> 30)) * 1566083941)) - i
            mt[i] &= 0xFFFFFFFF
            i += 1
            if i >= 624:
                mt[0] = mt[623]
                i = 1

        mt[0] = 0x80000000

    def generate_numbers(self):
        N = 624
        M = 397
        MATRIX_A = 0x9908b0df
        UPPER_MASK = 0x80000000
        LOWER_MASK = 0x7fffffff

        for kk in range(N - M):
            y = (self.mt[kk] & UPPER_MASK) | (self.mt[kk+1] & LOWER_MASK)
            self.mt[kk] = self.mt[kk+M] ^ (y >> 1) ^ (MATRIX_A if y & 1 else 0)

        for kk in range(N - M, N - 1):
            y = (self.mt[kk] & UPPER_MASK) | (self.mt[kk+1] & LOWER_MASK)
            self.mt[kk] = self.mt[kk + (M - N)] ^ (y >> 1) ^ (MATRIX_A if y & 1 else 0)

        y = (self.mt[N-1] & UPPER_MASK) | (self.mt[0] & LOWER_MASK)
        self.mt[N-1] = self.mt[M-1] ^ (y >> 1) ^ (MATRIX_A if y & 1 else 0)

        self.index = 0

    def get_random(self):
        if self.index >= 624:
            self.generate_numbers()

        y = self.mt[self.index]
        self.index += 1

        y ^= (y >> 11)
        y ^= (y << 7) & 0x9d2c5680
        y ^= (y << 15) & 0xefc60000
        y ^= (y >> 18)

        return y

def randomize_wall(seed_b64: str, num_tiles: int = 136, tiles=None) -> list:
    seed_bytes = base64.b64decode(seed_b64)
    init_key = list(struct.unpack("<624I", seed_bytes))
    rng = MT19937(init_key)
    src = [rng.get_random() for _ in range(288)]
    rnd = []
    for i in range(9):
        chunk = src[i*32 : (i+1)*32]
        chunk_bytes = struct.pack("<32I", *chunk)
        hash_bytes = hashlib.sha512(chunk_bytes).digest()
        rnd.extend(struct.unpack("<16I", hash_bytes))
    wall = tiles or list(range(num_tiles))
    for i in range(num_tiles - 1):
        j = i + (rnd[i] % (num_tiles - i))
        wall[i], wall[j] = wall[j], wall[i]
    return wall

def generate_stable_seed() -> str:
    """
    Генерирует криптографически случайный валидный сид (3328 символов Base64), структурно идентичный сиду из реального
    XML-лога игры на Tenhou.
    """
    random_uint32s = [int.from_bytes(secrets.token_bytes(4), byteorder="little") for _ in range(624)]
    seed_bytes = struct.pack("<624I", *random_uint32s)
    return base64.b64encode(seed_bytes).decode("ascii")
