# Lightweight backup runner - postgresql-client + rclone + supercronic
FROM alpine:3.24

ENV TZ=Europe/Kyiv
ENV SUPERCRONIC_VERSION=v0.2.33

RUN apk add --no-cache \
    postgresql16-client \
    rclone \
    bash \
    coreutils \
    tzdata \
    curl \
    ca-certificates \
 && cp /usr/share/zoneinfo/Europe/Kyiv /etc/localtime \
 && echo "Europe/Kyiv" > /etc/timezone

ARG TARGETARCH=amd64
RUN curl -fsSLO "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH}" \
 && chmod +x supercronic-linux-${TARGETARCH} \
 && mv supercronic-linux-${TARGETARCH} /usr/local/bin/supercronic

COPY backup.sh /usr/local/bin/backup.sh
COPY restore.sh /usr/local/bin/restore.sh
COPY crontab /etc/crontab

RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/restore.sh
RUN mkdir -p /backups

HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
  CMD pgrep supercronic || exit 1

CMD ["supercronic", "/etc/crontab"]
