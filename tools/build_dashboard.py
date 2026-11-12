"""Build the runtime pages/ mirror from the requested page/ authoring directory."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
source = root / "page/dashboard"
destination = root / "pages/dashboard"
destination.mkdir(parents=True, exist_ok=True)
for path in source.rglob("*"):
    if path.is_file():
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
print("Dashboard runtime assets synchronized.")
