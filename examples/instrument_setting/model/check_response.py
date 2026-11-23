"""Feed the stand-in model 1000 and pass when it reads back within 50."""
import json
import sys
from pathlib import Path

settings = json.loads(Path("model/settings.json").read_text(encoding="utf-8"))
fed = 1000
read = fed * (0.97 if settings["correction"] == "on" else 1.00)
print("fed {0}, read {1:.0f}, correction {2}".format(fed, read, settings["correction"]))
sys.exit(0 if abs(read - fed) <= 50 else 1)
