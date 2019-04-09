#!/bin/bash
read -p "Please enter your email: " email
echo 

python manage.py shell <<EOF
from schema.youps import *
me = ImapAccount.objects.get(email="$email")
FolderSchema.objects.filter(imap_account=me).delete()
me.is_initialized = False
me.save()
EOF