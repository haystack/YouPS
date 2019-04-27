#!/bin/sh
set -e

# remove existing cron jobs
rm -rf /var/spool/cron/crontabs && mkdir -m 0644 -p /var/spool/cron/crontabs

# copy cron jobs from /etc/cron.d 
[ "$(ls -A /etc/cron.d)" ] && cp -f /etc/cron.d/* /var/spool/cron/crontabs/ || true

# change permissions
chmod -R 0644 /var/spool/cron/crontabs

# run cron jobs in background and log to the logging file
# crond -s /var/spool/cron/crontabs -b -L /home/ubuntu/production/mailx/logs/cron.log 

# run cron jobs in background
crond -s /var/spool/cron/crontabs -b 

exec "$@"