FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Base utilities + Python for the in-container proxy. Playwright + Chromium
# are NOT needed inside the agent container — rendering happens in the
# verifier container. Keeping this image lean speeds up agent cold-start.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    coreutils \
    python3 \
 && rm -rf /var/lib/apt/lists/*

COPY proxy.py /opt/proxy.py
COPY entrypoint.sh /entrypoint.sh
COPY reference /reference
RUN chmod +x /entrypoint.sh /opt/proxy.py

# Route all HTTP(S) traffic through the in-container egress-logging proxy.
ENV HTTP_PROXY=http://127.0.0.1:8080 \
    HTTPS_PROXY=http://127.0.0.1:8080 \
    http_proxy=http://127.0.0.1:8080 \
    https_proxy=http://127.0.0.1:8080 \
    NO_PROXY=127.0.0.1,localhost \
    no_proxy=127.0.0.1,localhost

WORKDIR /app

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sleep", "infinity"]
