from pathlib import Path

from fastapi.templating import Jinja2Templates

from . import services

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.filters["hm"] = services.fmt_hm
templates.env.filters["hrs"] = services.hours
