#!/bin/bash

# stop on errors
set -e

# stop the cron jobs
pidfile="/home/ubuntu/production/mailx/loop_sync_user_inbox2.lock"
exec 200>$pidfile
flock 200 || exit 1
pidfile="/home/ubuntu/production/mailx/register_inbox2.lock"
exec 201>$pidfile
flock 201 || exit 1

# wait for mysql to start
echo "checking that mysql has started"
while ! mysqladmin ping -h"$DATABASE_HOST" --silent; do
    sleep 1
    echo "..."
done
echo "mysql started..."

# go to the root file
cd /home/ubuntu/production/mailx && \
# remove previous migrations
cd schema/migrations && \
# removes all migrations except __init__.py and __init__.pyc
ls | grep -v __init__.py | xargs -r rm -- && \
cd /home/ubuntu/production/mailx && \

# create the new database
{ mysql -h $DATABASE_HOST -u root -p$MYSQL_PASS <<EOF
    drop database if exists $DATABASE_NAME;
    create database $DATABASE_NAME;
    grant all privileges ON $DATABASE_NAME.* TO root@localhost;
EOF
} && \

# create the initial tables
# python manage.py syncdb && \

# create the initial schema migration with south
python manage.py makemigrations schema && \

# TODO call it later
# migrate django app tables, allow latency. 
# While this isn’t recommended, the migrations framework is sometimes too slow on large projects with hundreds of models.
python manage.py migrate --noinput && \

# apply the schema migration
python manage.py migrate schema && \

# alter tables to utf8
{ mysql -h $DATABASE_HOST -u root -p$MYSQL_PASS <<EOF
    USE $DATABASE_NAME;

    ALTER TABLE
        youps_folder
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;

    ALTER TABLE
        youps_base_message
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;

    ALTER TABLE
        youps_threads
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;

    ALTER TABLE
        schema_mailbotmode
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;

    ALTER TABLE
        schema_imapaccount
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;

    ALTER TABLE
        youps_contact
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;

    ALTER TABLE
        youps_contact_alias
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;
        
    ALTER TABLE
        schema_emailrule
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;

    ALTER TABLE
        youps_calendar
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;
EOF
} && \
# set the domain name for the site
{ python manage.py shell <<EOF
from django.contrib.sites.models import Site
mysite = Site.objects.get_current()
mysite.domain = "$DOMAIN_NAME"
mysite.save()
EOF
} && \

echo "RESET Complete" || \
echo "RESET Failed"