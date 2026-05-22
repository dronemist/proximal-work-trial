FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Lean agent container: just Python (for the egress-logging proxy) plus base
# utils. Playwright + Chromium are installed at verifier-time, not here, to
# keep the agent's cold-start small. The reference PNGs go in alongside.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    coreutils \
    python3 \
 && rm -rf /var/lib/apt/lists/*

COPY proxy.py /opt/proxy.py
COPY entrypoint.sh /entrypoint.sh
COPY reference /reference
RUN chmod +x /entrypoint.sh /opt/proxy.py

ENV HTTP_PROXY=http://127.0.0.1:8080 \
    HTTPS_PROXY=http://127.0.0.1:8080 \
    http_proxy=http://127.0.0.1:8080 \
    https_proxy=http://127.0.0.1:8080 \
    NO_PROXY=127.0.0.1,localhost \
    no_proxy=127.0.0.1,localhost

WORKDIR /app

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sleep", "infinity"]
