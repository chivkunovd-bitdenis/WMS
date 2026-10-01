# Preserve the verified running WMS-627 image; replace only the FBS pick module.
ARG WMS628_BASE_IMAGE=wms-prod-api:wms627-660bc5c7
FROM ${WMS628_BASE_IMAGE}
ARG WMS628_SOURCE_SHA
ARG WMS628_BASE_IMAGE_ID
LABEL org.opencontainers.image.revision=${WMS628_SOURCE_SHA}
LABEL wms.hotfix="WMS-628"
LABEL wms.base-image-id=${WMS628_BASE_IMAGE_ID}
COPY app/services/fbs_picking_service.py /app/app/services/fbs_picking_service.py
