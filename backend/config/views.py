from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404


def spa_index(_request):
    index_path = Path(settings.PROJECT_ROOT) / "frontend" / "dist" / "index.html"
    if not index_path.exists():
        raise Http404("Frontend build not found. Run `npm run build` in frontend first.")
    return FileResponse(index_path.open("rb"), content_type="text/html")
