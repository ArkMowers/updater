#!/usr/bin/env python3

import json
from hash import hash
import pathlib
from datetime import datetime

data = {
    "time": datetime.now().isoformat(),
    "hash": hash(pathlib.Path.cwd()),
}

with open("version.json", "w") as f:
    json.dump(data, f)
