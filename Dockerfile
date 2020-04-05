FROM openjdk:slim
COPY --from=python:2 / /
# FROM python:2
ENV PYTHONUNBUFFERED 1
RUN apt-get update && apt-get install -y \
    ant \ 
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
# install jpype for python-java bindings
# COPY ./usr/java/openjdk-13/ ./usr/lib/jvm/
# RUN git clone https://github.com/originell/jpype.git && \
#     cd jpype && \
#     sed -i "s/elif jc.isSubclass('java.util.Iterator').*/elif jc.isSubclass('java.util.Iterator') and (members.has_key('next') or members.has_key('__next__')):/g" /jpype/jpype/_jcollection.py && \
#     JAVA_HOME=/usr/java/openjdk-13 python setup.py install
# RUN git clone https://github.com/originell/jpype.git && \
#     cd jpype && \
#     JAVA_HOME=/usr/java/openjdk-13 python setup.py install
RUN mkdir -p /home/ubuntu/production/mailx
WORKDIR /home/ubuntu/production/mailx
COPY ./murmur-env/. /opt/murmur/
COPY tasks-cron-docker /etc/cron.d/tasks-cron
RUN crontab /etc/cron.d/tasks-cron
COPY requirements.docker.txt /home/ubuntu/production/mailx/requirements.txt
RUN pip install -r requirements.txt --no-cache-dir
RUN python -m spacy download en_core_web_sm
# COPY . /home/ubuntu/production/mailx/