import sys
import traceback

try:
    from StringIO import StringIO
except ImportError:
    import io
import contextlib
from smtp_handler.utils import send_email, get_body
from smtp_handler.Pile import Pile
from email import message, utils, message_from_string
from email.utils import parseaddr
from imapclient import IMAPClient
from http_handler.settings import BASE_URL, WEBSITE, IMAP_SECRET
from engine.google_auth import GoogleOauth2
from Crypto.Cipher import AES
from engine.constants import msg_code
from datetime import datetime, timedelta
from schema.models import MailbotMode
import calendar
import base64


def authenticate(imap_account):
    res = {'status': False, 'imap_error': False, 'imap_log': "", 'imap': None}
    email_addr = ""
    try:
        imap = IMAPClient(imap_account.host, use_uid=True)
        email_addr = imap_account.email
        if imap_account.is_oauth:
            # TODO if access_token is expired, then get a new token
            imap.oauth2_login(imap_account.email, imap_account.access_token)
        else:
            aes = AES.new(IMAP_SECRET, AES.MODE_CBC, 'This is an IV456')
            password = aes.decrypt(base64.b64decode(imap_account.password))

            index = 0
            last_string = password[-1]
            for c in reversed(password):
                if last_string != c:
                    password = password[:(-1) * index]
                    break
                index = index + 1

            imap.login(imap_account.email, password)

        res['imap'] = imap
        res['status'] = True
    except IMAPClient.Error, e:
        try:
            print "try to renew token"
            if imap_account.is_oauth:
                oauth = GoogleOauth2()
                response = oauth.RefreshToken(imap_account.refresh_token)
                imap.oauth2_login(imap_account.email, response['access_token'])

                imap_account.access_token = response['access_token']
                imap_account.save()

                res['imap'] = imap
                res['status'] = True
            else:
                res['code'] = "Can't authenticate your email"
        except IMAPClient.Error, e:
            res['imap_error'] = e
            res['code'] = "Can't authenticate your email"

        except Exception, e:
            # TODO add exception
            res['imap_error'] = e
            print e
            res['code'] = msg_code['UNKNOWN_ERROR']

    if res['status'] is False:
        # email to the user that there is error at authenticating email
        if len(email_addr) > 0:
            subject = "[" + WEBSITE + "] Authentication error occurs"
            body = "Authentication error occurs! \n" + str(res['imap_error'])
            body += "\nPlease log in again at " + BASE_URL + "/editor"
            send_email(subject, WEBSITE + "@" + BASE_URL, email_addr, body)

        # TODO don't delete
        # Delete this ImapAccount information so that it requires user to reauthenticate
        imap_account.password = ""
        imap_account.access_token = ""

        # turn off the email engine
        imap_account.is_running = False
        imap_account.save()

    return res


def append(imap, subject, content):
    new_message = message.Message()
    new_message["From"] = "mailbot-log@" + BASE_URL
    new_message["Subject"] = subject
    new_message.set_payload(content)

    imap.append('INBOX', str(new_message), ('murmur-log'))


def fetch_latest_email_id(imap_account, imap_client):
    imap_client.select_folder("INBOX")
    uid_list = []

    # init
    if imap_account.newest_msg_id == -1:
        uid_list = imap_client.search("UID 199510:*")

    else:
        uid_list = imap_client.search("UID %d:*" % imap_account.newest_msg_id)

    # error handling for empty inbox
    if len(uid_list) == 0:
        uid_list = [1]

    return max(uid_list)


def format_log(msg, is_error=False, subject=""):
    s = "Subject: " + subject + " | "
    if is_error:
        return "[Error] " + s + msg
    else:
        return "[Info] " + s + msg


def wrapper(imap_account, imap, code, search_creteria, is_test=False, email_content=None):
    interpret(imap_account, imap, code, search_creteria, is_test, email_content)


# TODO what is email_content??? why are we not using get_content
def interpret(imap_account, imap, code, search_criteria, is_test=False, email_content=None):
    res = {'status': False, 'imap_error': False, 'imap_log': ""}
    messages = imap.search(search_criteria)
    is_valid = True

    if len(messages) == 0:
        is_valid = False

    pile = Pile(imap, search_criteria)
    if not pile.check_email():
        is_valid = False

    @contextlib.contextmanager
    def stdoutIO(stdout=None):
        old = sys.stdout
        if stdout is None:
            stdout = StringIO()
        sys.stdout = stdout
        yield stdout
        sys.stdout = old

    with stdoutIO() as s:
        def catch_exception(e):
            etype, evalue = sys.exc_info()[:2]
            estr = traceback.format_exception_only(etype, evalue)
            logstr = 'Error during executing your code \n'
            for each in estr:
                logstr += '{0}; '.format(each.strip('\n'))

            logstr = "%s \n %s" % (logstr, str(e))

            # Send this error msg to the user
            res['imap_log'] = logstr
            res['imap_error'] = True

        def send(subject="", to_addr="", body=""):
            """Send an email with a specified subject and body.
            Args:
                subject (str): The subject of the email
                to_addr (str): The person receiving the email
                body (str): The body of the email
            """
            if not to_addr:
                print format_log('send(): recipient email address is not provided', True, pile.get_subject())
                return 

            if not is_test:
                send_email(subject, imap_account.email, to_addr, body)

            print format_log("send(): send a message to  %s" % str(to_addr), False, get_subject())

        def add_gmail_labels(flags):
            """Add gmail labels to the emails in the pile.

            Args:
                flags (List[str]): List of flags to add to the email
            """
            if not is_test:
                pile.add_gmail_labels(flags)

            print format_log("add_gmail_labels(): add gmail labels to a message %s" % str(flags), False,
                             pile.get_subject())

        def add_labels(flags):
            """Alias for add_notes.

            Adds flags to the emails in the pile.

            Args:
                flags (List[str]): list of flags to add to the email(s)

            """
            add_notes(flags, "add_labels")

        def add_notes(flags, alias="add_notes"):
            """Adds flags to the emails in the pile.

            Args:
                flags (List[str]): list of flags to add to the email(s)
                alias (str): the alias used for logging
            """
            if type(flags) is not list:
                print format_log(alias + '(): args flags must be a list of strings', True, pile.get_subject())
                return 

            for f in flags:
                if not isinstance(f, str):
                    print format_log(alias + '(): args flags must be a list of strings', True, pile.get_subject())

            for f in range(len(flags)):
                flags[f] = flags[f].strip()

            if not is_test:
                pile.add_notes(flags)

            print alias + "(): successfully added " + str(flags)

        def copy(dst_folder):
            """Copy emails in the pile to the destination folder.

            Args:
                dst_folder (str): the folder the emails are going to be copied into. Is created if it does not exist.
            """
            if not dst_folder:
                print format_log('copy(): dst_folder must contain at least one letter or number', True,
                                 pile.get_subject())
                return 

            if not pile.folder_exists(dst_folder):
                print format_log('copy(): folder %s does not exist' % dst_folder, False, pile.get_subject())
                pile.create_folder(dst_folder)
                print format_log('copy(): created folder %s' % dst_folder, False, pile.get_subject())

            if not is_test:
                pile.copy(dst_folder)

            print format_log('copy(): copied email to folder %s' % dst_folder, False, pile.get_subject())

        def delete():
            if not is_test:
                pile.delete()
            print format_log(
                'delete(): deleting a message \n **WARNING: following actions can throw errors since you have deleted '
                'the message',
                False, pile.get_subject())

        def get_history(email, hours=24, cond=True):
            if len(email) == 0:
                raise Exception('get_history(): email address is not provided')

            if hours <= 0:
                raise Exception('get_history(): hours must be bigger than 0')

            # get uid of emails within interval
            now = datetime.now()
            start_time = now - timedelta(hours=hours)
            heuristic_id = imap_account.newest_msg_id - 100 if imap_account.newest_msg_id - 100 > 1 else 1
            name, sender_addr = parseaddr(get_sender().lower())
            today_email_ids = imap.search('FROM %s SINCE "%d-%s-%d"' % (
                sender_addr, start_time.day, calendar.month_abbr[start_time.month], start_time.year))

            # today_email = Pile(imap, 'UID %d:* SINCE "%d-%s-%d"' % (heuristic_id, start_time.day, calendar.month_abbr[start_time.month], start_time.year))
            # min_msgid = 99999
            # logging.debug("before get dates")

            received_cnt = 0
            sent_cnt = 0
            cond_cnt = 0
            for msgid in reversed(today_email_ids):
                p = Pile(imap, 'UID %d' % (msgid))

                t = p.get_date()
                date_tuple = utils.parsedate_tz(t)
                if date_tuple:
                    local_date = datetime.fromtimestamp(
                        utils.mktime_tz(date_tuple))

                    if start_time > local_date:
                        break

                    rs = p.get_recipients()
                    ss = p.get_senders()

                    with_email = False

                    # check if how many msg sent to this email
                    for j in range(len(rs)):
                        if email in rs[j] and imap_account.email in ss[0]:
                            sent_cnt = sent_cnt + 1
                            with_email = True
                            break

                    for j in range(len(ss)):
                        if email in ss[j]:
                            received_cnt = received_cnt + 1
                            with_email = True
                            break

                    if with_email:
                        if cond is True:
                            cond_cnt = cond_cnt + 1
                        else:
                            if cond(p):
                                cond_cnt = cond_cnt + 1

            # for msg in today_email.get_dates():
            #     msgid, t = msg
            #     date_tuple = utils.parsedate_tz(t)
            #     if date_tuple:
            #         local_date = datetime.fromtimestamp(
            #             utils.mktime_tz(date_tuple))

            #         if start_time < local_date:
            #             emails.append( msgid )

            # for i in range(len(emails)):
            #     p = Pile(imap, "UID %d" % (emails[i]))

            #     rs = p.get_recipients()
            #     ss = p.get_senders()

            #     with_email = False

            #     # check if how many msg sent to this email
            #     for j in range(len(rs)):
            #         if email in rs[j] and imap_account.email in ss[0]:
            #             sent_cnt = sent_cnt + 1
            #             with_email = True
            #             break

            #     for j in range(len(ss)):
            #         if email in ss[j]:
            #             received_cnt = received_cnt + 1
            #             with_email = True
            #             break

            #     if with_email:
            #         if cond == True:
            #             cond_cnt = cond_cnt + 1
            #         else:
            #             if cond(p):
            #                 cond_cnt = cond_cnt + 1

            r = {'received_emails': received_cnt, 'cond': cond_cnt}

            return r

        def get_sender():
            return pile.get_sender()

        def get_content():
            if email_content:
                return email_content
            else:
                return pile.get_content()

        def get_date():
            return pile.get_date()

        def get_attachment():
            print format_log('get_attachment() NOT IMPLEMENTED', False, pile.get_subject())
            return None

        def get_subject():
            return pile.get_subject()

        def get_recipients():
            return pile.get_recipient()

        def get_attachments():
            print format_log('get_attachments() NOT IMPLEMENTED', False, pile.get_subject())
            return None

        def get_labels():
            return pile.get_notes()

        def get_notes():
            return pile.get_notes()

        def get_gmail_labels():
            return pile.get_gmail_labels()

        def mark_read(is_seen=True):

            if not is_test:
                pile.mark_read(is_seen)
            print format_log("Mark Message a message %s" % ("read" if is_seen else "unread"), False, pile.get_subject())

        def move(dst_folder):
            if not dst_folder:
                print format_log('move(): dst_folder must contain at least one letter or number', True,
                                 pile.get_subject())
                return 

            if not pile.folder_exists(dst_folder):
                print format_log('move(): folder %s does not exist' % dst_folder, False, pile.get_subject())
                pile.create_folder(dst_folder)
                print format_log('move(): created folder %s' % dst_folder, False, pile.get_subject())

            if not is_test:
                pile.move(dst_folder)
            print format_log(
                "move(): moved message \n**Warning: your following action might throw errors as you move the message"
                , False, pile.get_subject())

        def remove_labels(flags):
            remove_notes(flags)

        def remove_notes(flags):
            if type(flags) is not list:
                print format_log('remove_labels(): args flags must be a list of strings', True, pile.get_subject())
                return 

            for f in flags:
                if not isinstance(f, str):
                    print format_log('remove_labels(): args flags must be a list of strings', True, pile.get_subject())
                return

            if not is_test:
                pile.remove_notes(flags)

            print format_log("Remove labels %s of a message" % flags, False, pile.get_subject())

        def remove_gmail_labels(flags):
            if type(flags) is not list:
                raise Exception('remove_gmail_labels(): args flags must be a list of strings')

            for f in flags:
                if not isinstance(f, str):
                    raise Exception('remove_gmail_labels(): args flags must be a list of strings')

            if not is_test:
                pile.remove_gmail_labels(flags)

            print format_log("Remove labels %s of a message" % flags, False, pile.get_subject())

        # return a list of email UIDs
        def search(criteria=u'ALL', charset=None, folder=None):
            # TODO how to deal with folders
            # TODO this could perform an intersection with the current pile. Otherwise this exposes emails which are not in the current scope
            # iterate through all the functions
            if folder is None:
                pass

            # iterate through a folder of list of folder
            else:
                # if it's a list iterate
                pass
                # else it's a string search a folder

            select_folder('INBOX')
            return imap.search(criteria, charset)

        def get_body_test(m):
            # raw=email.message_from_bytes(data[0][1])
            response = imap.fetch(m, ['BODY[TEXT]'])
            bodys = []
            for msgid, data in response.items():
                body = message_from_string(data[b'BODY[TEXT]'].decode('utf-8'))
                bodys.append(get_body(body))
                # print (body)

            # email_message = email.message_from_string(str(message))
            # msg_text = get_body(email_message)

            return bodys

        def create_folder(folder):
            if not folder:
                print format_log('create_folder(): folder must contain at least one character or number', True,
                                 pile.get_subject())
                return

            if pile.folder_exists(folder):
                print format_log('create_folder(): the folder %s already exists' % folder, True, pile.get_subject())
                return

            if not is_test:
                pile.create_folder(folder)

            print format_log('create_folder(): created folder %s' % folder, False, pile.get_subject())

        def delete_folder(folder):
            if not folder:
                print format_log('delete_folder(): folder must contain at least one character or number', True,
                                 pile.get_subject())
                return

            if not pile.folder_exists(folder):
                print format_log('delete_folder(): the folder %s does not exist' % folder, True, pile.get_subject())
                return

            if not is_test:
                pile.delete_folder(folder)

            print format_log('delete_folder(): deleted folder %s' % folder, False, pile.get_subject())

        def list_folders(directory=u'', pattern=u'*'):
            return pile.list_folders(directory, pattern)

        def select_folder(folder):
            # TODO this is an odd method since we don't use Pile in this case...
            if not imap.folder_exists(folder):
                format_log("Select folder; folder %s not exist" % folder, True, get_subject())
                return

            imap.select_folder(folder)
            print "Select a folder " + folder

        def rename_folder(old_name, new_name):
            if not old_name:
                print format_log('rename_folder(): old_name must contain at least one character or number', True,
                                 pile.get_subject())
                return

            if not new_name:
                print format_log('rename_folder(): new_name must contain at least one character or number', True,
                                 pile.get_subject())
                return

            if pile.folder_exists(new_name):
                print format_log('rename_folder(): the folder %s already exists' % new_name, True, pile.get_subject())
                return

            if not is_test:
                pile.rename_folder(old_name, new_name)

            print format_log("Rename a folder %s to %s" % (old_name, new_name), False, pile.get_subject())

        def get_mode():
            if imap_account.current_mode:
                return imap_account.current_mode.uid

            else:
                return None

        def set_mode(mode_index):
            try:
                mode_index = int(mode_index)
            except ValueError:
                raise Exception('set_mode(): args mode_index must be a index (integer)')

            mm = MailbotMode.objects.filter(uid=mode_index, imap_account=imap_account)
            if mm.exists():
                mm = mm[0]
                if not is_test:
                    imap_account.current_mode = mm
                    imap_account.save()

                print format_log("Set your mail mode to %s (%d)" % (mm.name, mode_index), False, get_subject())
                return True
            else:
                print format_log("A mode ID %d not exist!" % (mode_index), True, get_subject())
                return False

        try:
            if is_valid:
                exec code in globals(), locals()
                pile.add_notes(['YouPS'])
        except Exception as e:
            catch_exception(e)

        res['imap_log'] = s.getvalue() + res['imap_log']

        return res
