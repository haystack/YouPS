from django.core.management.base import BaseCommand, CommandError
from smtp_handler.utils import *
from http_handler.settings import BASE_URL, DEFAULT_FROM_EMAIL, WEBSITE
from schema.models import *
import datetime
from schema.youps import EmailRule, ImapAccount

class Command(BaseCommand):
    args = ''
    help = 'Collect users script at the moment with the datetime'

    def file_write(self, s, f):
        try: 
            f.write(s)
        except:
            for body_charset in 'US-ASCII', 'ISO-8859-1', 'UTF-8':
                try:
                    s.encode(body_charset)
                except UnicodeEncodeError:
                    pass
                else:
                    break
                        
            f.write(s.encode(body_charset))

    def handle(self, *args, **options):
        path = 'user_scripts/'
        currentDate = str(datetime.datetime.now().date())

        for user in ImapAccount.objects.filter():
            with open(path + user.email + "_" + currentDate + ".py", 'w') as f:
                for e in EmailRule.objects.filter(mode__imap_account=user):
                    f.write("# Rule: %s (%s)\n" % (e.name, e.type))
                    self.file_write(e.code, f)
                    f.write("\n\n")

                f.write("\n\n#######command \n\n")

                for e in EmailRule.objects.filter(imap_account=user, type='shortcut'):
                    f.write("# Command: %s \n" % (e.name))
                    self.file_write(e.code, f)
                    f.write("\n\n")

