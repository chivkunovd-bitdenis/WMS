FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV WB_EMULATOR_DB_PATH=/data/wb_emulator.sqlite

RUN pip install --no-cache-dir -U pip

COPY wb_emulator/requirements.txt /app/wb_emulator/requirements.txt
RUN pip install --no-cache-dir -r /app/wb_emulator/requirements.txt

COPY wb_emulator /app/wb_emulator

RUN mkdir -p /data
VOLUME /data

EXPOSE 8000

CMD ["uvicorn", "wb_emulator.main:app", "--host", "0.0.0.0", "--port", "8000"]
