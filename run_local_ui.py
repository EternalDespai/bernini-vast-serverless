"""One-command Windows/Linux local UI launcher (after .env configuration)."""
import os
from pathlib import Path

from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).with_name(".env"))
    required = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
                "R2_BUCKET", "VAST_API_KEY", "BERNINI_VAST_GENERATE_URL",
                "BERNINI_WORKFLOW_PATH")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise SystemExit("Configure .env first; missing: " + ", ".join(missing))
    workflow = Path(os.environ["BERNINI_WORKFLOW_PATH"])
    if not workflow.is_file():
        raise SystemExit(f"Workflow file not found: {workflow}")
    import uvicorn
    print("Bernini local UI: http://127.0.0.1:8765", flush=True)
    uvicorn.run("local_ui:app", host="127.0.0.1", port=8765, workers=1)


if __name__ == "__main__":
    main()
