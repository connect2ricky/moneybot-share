import base64
import gzip
import unittest

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from moneybot import phone

KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()


class Encrypt(unittest.TestCase):
    def test_file_opens_with_the_key(self):
        blob = phone.encrypt(b'{"a": 1}', KEY)
        self.assertEqual(blob[:4], b"MBP1")
        plain = AESGCM(base64.urlsafe_b64decode(KEY)).decrypt(blob[4:16], blob[16:], b"MBP1")
        self.assertEqual(gzip.decompress(plain), b'{"a": 1}')

    def test_each_file_uses_a_new_nonce(self):
        self.assertNotEqual(phone.encrypt(b"x", KEY)[4:16], phone.encrypt(b"x", KEY)[4:16])


if __name__ == "__main__":
    unittest.main()
