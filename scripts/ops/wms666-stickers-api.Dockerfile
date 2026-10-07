# Preserve current runtime; web COPY retains assets used by open tabs.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG WMS_DEPLOY_SHA
LABEL org.opencontainers.image.revision=$WMS_DEPLOY_SHA
COPY backend/app/services/fbs_supply_service.py /app/app/services/fbs_supply_service.py
