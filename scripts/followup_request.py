"""One provider request in a child process; parent enforces an absolute deadline."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forensics.runner import Client

request = json.loads(sys.stdin.buffer.read())
try:
    response = Client(request["config"], request["max_tokens"]).complete(request["messages"], request["tools"])
    sys.stdout.buffer.write(json.dumps(response).encode("utf8"))
except Exception as error:
    status = re.search(r"Provider HTTP [0-9]{3}", str(error))
    sys.stderr.write(status.group() if status else type(error).__name__)
    sys.exit(1)
