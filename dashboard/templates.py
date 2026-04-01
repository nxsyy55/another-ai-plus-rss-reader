from fastapi.templating import Jinja2Templates
from dateutil import parser
import datetime

templates = Jinja2Templates(directory="templates/dashboard")

def to_local_datetime(dt_str):
    if not dt_str: return None
    if isinstance(dt_str, datetime.datetime):
        return dt_str.astimezone()
    try:
        dt_utc = parser.parse(dt_str)
        return dt_utc.astimezone()
    except Exception:
        return dt_str

templates.env.filters["to_local_datetime"] = to_local_datetime
templates.env.filters["strftime"] = lambda value, format: value.strftime(format) if hasattr(value, 'strftime') else value
