"""Git helpers shared by the test modules that build throwaway repositories under tmp_path."""
import subprocess
from pathlib import Path

GIT_IDENTITY = (
    "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
)


def git(root: Path, *args: str) -> None:
    """Run one git command in root with a fixed test identity; raise on a non-zero exit."""
    subprocess.run(["git", *GIT_IDENTITY, "-C", str(root), *args], check=True, capture_output=True)
