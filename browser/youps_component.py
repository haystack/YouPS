from django.template import Context, Template, loader

import json
import logging

from schema.youps import (FolderSchema, ImapAccount, MailbotMode, MessageSchema, EmailRule)

logger = logging.getLogger('youps')  # type: logging.Logger

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

                            editors.append(e)
    except Exception as e:
        logger.info(e)
    # mark_current = False	
	# tab_contents = []
	# for mode in modes:
	# 	if current_mode == None or mark_current == True:
	# 		mark_current = False
		
	# 	c = {'rules':rules, 'mode': mode}
	# 	msg = loader.get_template('youps/new_message.html')
	# 	flag = loader.get_template('youps/flag_change.html')
	# 	deadline = loader.get_template('youps/deadline.html')
	# 	shortcut = loader.get_template('youps/shortcut.html')
	
	# 	c = {'new_message': msg.render(Context(c)), 'flag_change': flag.render(Context(c)), 'deadline': deadline.render(Context(c)), 'shortcut': shortcut.render(Context(c)), 'mark_current': mark_current}

	# 	tab_content = loader.get_template('youps/tab_content.html')

	# 	tab_contents.append(tab_content)
	# logger.info(msg.render(Context(c)))

	# c = {'modes':modes}

	# c = {'user': request.user, 'is_test': is_test, 'is_running': is_running, 'is_initialized': is_initialized,
	# 	'folders': folders, 'rule_folder': email_rule_folder,'mode_exist': mode_exist, 'modes': modes, 'rules':rules, 'current_mode': current_mode,
	# 	'imap_authenticated': imap_authenticated, 'website': WEBSITE, 
	# 	'shortcuts_exist': shortcuts_exist, 'shortcuts': shortcuts}

	# t = loader.get_template('youps/login_email.html')

    logger.info(editors)

    return HttpResponse(json.dumps({"res": editors}), content_type="application/json")
