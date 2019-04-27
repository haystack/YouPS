#!/bin/bash
# stop on errors
set -e

# file to lock 
pidfile="/home/ubuntu/production/mailx/loop_sync_user_inbox.lock"
 
# lock it
exec 200>$pidfile
flock 200 || exit 1
 
## Your code:

# read the users email
if [ $# -eq 0 ]; then
    read -p "Please enter your email: " email
    echo 
else
    email=$1
fi

# run our code
python manage.py shell <<EOF
from schema.youps import *
me = ImapAccount.objects.get(email="$email")
me.execution_log = ""
MessageSchema.objects.filter(imap_account=me).delete()
FolderSchema.objects.filter(imap_account=me).delete()
BaseMessage.objects.filter(imap_account=me).delete()
me.is_initialized = False
me.save()
EOF

