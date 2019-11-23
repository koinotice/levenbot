try:
    # pysha3
    from sha3 import keccak_256
except ImportError:
    # pycryptodome
    from Crypto.Hash import keccak
    # keccak_256 = lambda *args: keccak.new(*args, digest_bits=256)
    keccak_256 = lambda data=None: keccak.new(data=data, digest_bits=256)