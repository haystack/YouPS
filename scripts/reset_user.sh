#!/bin/bash


if [ $# -eq 0 ]; then
    read -p "Please enter your email: " email
    echo 
else
    email=$1
fi



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