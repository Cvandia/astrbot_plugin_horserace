"""Build the runtime pages/ mirror from the requested page/ authoring directory."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
source = root / "page/dashboard"
destination = root / "pages/dashboard"
destination.mkdir(parents=True, exist_ok=True)
for name in ("index.html", "app.js", "style.css", "_page.json"):
    shutil.copy2(source / name, destination / name)
print("Dashboard runtime assets synchronized.")
