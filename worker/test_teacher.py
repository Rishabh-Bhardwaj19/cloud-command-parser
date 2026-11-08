
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

PROMPT_PATH = Path("prompts/teacher_prompt.txt")
MODEL = "phi3.5"

ALLOWED_INTENTS = [
    "alarm_set",
    "alarm_query",
    "calendar_set",
    "calendar_query",
    "calendar_remove",
    "weather_query",
    "datetime_query",
    "recommendation_events"
]

EXPECTED_KEYS = {"intent", "date", "time", "place"}

# JSON Schema to enforce the four required keys
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ALLOWED_INTENTS
        },
        "date": {"type": ["string", "null"]},
        "time": {"type": ["string", "null"]},
        "place": {"type": ["string", "null"]}
    },
    "required": ["intent", "date", "time", "place"],
    "additionalProperties": False
}


def call_teacher(command):

    # Read the saved teacher prompt
    prompt_template = PROMPT_PATH.read_text(
        encoding="utf-8"
    ).strip()

    full_prompt = prompt_template + "\n" + command

    # Prepare Ollama request
    payload = {
        "model": MODEL,
        "prompt": full_prompt,
        "format": OUTPUT_SCHEMA,
        "stream": False,
        "options": {
            "temperature": 0,
            "seed": 42,
            "num_ctx": 2048
        }
    }

    request = Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urlopen(request, timeout=300) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        # Preserve the teacher's exact generated response
        teacher_raw = result["response"]

        print("\nRaw teacher response:")
        print(teacher_raw)

        # Parse only for validation, never modify the raw output
        parsed = json.loads(teacher_raw)

        valid = True

        if not isinstance(parsed, dict):
            print("\nINVALID: Output is not a JSON object.")
            return

        if set(parsed.keys()) != EXPECTED_KEYS:
            print("\nINVALID: Incorrect JSON keys.")
            valid = False

        if parsed.get("intent") not in ALLOWED_INTENTS:
            print("\nINVALID: Intent is not allowed.")
            valid = False

        for slot in ("date", "time", "place"):
            value = parsed.get(slot)

            if value is not None:
                if not isinstance(value, str):
                    print(f"\nINVALID: {slot} must be text or null.")
                    valid = False
                elif value not in command:
                    print(f"\nINVALID: {slot} not found in command.")
                    valid = False

        print(
            "\nValidation result:",
            "PASS" if valid else "FAIL"
        )

    except json.JSONDecodeError:
        print("\nINVALID: Teacher returned invalid JSON.")

    except (HTTPError, URLError, TimeoutError) as error:
        print("\nOllama API error:", error)

    except (KeyError, TypeError) as error:
        print("\nUnexpected API response:", error)


if __name__ == "__main__":
    user_command = input("Enter a command: ").strip()

    if user_command:
        call_teacher(user_command)
    else:
        print("Command cannot be empty.")
