import base64, email, hashlib, json, logging, random, re, requests, sys, time

from bleach import clean
from cgi import escape
from datetime import timedelta
from django.utils.timezone import utc
from django.db.models import Q
from email.utils import parseaddr
from html2text import html2text
from salmon.mail import MailResponse
from pytz import utc

from browser.util import *
from constants import *
from engine.google_auth import *
from engine.constants import extract_hash_tags, ALLOWED_MESSAGE_STATUSES
from gmail_setup.api import update_gmail_filter, untrash_message
from gmail_setup.views import build_services
from http_handler.settings import BASE_URL, WEBSITE, AWS_STORAGE_BUCKET_NAME, PERSPECTIVE_KEY, IMAP_SECRET
from s3_storage import upload_attachments, download_attachments, download_message
from schema.models import *
from smtp_handler.utils import *

from engine.youps import login_imap, fetch_execution_log, apply_button_rule, create_mailbot_mode, fetch_watch_message, delete_mailbot_mode, remove_rule, run_mailbot, run_simulate_on_messages, save_shortcut, handle_imap_idle

def format_date_time(d):
    return datetime.strftime(d, '%Y/%m/%d %H:%M:%S')

