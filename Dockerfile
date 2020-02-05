FROM openjdk:slim
COPY --from=python:2 / /
# FROM python:2
ENV PYTHONUNBUFFERED 1
RUN apt-get update && apt-get install -y \
    telnet \
    default-mysql-client \
    cron && \
    rm -rf /var/lib/apt/lists/*
# Install OpenJDK-7
# RUN add-apt-repository ppa:openjdk-r/ppa && \
#     apt-get update && \
#     apt-get install -y openjdk-7-jdk && \
#     apt-get install -y ant && \
#     apt-get clean;
RUN mkdir -p /home/ubuntu/production/mailx
WORKDIR /home/ubuntu/production/mailx
COPY ./murmur-env/. /opt/murmur/
COPY tasks-cron-docker /etc/cron.d/tasks-cron
RUN crontab /etc/cron.d/tasks-cron
COPY requirements.docker.txt /home/ubuntu/production/mailx/requirements.txt
RUN pip install -r requirements.txt --no-cache-dir
# COPY . /home/ubuntu/production/mailx/