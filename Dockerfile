FROM python:3-alpine
ENV PYTHONUNBUFFERED 1
RUN apk add --no-cache mysql-client dcron su-exec bash && rm -rf /var/cache/apk/*
RUN mkdir -p /var/log/cron && mkdir -m 0644 -p /var/spool/cron/crontabs && touch /var/log/cron/cron.log && mkdir -m 0644 -p /etc/cron.d
WORKDIR /home/ubuntu/production/mailx
COPY ./murmur-env/. /opt/murmur/
COPY tasks-cron-docker /etc/cron.d/tasks-cron
COPY requirements.docker.txt /home/ubuntu/production/mailx/requirements.txt
RUN apk add --no-cache --virtual .build-deps gcc musl-dev \
    && pip install cython --no-cache-dir \
    && pip install -r requirements.txt --no-cache-dir\
    && apk del .build-deps
# COPY . /home/ubuntu/production/mailx/
# USER 1000:1000 