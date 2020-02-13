import logging
import datetime 
from django.contrib.sites.models import Site
from django.utils import timezone
from browser.imap import authenticate
from engine.models.mailbox import MailBox
from engine.utils import dump_execution_log
from http_handler.settings import BASE_URL, PROTOCOL
from schema.youps import ImapAccount, EmailRule, LogSchema
from smtp_handler.utils import send_email, _request_new_delta
import typing as t  # noqa: F401 ignore unused we use it for typing
import fcntl
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing
import imaplib
import json


logger = logging.getLogger('youps')  # type: logging.Logger



def get_lock(file):
    """Get a lock on the task

    Args:
        file (file): the lock file we are trying to get access to

    Returns:
        bool: True if we get the lock false otherwise
    """

    try:
        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        return False
    return True


def register_inbox():
    """Do the initial sync on an inbox.
    """


    lockFile = 'register_inbox2.lock'
    with open(lockFile, 'w') as f:
        have_lock = get_lock(f)
        if not have_lock:
            logger.info('Lock already taken %s' % lockFile)
            return

        for imapAccount in ImapAccount.objects.filter(is_initialized=False):
            try:
                logger.info('registering inbox: %s', imapAccount.email)

                while True:
                    try:
                        # authenticate with the user's imap server
                        auth_res = authenticate(imapAccount)
                        # if authentication failed we can't run anything
                        if not auth_res['status']:
                            # Stop doing loop
                            # TODO maybe we should email the user
                            logger.critical('register authentication failed for %s', imapAccount.email)
                            continue 

                        # get an imapclient which is authenticated
                        imap = auth_res['imap']  # type: IMAPClient


                        # create the mailbox
                        mailbox = MailBox(imapAccount, imap)
                        # TODO(lukemurray): remove this
                        mailbox._log_message_ids()
                        # sync the mailbox with imap
                        done = mailbox._sync()
                        if done:
                            break

                    # if we catch an EOF error we continue
                    except imaplib.IMAP4.abort:
                        logger.exception("Caught EOF error while syncing")
                        try:
                            imap.logout()
                        except Exception:
                            logger.exception("Failure while logging out due to EOF bug")
                        continue
                    # if we catch any other type of exception we abort to avoid infinite loop
                    except Exception:
                        logger.critical("Failure while initially syncing")
                        logger.exception("Failure while initially syncing")
                        raise

                logger.info("After sync, set up an exercise folder for the new user")
                try:
                        
                    imap.create_folder("_YouPS exercise")

                    msg1 = mailbox._create_message_wrapper("Welcome to YouPS!", imapAccount.email, content="This is the test email from YouPS", content_html="This is the test email from YouPS")
                    msg1["From"] = "hello-youps@csail.mit.edu"
                    imap.append("_YouPS exercise", str(msg1))

                    msg1 = mailbox._create_message_wrapper("[Example email] Follow up", imapAccount.email + ", mycoworker@mail.com", cc="mycoworker2@mail.com", content="Hello! I just wanted to follow up regarding our last meeting! Let me know how you think!", content_html="Hello! I just wanted to follow up regarding our last meeting! Let me know how you think!")
                    msg1["From"] = "hello-youps@csail.mit.edu"
                    imap.append("_YouPS exercise", str(msg1))

                    msg1 = mailbox._create_message_wrapper("[Example email] Blah blah", imapAccount.email + ", friend@mail.com", cc="friend1@mail.com", content="Howdy y'all!", content_html="Howdy y'all!")
                    msg1["From"] = "hello-youps@csail.mit.edu"
                    imap.append("_YouPS exercise", str(msg1))

                except Exception as e:
                    logger.exception(e)


                logger.info("Mailbox sync done: %s" % (imapAccount.email))

                # after sync, logout to prevent multi-connection issue
                imap.logout()

                imapAccount.is_initialized = True
                imapAccount.save()

                site = Site.objects.get_current()
                # TODO(lukemurray): bring this back
                # send_email("Your YouPS account is ready!",
                #            "no-reply@" + BASE_URL,
                #            imapAccount.email,
                #            "Start writing your automation rule here! %s://%s" % (PROTOCOL, site.domain))

                # Create a default mode & email rule to demo

                logger.info(
                    'Register done for %s', imapAccount.email)
            except ImapAccount.DoesNotExist:
                imapAccount.is_initialized = False
                imapAccount.save()
                logger.exception(
                    "syncing fails Remove periodic tasks. imap_account not exist %s" % (imapAccount.email))

            except Exception as e:
                logger.exception(
                    "User inbox syncing fails %s. Stop syncing %s" % (imapAccount.email, e))


def loop_sync_user_inbox():

    lockFile = 'loop_sync_user_inbox2.lock'
    with open(lockFile, 'w') as f:
        have_lock = get_lock(f)
        if not have_lock:
            logger.info('Lock already taken %s' % lockFile)
            return

        imapAccounts = ImapAccount.objects.filter(
            is_initialized=True)  # type: t.List[ImapAccount]
        for imapAccount in imapAccounts:
            # if imapAccount.email not in ["pmarsena@mit.edu", "youps.empty@gmail.com", "shachieg@csail.mit.edu"]:
            #     continue
            # refresh from database
            is_new_message = True
            imapAccount = ImapAccount.objects.get(id=imapAccount.id)
            if not imapAccount.is_initialized:
                continue

            if imapAccount.nylas_access_token:
                logger.info("Checking delta of %s " % imapAccount.email)
                # do sync whenever there is delta detected by Nylas
                cursor, is_new_message = _request_new_delta(imapAccount)

                if not cursor:
                    logger.info("No delta detected at %s -- move on to next inbox" % imapAccount.email)
                    continue 
                else:
                    # TODO update the cursor
                    imapAccount.nylas_delta_cursor = cursor
                    imapAccount.save()

            imapAccount_email = imapAccount.email

            try:
                logger.info('Start syncing %s ', imapAccount_email)

                # authenticate with the user's imap server
                auth_res = authenticate(imapAccount)
                # if authentication failed we can't run anything
                if not auth_res['status']:
                    # Stop doing loop
                    # TODO maybe we should email the user
                    logger.critical('authentication failed for %s' % imapAccount.email) 
                    continue

                # get an imapclient which is authenticated
                imap = auth_res['imap']

                # create the mailbox
                try:
                    mailbox = MailBox(imapAccount, imap)
                    # TODO(lukemurray): remove this

                    mailbox._log_message_ids()
                    # sync the mailbox with imap
                    if is_new_message:
                        mailbox._sync()
                        logger.info(mailbox.event_data_list)
                except Exception:
                    logger.exception("Mailbox sync failed")
                    # TODO maybe we should email the user
                    continue
                logger.debug("Mailbox sync done: %s" % (imapAccount_email))

                try:
                    # get scheduled tasks
                    email_rules = EmailRule.objects.filter(mode=imapAccount.current_mode, type__startswith='new-message-')  # type: t.List[EmailRule]
                    for email_rule in email_rules:
                        # Truncate millisec since mysql doesn't suport msec. 
                        now = timezone.now().replace(microsecond=0) + datetime.timedelta(seconds=1)

                        mailbox._manage_task(email_rule, now)

                        # mark timestamp to prevent running on certain message multiple times 
                        email_rule.executed_at = now + datetime.timedelta(seconds=1)
                        email_rule.save()
                        logger.info(mailbox.event_data_list)
                except Exception:
                    logger.exception("Mailbox managing task failed")
                    # TODO maybe we should email the user
                    continue
                logger.debug("Mailbox managing task done: %s" % (imapAccount_email))

                try:
                    # get deadline tasks
                    email_rules = EmailRule.objects.filter(mode=imapAccount.current_mode, type='deadline')  # type: t.List[EmailRule]
                    for email_rule in email_rules:
                        # Truncate millisec since mysql doesn't suport msec. 
                        now = timezone.now().replace(microsecond=0) + datetime.timedelta(seconds=1)
                        mailbox._get_due_messages(email_rule, now)

                        # mark timestamp to prevent running on certain message multiple times 
                        email_rule.executed_at = now + datetime.timedelta(seconds=1)
                        email_rule.save()
                        logger.info(mailbox.event_data_list)
                except Exception:
                    logger.exception("Mailbox managing task failed")
                    # TODO maybe we should email the user
                    continue
                try:
                    res = mailbox._run_user_code()
                except Exception:
                    logger.exception("Mailbox run user code failed")

                

                # after sync, logout to prevent multi-connection issue
                imap.logout()

                logger.info(
                    'Sync done for %s', imapAccount_email)
            except ImapAccount.DoesNotExist:
                imapAccount.is_initialized = False
                imapAccount.save()
                logger.exception(
                    "syncing fails Remove periodic tasks. imap_account not exist %s" % (imapAccount_email))

            except Exception as e:
                logger.exception(
                    "User inbox syncing fails %s. Stop syncing %s" % (imapAccount_email, e))

def button_sync():
    pass