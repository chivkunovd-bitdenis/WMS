import datetime,json
from app.core.settings import settings
print(json.dumps({'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'label_template_enabled':settings.label_template_enabled}))
