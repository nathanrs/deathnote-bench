FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates procps git && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy==2.1.3 pandas==2.2.3 scipy==1.14.1
RUN useradd -m -s /bin/bash agent
COPY game_root/ /opt/game/
COPY app/ /app/
RUN mkdir -p /opt/game/state /logs && chmod -R go-rwx /opt/game && chmod 777 /logs && chmod 755 /root \
    && install -m 755 /opt/game/game /usr/local/bin/game && chown -R agent:agent /app
WORKDIR /app
CMD ["bash", "-c", "bash /opt/game/start.sh; sleep infinity"]
