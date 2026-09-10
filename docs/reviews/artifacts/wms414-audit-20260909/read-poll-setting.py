import datetime,json
from app.core.settings import settings
print(json.dumps({'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'fbs_poll_interval_sec':settings.fbs_poll_interval_sec}))
