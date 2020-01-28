import base64, json, logging,traceback

from annoying.decorators import render_to
from boto.s3.connection import S3Connection
from html2text import html2text
from salmon.mail import MailResponse

from django.contrib.auth.decorators import login_required
from django.conf import global_settings
from django.contrib.auth.forms import AuthenticationForm
from django.core.context_processors import csrf
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models.aggregates import Count
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render_to_response, render
from django.template.context import RequestContext
from django.utils.encoding import *
from django.template import Context, Template, loader
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder

from nylas import APIClient

from browser.util import load_groups, paginator, get_groups_links_from_roles, get_role_from_group_name
import engine.main
from engine.constants import msg_code
from http_handler.settings import WEBSITE, AWS_STORAGE_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, NYLAS_ID, NYLAS_SECRET
from registration.forms import RegistrationForm
from schema.youps import ImapAccount, MailbotMode, FolderSchema, EmailRule, EmailRule_Args
from smtp_handler.utils import *
import logging

from browser.youps_component import load_new_editor, create_mailbot_mode

logger = logging.getLogger('youps')  # type: logging.Logger

request_error = json.dumps({'code': msg_code['REQUEST_ERROR'], 'status': False})

if WEBSITE == 'murmur':
	group_or_squad = 'group'
elif WEBSITE == 'squadbox':
	group_or_squad = 'squad'

def lamson_status(request):
	import psutil
	response_text = ""
	if "lamson" in [psutil.Process(i).name() for i in psutil.pids()]:
		response_text = "lamson running"
	response = HttpResponse(response_text)
	return response

def logout(request):
	request.session.flush()
	return HttpResponseRedirect('/')

@render_to(WEBSITE+'/about.html')
def about(request):
	return {}

@render_to('404.html')
def error(request):
	res = {'website': WEBSITE}
	
	error = request.GET.get('e')
	if error == 'gname':
		res['error'] = '%s is not a valid group name.' % request.GET['name']
	elif error == 'admin':
		res['error'] = 'You do not have the admin privileges to visit this page.'
	elif error == 'member':
		res['error'] = 'You need to be a member of this group to visit this page.'
	elif error == 'perm':
		res['error'] = 'You do not have permission to visit this page.'
	elif error == 'thread':
		res['error'] = 'This thread no longer exists.'
	else:
		res['error'] = 'Unknown error.'
	return res


def index(request):
	homepage = "%s/home.html" % WEBSITE
	return HttpResponseRedirect('/editor')
			
@render_to("settings.html")
@login_required
def settings(request):
	user = get_object_or_404(UserProfile, email=request.user.email)
	
	return {'user': request.user, 'website' : WEBSITE, 'group_page' : True}

@render_to(WEBSITE+"/login_email.html")
def login_imap_view(request):
	imap_authenticated = False
	is_test = False
	is_running = False
	mode_exist = False
	modes = []
	current_mode = None
	shortcuts = ''
	is_initialized = False 
	folders = []
	email_rule_folder = []
	rules = []

	try: 
		if request.user.id != None:
			imap = ImapAccount.objects.filter(email=request.user.email)
			
			if imap.exists():
				if (imap[0].is_oauth and imap[0].access_token != "") or (not imap[0].is_oauth and imap[0].password != ""):
					imap_authenticated = True
					is_test = imap[0].is_test
					is_running = imap[0].is_running
					is_initialized = imap[0].is_initialized

					current_mode = imap[0].current_mode

					modes = MailbotMode.objects.filter(imap_account=imap[0])
					logger.info(modes.values())
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
								email_rule_folder.append( [f.name.encode('utf8', 'replace'), int(rule.id)]  )

		return {'user': request.user, 'is_test': is_test, 'is_running': is_running, 'is_initialized': is_initialized,
			'folders': folders, 'rule_folder': email_rule_folder,'mode_exist': mode_exist, 'modes': modes, 'rules':rules, 'current_mode': current_mode,
			'imap_authenticated': imap_authenticated, 'website': WEBSITE, 'shortcuts': shortcuts}
	except Exception as e:
		logger.exception(e)
		return {'user': request.user, 'website': WEBSITE}

# Nylas login callback
def login_imap_callback(request):
	res = {'website': WEBSITE}
	
	# logger.info(request)
	code = "OAQABAAIAAABeAFzDwllzTYGDLh_qYbH81VUHF"#request.GET['code']

	# Exchange the authorization code for an access token
	client = APIClient(NYLAS_ID, NYLAS_SECRET)
	logger.info(code)
	access_token = client.token_for_code(code)
	logger.info(access_token)

	return HttpResponseRedirect('/editor')

@render_to(WEBSITE+"/docs.html")
def docs_view(request):
	return {'website': WEBSITE}

@render_to(WEBSITE+"/about.html")
def about_view(request):
	return {'website': WEBSITE}

@render_to(WEBSITE+"/calendar.html")
def calendar_view(request):
	return {'website': WEBSITE}

@render_to(WEBSITE+"/privacy.html")
def privacy_view(request):
	return {'website': WEBSITE}

@render_to(WEBSITE+"/email_button.html")
def email_button_view(request):
	try: 
		if request.user.email:
			imap_account = ImapAccount.objects.get(email=request.user.email)
			folders = FolderSchema.objects.filter(imap_account=imap_account).filter(is_selectable=True).values('name')
						
			folders = [f['name'].encode('utf8', 'replace') for f in folders]

			email_rules = EmailRule.objects.filter(mode__imap_account=imap_account, type__startswith='shortcut')

			today = timezone.now()
			return {'website': WEBSITE, 'folders': folders, 'email_rules': email_rules, 'imap_authenticated': True, 'is_gmail': imap_account.is_gmail, 'YEAR': today.year, 'MONTH': "%02d" % today.month, 'DAY': "%02d" % today.day}
	except ImapAccount.DoesNotExist:
		return {'website': WEBSITE, 'folders': [], 'imap_authenticated': False}
	except:
		return {'website': WEBSITE, 'folders': [], 'imap_authenticated': False}

@login_required
def get_email_rule_meta(request):
	res = {'status' : False}

	try: 
		logger.exception(request.user.email)
		if request.user.email:
			imap_account = ImapAccount.objects.get(email=request.user.email)

			# serializing
			email_rules = []
			for obj in EmailRule.objects.filter(mode__imap_account=imap_account, type__startswith='shortcut'):
				email_rules.append( {"name": obj.name, "email": obj.get_forward_addr(), "id": obj.id, "params": [{"name": era["name"], "type": era["type"], "html": _load_component(era["type"], {"name": era["name"]})} for era in EmailRule_Args.objects.filter(rule=obj).values('name', 'type')]} )
			logger.exception(email_rules)


			res['rules'] = email_rules
			logger.exception(res)
			logger.exception(json.dumps(res))
			return HttpResponse(json.dumps(res), content_type="application/json")
	except ImapAccount.DoesNotExist:
		return {'website': WEBSITE, 'imap_authenticated': False}
	except Exception as e:
		logger.exception(e)
		return {'website': WEBSITE, 'imap_authenticated': False}

def _load_component(component, context=None):

	try:
		template = loader.get_template('youps/components/%s.html' % component)
		c = {}
		logger.info(component)
		if component == 'string':
			c = {"name": context["name"] if context else ""}
		elif component == 'datetime':
			# TODO if base msg has deadline
			# set as the deadline
			# else today date
			today = timezone.now()
			
			c = {'user_datetime': today.strftime('%Y-%m-%dT00:00'), "name": context["name"]} 		
		elif component == "email_expandable_row":
			c = {'sender': context['sender'], "subject": context['subject'], "date": context['date'], "message_id": context['message_id']}
			logger.info(c)
		return template.render( Context(c) )

	except Exception as e:
		logger.info(e)
		raise e
	

def load_components(request):
	res = {"status": True, "code": 200}

	try:
		component = request.POST['component']
		logger.info(component)
		# basemsg_uid = request.POST['FILL HERE']
		
		res['template'] = _load_component(component, res['context'])

		return HttpResponse(json.dumps(res), content_type="application/json")
	except Exception as e:
		logger.info(e)
		return HttpResponse(request_error, content_type="application/json")

		
@login_required
def login_imap(request):
	try:
		# TODO nylas https://docs.nylas.com/reference#oauth - oauth/tokenize and receive code
		user = get_object_or_404(UserProfile, email=request.user.email)

		# email = request.POST['email']
		host = request.POST['host']
		is_oauth = True if request.POST['is_oauth'] == "true" else False
		password = request.POST['password']

		res = engine.main.login_imap(user.email, password, host, is_oauth)
		return HttpResponse(json.dumps(res), content_type="application/json")
	except Exception as e:
		logger.exception(e)
		return HttpResponse(request_error, content_type="application/json")

@login_required
def apply_button_rule(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)
		 
		msg_schema_id = request.POST['msg_id']
		er_id = request.POST['er_id']
		kargs = json.loads(request.POST.get('kargs'))
		res = engine.main.apply_button_rule(user, request.user.email, er_id, msg_schema_id, kargs)
		
		return HttpResponse(json.dumps(res, cls=DjangoJSONEncoder), content_type="application/json")
	except Exception as e:
		logger.exception(e)
		return HttpResponse(request_error, content_type="application/json")

@login_required
def fetch_execution_log(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)
		from_id = None if not request.POST['from_id'] else request.POST['from_id']
		to_id = None if not request.POST['to_id'] else request.POST['to_id']

		res = engine.main.fetch_execution_log(user, request.user.email, from_id, to_id)
		return HttpResponse(json.dumps(res), content_type="application/json")
	except Exception as e:
		logger.exception(e)
		return HttpResponse(request_error, content_type="application/json")

@login_required
def fetch_watch_message(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)
		
		watched_message = request.POST.getlist('watched_message[]')

		res = engine.main.fetch_watch_message(user, request.user.email, watched_message)

		res['message_rows'] = []
		for context in res['contexts']:
			res['message_rows'].append( _load_component("email_expandable_row", context) )
			
		return HttpResponse(json.dumps(res), content_type="application/json")
	except EmailRule.DoesNotExist:
		logger.exception("where did er go??")
		return HttpResponse(request_error, content_type="application/json")
	except Exception as e:
		logger.exception(e)
		return HttpResponse(request_error, content_type="application/json")

@login_required
def folder_recent_messages(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)

		folder_name = request.POST['folder_name']
		N = request.POST['N']

		# res = engine.main.folder_recent_messages(user, user.email, folder_name, N)
		return HttpResponse(None, content_type="application/json")
	except Exception as e:
		logging.debug(e)
		return HttpResponse(request_error, content_type="application/json")

@login_required
def remove_rule(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)
		
		rule_id = request.POST['rule-id']
		res = engine.main.remove_rule(user, request.user.email, rule_id)
		return HttpResponse(json.dumps(res), content_type="application/json")
	except Exception as e:
		logging.debug(e)
		return HttpResponse(request_error, content_type="application/json")

@login_required
def run_mailbot(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)
		
		current_mode_id = request.POST['current_mode_id']
		modes = json.loads(request.POST['modes']) 
		is_test = True if request.POST['test_run'] == "true" else False
		run_request = True if request.POST['run_request'] == "true" else False
		res = engine.main.run_mailbot(user, request.user.email, current_mode_id, modes, is_test, run_request)
		return HttpResponse(json.dumps(res), content_type="application/json")
	except Exception as e:
		logging.debug(e)
		return HttpResponse(request_error, content_type="application/json")

@login_required
def run_simulate_on_messages(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)
		
		# folder_name = request.POST['folder_name']
		folder_name = request.POST.getlist('folder_name[]')
		N = request.POST['N']
		code = request.POST['user_code']
		
		res = engine.main.run_simulate_on_messages(user, request.user.email, folder_name, N, code)
		return HttpResponse(json.dumps(res), content_type="application/json")
	except Exception as e:
		logger.exception("Error simulating login %s %s " % (e, traceback.format_exc()))
		return HttpResponse(request_error, content_type="application/json")
		
@login_required
def save_shortcut(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)
		
		shortcuts = request.POST['shortcuts']
		
		res = engine.main.save_shortcut(user, request.user.email, shortcuts)
		return HttpResponse(json.dumps(res), content_type="application/json")
	except Exception as e:
		logger.debug(e)
		return HttpResponse(request_error, content_type="application/json")

@login_required
def undo(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)
		
		logschema_id = request.POST['logschema-id']
		res = engine.main.undo(user, request.user.email, logschema_id)
		return HttpResponse(json.dumps(res), content_type="application/json")
	except Exception as e:
		logging.debug(e)
		return HttpResponse(request_error, content_type="application/json")

@login_required
def delete_mailbot_mode(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)
		
		mode_id = request.POST['id']

		res = engine.main.delete_mailbot_mode(user, request.user.email, mode_id)
		return HttpResponse(json.dumps(res), content_type="application/json")
	except Exception as e:
		logger.exception(e)
		return HttpResponse(request_error, content_type="application/json")

@login_required
def handle_imap_idle(request):
	try:
		user = get_object_or_404(UserProfile, email=request.user.email)

		res = engine.main.get_deltas_cursors(user, request.user.email)
		logger.info(res)
		return HttpResponse(json.dumps(res), content_type="application/json")
	except Exception as e:
		logger.exception(e)
		return HttpResponse(request_error, content_type="application/json")

@login_required
def murmur_acct(request, acct_func=None, template_name=None):
	user = get_object_or_404(UserProfile, email=request.user.email)
	groups = Group.objects.filter(membergroup__member=user).values("name")
	groups_links = get_groups_links_from_roles(user, groups)

	context = {'groups': groups, 'groups_links' : groups_links, 'user': request.user, 'website' : WEBSITE, 'group_page' : True} 
	return acct_func(request, template_name=template_name, extra_context=context)

