import xxhash
import json
import pathlib
from datetime import datetime

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

def publish():
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    data = {
        "time": datetime.now(tz=ZoneInfo("Asia/Shanghai")).isoformat(),
        "hash": hash(pathlib.Path.cwd()),
    }

    with open("version.json", "w") as f:
        json.dump(data, f)
