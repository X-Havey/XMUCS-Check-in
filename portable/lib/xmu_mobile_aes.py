"""AES-CBC adapter for the XMU login SDK, using the bundled pyaes library."""
import pyaes


class AES:
    MODE_CBC = 2

    @staticmethod
    def new(key, mode, iv=None, **kwargs):
        if mode != AES.MODE_CBC or kwargs:
            raise ValueError("The XMU mobile login adapter supports AES-CBC only.")
        if len(key) not in (16, 24, 32) or iv is None or len(iv) != 16:
            raise ValueError("Invalid AES key or CBC IV length.")
        cipher = pyaes.AESModeOfOperationCBC(bytes(key), iv=bytes(iv))

        class CBC:
            def encrypt(self, data):
                data = bytes(data)
                if len(data) % 16:
                    raise ValueError("AES-CBC input must already be padded to 16-byte blocks.")
                return b"".join(cipher.encrypt(data[index:index + 16]) for index in range(0, len(data), 16))

        return CBC()
