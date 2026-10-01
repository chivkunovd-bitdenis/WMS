# Minimal overlay preserves the verified running production API image.
# Build with the recorded base image and the source from the published commit.
ARG WMS622_BASE_IMAGE=wms-prod-api:wms622-before
FROM ${WMS622_BASE_IMAGE}
ARG WMS622_SOURCE_SHA
LABEL org.opencontainers.image.revision=${WMS622_SOURCE_SHA}
LABEL wms.hotfix="WMS-622"
COPY backend/app/services/packaging_task_service.py /app/app/services/packaging_task_service.py
