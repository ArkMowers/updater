import xxhash
import json
import pathlib


def hash(path):
    p = pathlib.Path(path)
    result = {}
    for i in p.glob("**/*"):
        if i.is_file():
            with i.open("rb") as f:
                hex = xxhash.xxh64(f.read()).hexdigest()
                relative_path = str(i)[len(str(p)) + 1 :].replace("\\", "/")
                result[relative_path] = hex
    return result
