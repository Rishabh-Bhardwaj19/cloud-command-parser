"""Create deliberately invalid predictions for CI quality-gate testing."""

import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])

with source.open(encoding="utf-8") as file:
    records = [
        json.loads(line)
        for line in file
        if line.strip()
    ]

with destination.open("w", encoding="utf-8") as file:
    for record in records:
        file.write(json.dumps({
            "id": record["id"],
            "prediction": "INTENTIONALLY_INVALID_OUTPUT"
        }) + "\n")

print(
    f"Created {len(records)} deliberately invalid predictions "
    f"in {destination}"
)
