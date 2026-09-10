import datetime,json
from app.core.settings import settings
print(json.dumps({'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'app_env':settings.app_env,'ozon_live_api_enabled':settings.ozon_live_api_enabled}))
