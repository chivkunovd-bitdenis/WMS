import datetime,json
from app.core.settings import settings
print(json.dumps({'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'dadata_configured':bool(settings.dadata_token)}))
