#!/bin/bash
cd ~/production/mailx || exit;

# remove previous migrations
cd schema/migrations || exit;
# removes all migrations except __init__.py and __init__.pyc
ls | grep -v __init__.py | xargs rm
cd ~/production/mailx;

# get the name of the mysql database
echo -n Database Name:
read -s databaseName
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

echo -e "\e[33mMake sure to update the database name in private.py to \n \e[1m$databaseName"


