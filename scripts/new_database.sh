#!/bin/bash

# make sure the user has update the database name in private.py
read -p "Have you updated the database name in private.py? (yes/no): "
if [ "$REPLY" != "yes" ]; then
   exit
fi

# go to the root file
cd ~/production/mailx || exit;

# remove previous migrations
cd schema/migrations || exit;
# removes all migrations except __init__.py and __init__.pyc
ls | grep -v __init__.py | xargs -r rm;
cd ~/production/mailx;

# get the name of the mysql database
echo -n Database Name:
read databaseName
echo 

# get the mysql password
echo -n MySql Password: 
read -s password
echo

# create the new database
mysql -u root -p$password <<EOF
    create database $databaseName;
    grant all privileges ON $databaseName.* TO root@localhost;
EOF

# create the initial tables
python manage.py syncdb;

# create the initial schema migration with south
python manage.py schemamigration schema --initial;

# apply the schema migration
python manage.py migrate schema

# apply the djcelery migration
python manage.py migrate djcelery

# alter tables to utf8
mysql -u root -p$password <<EOF
    ALTER TABLE
        youps_folder
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;

    ALTER TABLE
        youps_message
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
        schema_action
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;

    ALTER TABLE
        youps_contact
        CONVERT TO CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci;

EOF

echo -e "\e[33mMake sure to update the database name in private.py to \n \e[1m$databaseName\e[0m"


