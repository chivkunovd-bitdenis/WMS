# Preserve the running API baseline, overlay only WMS-627 source from Git.
ARG WMS627_BASE_IMAGE=wms-prod-api:wms622-addb225f
FROM ${WMS627_BASE_IMAGE}
ARG WMS627_SOURCE_SHA
LABEL org.opencontainers.image.revision=${WMS627_SOURCE_SHA}
LABEL wms.hotfix="WMS-627"
COPY app/services/fbs_observed_delivery_service.py /app/app/services/fbs_observed_delivery_service.py
COPY app/services/fbs_tracking_service.py /app/app/services/fbs_tracking_service.py
COPY app/services/wb_marketplace_orders_service.py /app/app/services/wb_marketplace_orders_service.py
