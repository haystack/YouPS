import logging
import datetime 
from django.contrib.sites.models import Site
from django.utils import timezone
from browser.imap import authenticate
from engine.models.mailbox import MailBox
from http_handler.settings import BASE_URL, PROTOCOL
from schema.youps import ImapAccount, EmailRule
from smtp_handler.utils import send_email
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

    lockFile = 'register_inbox.lock'
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

                logger.info("Mailbox sync done: %s" % (imapAccount.email))

                # after sync, logout to prevent multi-connection issue
                imap.logout()

                imapAccount.is_initialized = True
                imapAccount.save()

                site = Site.objects.get_current()
                send_email("Your YoUPS account is ready!",
                           "no-reply@" + BASE_URL,
                           imapAccount.email,
                           "Start writing your automation rule here! %s://%s" % (PROTOCOL, site.domain))

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

    lockFile = 'loop_sync_user_inbox.lock'
    with open(lockFile, 'w') as f:
        have_lock = get_lock(f)
        if not have_lock:
            logger.info('Lock already taken %s' % lockFile)
            return

        imapAccounts = ImapAccount.objects.filter(
            is_initialized=True)  # type: t.List[ImapAccount]
        for imapAccount in imapAccounts:
            # refresh from database
            imapAccount = ImapAccount.objects.get(id=imapAccount.id)
            if not imapAccount.is_initialized:
                continue

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
                    # sync the mailbox with imap
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
                except Exception():
                    logger.exception("Mailbox run user code failed")

                if res is not None and res.get('imap_log', ''):
                    log_decoded = json.loads(imapAccount.execution_log) if len(imapAccount.execution_log) else {}
                    log_decoded.update( res['imap_log'] )

                    imapAccount.execution_log = json.dumps(log_decoded)
                    # imapAccount.execution_log = "%s\n%s" % (
                    #     res['imap_log'], imapAccount.execution_log)
                    imapAccount.save()

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