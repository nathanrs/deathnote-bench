FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates procps && rm -rf /var/lib/apt/lists/*
RUN useradd -m -s /bin/bash agent
COPY game_root/ /opt/game/
RUN mkdir -p /opt/game/state /logs /app && chmod -R go-rwx /opt/game && chmod 777 /logs && chmod 755 /root \
    && install -m 755 /opt/game/game /usr/local/bin/game && chown -R agent:agent /app
WORKDIR /app
CMD ["bash", "-c", "bash /opt/game/start.sh; sleep infinity"]
