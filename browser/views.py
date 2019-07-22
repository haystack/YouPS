import base64, json, logging,traceback

from annoying.decorators import render_to
from boto.s3.connection import S3Connection
from html2text import html2text
from lamson.mail import MailResponse


from django.conf import global_settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.context_processors import csrf
from django.core.urlresolvers import reverse
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models.aggregates import Count
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render_to_response, render
from django.template.context import RequestContext
from django.utils.encoding import *
from django.utils.http import urlencode

from browser.util import load_groups, paginator, get_groups_links_from_roles, get_role_from_group_name
import engine.main
from engine.constants import msg_code
from http_handler.settings import WEBSITE, AWS_STORAGE_BUCKET_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
from registration.forms import RegistrationForm
from schema.youps import ImapAccount, MailbotMode, FolderSchema, EmailRule
from smtp_handler.utils import *
import logging

from browser.youps_component import load_new_editor

logger = logging.getLogger('youps')  # type: logging.Logger

request_error = json.dumps({'code': msg_code['REQUEST_ERROR'], 'status': False})

if WEBSITE == 'murmur':
    group_or_squad = 'group'
elif WEBSITE == 'squadbox':
    group_or_squad = 'squad'

# TODO(lukemurray): not sure that we want this here since its not a request
def _is_imap_authenticated(imap):
    """Return true if we can read the users email. False otherwise.

    THIS IS NOT CHECKING FOR LOGIN.

    Args:
        imap: django model of a users imap account.
    """
    return (imap[0].is_oauth and imap[0].access_token != "") or (not imap[0].is_oauth and imap[0].password != "")

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
    shortcuts_exist = False
    is_initialized = False
    folders = []
    email_rule_folder = []
    rules = []

    try:
        logger.info("login_imap_view() request info %s", request)
        logger.info("login_imap_view() user info %s", request.user)

        # redirect users who are not logged in to the login screen
        if not request.user.is_authenticated():
            base_url = reverse('auth_login')  # /login/
            # TODO(lukemurray): not sure that next parameter is doing anything
            query_string =  urlencode({'next': '/editor'})  # next=%2feditor
            url = '{}?{}'.format(base_url, query_string)  # /login/?next=/editor
            logger.info("login_imap_view(): redirect to %s", url)
            return redirect(url)  # do the redirect

        if request.user.id is not None:
            # redirect users without imap accounts and users with unauthenticated imap
            # accounts to the email authorization page
            try:
                imap = ImapAccount.objects.get(email=request.user.email)
            except ImapAccount.DoesNotExist:
                imap = None
            if imap is None or not _is_imap_authenticated(imap):
                # redirect users who are not authenticated to the authentication screen
                return redirect('email_auth')

            imap_authenticated = True
            is_test = imap[0].is_test
            is_running = imap[0].is_running
            is_initialized = imap[0].is_initialized

            current_mode = imap[0].current_mode

            modes = MailbotMode.objects.filter(imap_account=imap[0])
            logger.info(modes.values())
            mode_exist = modes.exists()

            shortcuts = imap[0].shortcuts
            if len(shortcuts) > 0:
                shortcuts_exist = True

            if is_initialized:
                # send their folder list
                folders = FolderSchema.objects.filter(imap_account=imap[0]).values('name')

                folders = [f['name'].encode('utf8', 'replace') for f in folders]

                # mode_folder = MailbotMode_Folder.objects.filter(imap_account=imap[0])
                # mode_folder = [[str(mf.folder.name), str(mf.mode.uid)] for mf in mode_folder]

                rules = EmailRule.objects.filter(mode__imap_account=imap[0])
                for rule in rules:
                    for f in rule.folders.all():
                        email_rule_folder.append([f.name.encode('utf8', 'replace'), int(rule.id)])

        return {'user': request.user, 'is_test': is_test,
                'is_running': is_running, 'is_initialized': is_initialized,
                'folders': folders, 'rule_folder': email_rule_folder,
                'mode_exist': mode_exist, 'modes': modes, 'rules': rules,
                'current_mode': current_mode,
                'imap_authenticated': imap_authenticated, 'website': WEBSITE,
                'shortcuts_exist': shortcuts_exist, 'shortcuts': shortcuts}
    except Exception as e:
        logger.exception(e)
        return {'user': request.user, 'website': WEBSITE}

@render_to(WEBSITE+"/docs.html")
def docs_view(request):
    return {'website': WEBSITE}

@render_to(WEBSITE+"/about.html")
def about_view(request):
    return {'website': WEBSITE}

@render_to(WEBSITE+"/calendar.html")
def calendar_view(request):
    return {'website': WEBSITE}

@login_required
@render_to(WEBSITE+"/authorize_email.html")
def authorize_email(request):
    """Display a form for the user to grant access to their email.

    When given a POST request this method responds to the authorize email
    form. When given a GET request this method renders the authorize email
    form.
    """
    assert request.user.is_authenticated(), "login_required not working as expected"

    errors = []

    # if we get a post request we try to process the form
    if request.method == 'POST':

        if not request.user.is_authenticated():
            errors.append('You need to login first')
        else:
            try:
                user = get_object_or_404(UserProfile, email=request.user.email)
                auth_method = request.POST["use_oauth"]
                if auth_method == "oauth":
                    oauth_code = request.POST["oauth-code"]
                    engine.main.login_imap(user.email, oauth_code, 'imap.gmail.com', is_oauth=True)
                    return redirect("editor")
                elif auth_method == "password":
                    password = request.POST["password"]
                    host = request.POST["imap-host"]
                    engine.main.login_imap(user.email, password, host, is_oauth=False)
                    return redirect("editor")
                else:
                    raise RuntimeError('Neither oauth or password was selected')
            except Exception:
                errors.append('Failed to login please try again or contact the admins.')
    # if we get a get request see if the user is already authenticated
    # and redirect them to the editor if they are
    elif request.method == 'GET':
        if request.user.id is not None:
            try:
                imap = ImapAccount.objects.get(email=request.user.email)
                if _is_imap_authenticated(imap):
                    return redirect('editor')
            except ImapAccount.DoesNotExist:
                pass

    # fallback to rendering the auth form page
    return {'user': request.user, 'website': WEBSITE, 'errors': errors}


@login_required
def login_imap(request):
    try:
        user = get_object_or_404(UserProfile, email=request.user.email)

        # email = request.POST['email']
        host = request.POST['host']
        is_oauth = True if request.POST['is_oauth'] == "true" else False
        password = request.POST['password']

        res = engine.main.login_imap(user.email, password, host, is_oauth)
        return HttpResponse(json.dumps(res), content_type="application/json")
    except Exception, e:
        print e
        logging.debug(e)
        return HttpResponse(request_error, content_type="application/json")

@login_required
def fetch_execution_log(request):
    try:
        user = get_object_or_404(UserProfile, email=request.user.email)

        res = engine.main.fetch_execution_log(user, request.user.email)
        return HttpResponse(json.dumps(res), content_type="application/json")
    except Exception, e:
        print e
        logging.debug(e)
        return HttpResponse(request_error, content_type="application/json")

@login_required
def folder_recent_messages(request):
    try:
        user = get_object_or_404(UserProfile, email=request.user.email)

        folder_name = request.POST['folder_name']
        N = request.POST['N']

        # res = engine.main.folder_recent_messages(user, user.email, folder_name, N)
        return HttpResponse(None, content_type="application/json")
    except Exception, e:
        print e
        logging.debug(e)
        return HttpResponse(request_error, content_type="application/json")

@login_required
def remove_rule(request):
    try:
        user = get_object_or_404(UserProfile, email=request.user.email)

        rule_id = request.POST['rule-id']
        res = engine.main.remove_rule(user, request.user.email, rule_id)
        return HttpResponse(json.dumps(res), content_type="application/json")
    except Exception, e:
        print e
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
    except Exception, e:
        print e
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
    except Exception, e:
        logger.exception("Error simulating login %s %s " % (e, traceback.format_exc()))
        return HttpResponse(request_error, content_type="application/json")

@login_required
def save_shortcut(request):
    try:
        user = get_object_or_404(UserProfile, email=request.user.email)

        shortcuts = request.POST['shortcuts']

        res = engine.main.save_shortcut(user, request.user.email, shortcuts)
        return HttpResponse(json.dumps(res), content_type="application/json")
    except Exception, e:
        print e
        logging.debug(e)
        return HttpResponse(request_error, content_type="application/json")

@login_required
def create_mailbot_mode(request):
    try:
        user = get_object_or_404(UserProfile, email=request.user.email)

        res = engine.main.create_mailbot_mode(user, request.user.email)
        return HttpResponse(json.dumps(res), content_type="application/json")
    except Exception, e:
        logger.exception(e)
        return HttpResponse(request_error, content_type="application/json")

@login_required
def delete_mailbot_mode(request):
    try:
        user = get_object_or_404(UserProfile, email=request.user.email)

        mode_id = request.POST['id']

        res = engine.main.delete_mailbot_mode(user, request.user.email, mode_id)
        return HttpResponse(json.dumps(res), content_type="application/json")
    except Exception, e:
        logger.exception(e)
        return HttpResponse(request_error, content_type="application/json")

@login_required
def murmur_acct(request, acct_func=None, template_name=None):
    user = get_object_or_404(UserProfile, email=request.user.email)
    groups = Group.objects.filter(membergroup__member=user).values("name")
    groups_links = get_groups_links_from_roles(user, groups)

    context = {'groups': groups, 'groups_links' : groups_links, 'user': request.user, 'website' : WEBSITE, 'group_page' : True}
    return acct_func(request, template_name=template_name, extra_context=context)

