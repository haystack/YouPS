from django.template import Context, Template, loader
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render_to_response, render

import json
import logging
from engine.constants import msg_code

import engine.main
from schema.models import UserProfile
from schema.youps import (FolderSchema, ImapAccount, MailbotMode, MessageSchema, EmailRule, EmailRule_Args)
from http_handler.settings import PROTOCOL, BASE_URL

logger = logging.getLogger('youps')  # type: logging.Logger

request_error = json.dumps({'code': msg_code['REQUEST_ERROR'], 'status': False})

def get_base_code(rule_type):
    d = {
        "new-message": """def on_message(my_message):
    # my_message is a Message instance of a newly arrived message
    # You can choose to run this rule only if the message is arrived in certain folders by selecting them at the left panel
    print(my_message.recipients)
    if my_message.sender not in ['me@email.com', 'advisor@email.com']:
        my_message.see_later()""",
        "deadline": """def on_deadline(my_message):
    # my_message is a Message instance 
    # this function executes at my_message.deadline
    # by default, Message instances does not have deadline otherwise you specify it
    pass""",
        "flag-change": "def on_flag_added(my_message, added_flags):\n    pass\n\ndef on_flag_removed(my_message, removed_flags):",
        "shortcut": """def on_command(my_message, kargs):
    # shortcut is a custom add-on feature. Create shortcuts and use them at %s://%s/button 
    # my_message is a Message instance 
    # kargs is a dictionary that contains arguments you specify at the left panel e.g., kargs['arg_name']
    def highlight(msg):
        if not msg.is_replied:
            msg.mark_unread()
    my_message.on_time(highlight, 300)""" % (PROTOCOL, BASE_URL)
    }

    return d[rule_type]

def create_new_editor(imap_account, rule_type, mode_id):
    editors = []
    
    rule_name = ""
    if "new-message" in rule_type:
        rule_name = "My email filters"
    elif "deadline" in rule_type:
        rule_name = "Message deadline handler"
    else:
        rule_name = "My email shortcut"

    new_er = None
    if rule_type != "shortcut":
        try:
            new_er = EmailRule(name=rule_name, type=rule_type, mode=MailbotMode.objects.get(id=mode_id), code=get_base_code(rule_type))
        except MailbotMode.DoesNotExist:
            new_mm = MailbotMode(imap_account=imap_account)
            new_mm.save()

            new_er = EmailRule(name=rule_name, type=rule_type, mode=new_mm, code=get_base_code(rule_type))
    else:
        new_er = EmailRule(name=rule_name, type=rule_type, imap_account=imap_account, code=get_base_code(rule_type))
    new_er.save()

    user_inbox = FolderSchema.objects.get(imap_account=imap_account, name__iexact="inbox")
    new_er.folders.add(user_inbox)

    test_folder = FolderSchema.objects.filter(imap_account=imap_account, name="_YouPS exercise")
    if test_folder.exists():
        new_er.folders.add(test_folder[0])

    logger.info(new_er.folders.exists())
    folders = FolderSchema.objects.filter(imap_account=imap_account)
    c = {'rule': new_er, 'folders': folders}
    # logger.info('youps/%s.html' % rule_type.replace("-", "_"))
    template = loader.get_template('youps/components/%s.html' % rule_type.replace("-", "_"))

    e = {'template': template.render(Context(c))}

    editors.append( e )

    return editors

def load_new_editor(request):
    email_rule_folder = []
    rules = []
    editors = []

    try:
        if request.user.id != None:
            imap = ImapAccount.objects.filter(email=request.user.email)
            
            if imap.exists():
                # Load existing rule
                if True if request.POST['load_exist'] == "true" else False:
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
                        rules = None
                        if request.POST['type'] == "shortcut":
                            rules = EmailRule.objects.filter(imap_account=imap[0])
                        else:
                            rules = EmailRule.objects.filter(mode__imap_account=imap[0])
                        # logger.info(rules)

                        for rule in rules:
                            for f in rule.folders.all():
                                email_rule_folder.append( [f.name.encode('utf8', 'replace'), int(rule.id)]  )

                            folders = FolderSchema.objects.filter(imap_account=imap[0])
                            c = {'rule': rule, 'folders': folders}
                            rule_type = rule.type
                            if request.POST['type'] and request.POST['type'] != rule_type:
                                continue
                            if rule_type == "shortcut":
                                args = EmailRule_Args.objects.filter(rule=rule)
                                c = {'rule': rule, 'folders': folders, 'args': args}
                            elif rule_type.startswith("new-message"):
                                rule_type = "new-message"
                            
                            logger.debug('youps/%s.html' % rule_type.replace("-", "_"))
                            template = loader.get_template('youps/components/%s.html' % rule_type.replace("-", "_"))

                            e = {'type': rule_type, 'mode_uid': -1 if not rule.mode else rule.mode.id, 'template': template.render(Context(c))}

                            editors.append( e )

                            logger.debug(editors)
                # create a new rule
                else:
                    rule_type = request.POST['type']
                    mode_id = request.POST['mode'] if "mode" in request.POST else -1

                    editors = create_new_editor(imap[0], rule_type, mode_id)
    except Exception as e:
		logger.exception(e)
		return HttpResponse(request_error, content_type="application/json")


    return HttpResponse(json.dumps({"editors": editors, "status": True, "code": 200}), content_type="application/json")


@login_required
def create_mailbot_mode(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)

		event_type = ["new_message", "flag_change", "deadline", "shortcut"]
		c= {}
		for component in event_type:
			template = loader.get_template('youps/components/%s-add.html' % component)
			c[component] = template.render(Context({}))

		res = engine.main.create_mailbot_mode(user, request.user.email)
        
		c["mode_id"] = res["mode-id"]
		logger.debug(c)

		template = loader.get_template('youps/components/mode.html')
		new_mode = template.render(Context(c))
		res['new_mode'] = new_mode

		return HttpResponse(json.dumps(res), content_type="application/json")
	except Exception, e:
		logger.exception(e)
		return HttpResponse(request_error, content_type="application/json")