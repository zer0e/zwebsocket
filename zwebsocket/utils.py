def prepare_data(data):
    if isinstance(data, str):
        return data.encode("utf-8")
    elif isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    else:
        raise TypeError("data must be str or byte")
