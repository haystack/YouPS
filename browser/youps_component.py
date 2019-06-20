from django.template import Context, Template, loader
from django.http import HttpResponse

import json
import logging
from engine.constants import msg_code

from schema.youps import (FolderSchema, ImapAccount, MailbotMode, MessageSchema, EmailRule)

logger = logging.getLogger('youps')  # type: logging.Logger

request_error = json.dumps({'code': msg_code['REQUEST_ERROR'], 'status': False})

def load_new_editor(request):
    email_rule_folder = []
    rules = []
    editors = []
    try:
        if request.user.id != None:
            imap = ImapAccount.objects.filter(email=request.user.email)
            
            if imap.exists():
                if request.POST['load_exist']:
                    is_initialized = imap[0].is_initialized

                    current_mode = imap[0].current_mode

                    modes = MailbotMode.objects.filter(imap_account=imap[0])
                    mode_exist = modes.exists()

                    if is_initialized:
                        # send their folder list
                        folders = FolderSchema.objects.filter(imap_account=imap[0]).values('name')
                    
                        folders = [f['name'].encode('utf8', 'replace') for f in folders]

                        # mode_folder = MailbotMode_Folder.objects.filter(imap_account=imap[0])
                        # mode_folder = [[str(mf.folder.name), str(mf.mode.uid)] for mf in mode_folder]

                        rules = EmailRule.objects.filter(mode__imap_account=imap[0])
                        

                        for rule in rules:
                            for f in rule.folders.all():
                                email_rule_folder.append( [f.name.encode('utf8', 'replace'), int(rule.uid)]  )

                            c = {'rule': rule}
                            logger.info('youps/%s.html' % rule.type.replace("-", "_"))
                            template = loader.get_template('youps/%s.html' % rule.type.replace("-", "_"))

                            e = {'type': rule.type, 'mode_uid': rule.mode.uid, 'template': template.render(Context(c))}

                            editors.append( e )
    except Exception as e:
		logger.debug(e)
		return HttpResponse(request_error, content_type="application/json")


    return HttpResponse(json.dumps({"editors": editors, "status": True, "code": 200}), content_type="application/json")
