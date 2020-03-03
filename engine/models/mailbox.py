from __future__ import unicode_literals, print_function, division
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing
from event import Event
import logging
import datetime
import smtplib
import traceback
import typing as t  # noqa: F401 ignore unused we use it for typing
from schema.youps import ImapAccount, BaseMessage, FolderSchema, MailbotMode, EmailRule  # noqa: F401 ignore unused we use it for typing
from folder import Folder
from smtp_handler.utils import format_email_address, send_email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from engine.models.event_data import NewMessageDataDue

from browser.imap import decrypt_plain_password
from engine.google_auth import GoogleOauth2
from nylas import APIClient
from http_handler.settings import CLIENT_ID, NYLAS_ID, NYLAS_SECRET

logger = logging.getLogger('youps')  # type: logging.Logger


class MailBox(object):
    def __init__(self, imap_account, imap_client, is_simulate=False):
        # type: (ImapAccount, IMAPClient) -> MailBox
        """Create a new instance of the client's mailbox using a connection
        to an IMAPClient.
        """
        from engine.models.event_data import AbstractEventData

        self._imap_client = imap_client  # type: IMAPClient

        self._imap_account = imap_account  # type: ImapAccount

        # Events
        self.new_message_handler = Event()  # type: Event
        self.added_flag_handler = Event()  # type: Event
        self.removed_flag_handler = Event()  # type: Event
        self.deadline_handler = Event()  # type: Event
        self.moved_message_handler = Event()  # type: Event

        self.event_data_list = []  # type: t.List[AbstractEventData]
        self.new_message_ids = set()  # type: t.Set[str]
        self.is_simulate = is_simulate  # type: bool
        

    def __str__(self):
        # type: () -> t.AnyStr
        """Produce a string representation of the mailbox

        Returns:
            str: string representation of the mailbox
        """

        return "mailbox: %s" % (self._imap_account.email)

    def _log_message_ids(self):
        from engine.models.message import Message
        from pprint import pformat
        import cPickle as pickle

        import sqlite3
        conn = sqlite3.connect('/home/ubuntu/production/mailx/logs/message_data.db')
        c = conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS "data" (
            "id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
            "email"	INTEGER NOT NULL,
            "folder"	TEXT NOT NULL,
            "uid"	INTEGER NOT NULL,
            "data"	TEXT NOT NULL
        );
        ''')
        conn.commit()
        c.execute('''
        CREATE TABLE IF NOT EXISTS "synced" (
            "id"	INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE,
            "email"	INTEGER NOT NULL
        );
        ''')
        conn.commit()

        emails = [email[0] for email in c.execute("SELECT email FROM synced")]
        if self._imap_account.email in emails:
            logger.info("_log_message_ids(): already logged %s", self._imap_account.email)
            return

        logger.info("_log_message_ids(): logging message data for  %s", self._imap_account.email)
        for folder in self._list_selectable_folders():
            response = self._imap_client.select_folder(folder.name)
            min_mail_id = folder._get_min_mail_id()
            uid_criteria = '%d:*' % (min_mail_id + 1)
            is_gmail = self._imap_account.is_gmail
            descriptors = Message._get_descriptors(is_gmail)
            fetch_data = self._imap_client.fetch(uid_criteria, descriptors)
            values = [(self._imap_account.email, folder.name, uid, pickle.dumps(fetch_data[uid])) for uid in fetch_data]
            c.executemany("INSERT INTO data (email, folder, uid, data)  VALUES (?, ?, ?, ?)", values)
            conn.commit()


        c.execute("INSERT into synced (email) VALUES (?)", (self._imap_account.email,))
        conn.commit()

        # We can also close the connection if we are done with it.
        # Just be sure any changes have been committed or they will be lost.
        conn.close()

    

    def _add_contact(self, name, email_address):
        if self._imap_account.nylas_access_token:
            nylas = APIClient(
                NYLAS_ID,
                NYLAS_SECRET,
                self._imap_account.nylas_access_token
            )

            c = nylas.contacts.where(email=email_address)
            if c:
                for contact in c:
                    c.given_name = name
                    c.save()

            else:
                contact = nylas.contacts.create()
                
                contact.given_name = name
                contact.emails['personal'] = [email_address]
                
                contact.save()

    def _delete_contact(self, email_address):
        if self._imap_account.nylas_access_token:
            nylas = APIClient(
                NYLAS_ID,
                NYLAS_SECRET,
                self._imap_account.nylas_access_token
            )

            contacts = nylas.contacts.where(email=email_address)
            for c in contacts:
                nylas.contacts.delete(c.id)

        
    def _sync(self):
        # type: () -> bool 
        """Synchronize the mailbox with the imap server.
        """

        # should do a couple things based on
        # https://stackoverflow.com/questions/9956324/imap-synchronization
        # and https://tools.ietf.org/html/rfc4549
        # TODO for future work per folder might be highest common denominator for parallelizing
        for folder in self._list_selectable_folders():
            # response contains folder level information such as
            # uid validity, uid next, and highest mod seq
            if self._imap_account.email in ["lauralyn@mit.edu", "pmarsena@mit.edu"]:
                if folder.name in ["Calendar", "Contacts"]:
                    continue
                logger.debug("Laula; about to select_folder %s" % (folder.name))

            
            try:
                # if self._imap_account.email == "shachieg@csail.mit.edu":
                #     logger.info(folder.name)

                response = self._imap_client.select_folder(folder.name)
            except Exception as e:
                logger.critical("%s at %s" % (str(e), folder.name))
                continue

            # our algorithm doesn't work without these
            if not ('UIDNEXT' in response and 'UIDVALIDITY' in response):
                logger.critical("%s Missing UID Information" % folder)
                continue

            uid_next, uid_validity = response['UIDNEXT'], response['UIDVALIDITY']
            highest_mod_seq = response.get('HIGHESTMODSEQ')
            if highest_mod_seq:
                logger.debug("highest_mod_seq %d" % highest_mod_seq)

            # check if we are doing a total refresh or just a normal refresh
            # total refresh occurs the first time we see a folder and
            # when the UIDVALIDITY changes
            if folder._should_completely_refresh(uid_validity):
                folder._completely_refresh_cache()
            else:
                folder._refresh_cache(uid_next, highest_mod_seq, self.event_data_list, self.new_message_ids)

            # update the folder's uid next and uid validity
            folder._uid_next = uid_next
            folder._uid_validity = uid_validity

        return True

    def _manage_task(self, email_rule, now):
        # type: (EmailRule, datetime.datetime) -> None 
        """Add task to event_data_list, if there is message arrived in time span [last checked time, span_end]
        """ 
        time_span = int(email_rule.type.split('new-message-')[1])
        
        for folder_schema in email_rule.folders.all():
            folder = Folder(folder_schema, self._imap_client)
            time_start = email_rule.executed_at - datetime.timedelta(seconds=time_span)
            time_end = now - datetime.timedelta(seconds=time_span)

            logger.debug("time range %s %s" % (time_start, time_end))
            folder._search_scheduled_message(self.event_data_list, time_start, time_end)

    def _get_due_messages(self, email_rule, now):
        # type: (EmailRule, datetime.datetime) -> None 
        """Add task to event_data_list, if there is message arrived in time span [last checked time, span_end]
        """ 
        time_span = 0
        time_start = email_rule.executed_at - datetime.timedelta(seconds=time_span)
        time_end = now - datetime.timedelta(seconds=time_span)

        message_schemas = BaseMessage.objects.filter(imap_account=self._imap_account, deadline__range=[time_start, time_end])
        from engine.models.message import Message

        # Check if there are messages arrived+time_span between (email_rule.executed_at, now), then add them to the queue
        for bm_schema in message_schemas:
            
            logger.info("add deadline queue %s %s %s" %
                        (time_start, bm_schema.deadline, time_end))
            
            # TODO Maybe we should find a better way to pick a message schema
            for message_schema in bm_schema.messages.all():
                msg = Message(message_schema, self._imap_client)
                
                if "\\Deleted" in msg.flags:
                    continue
                self.event_data_list.append( NewMessageDataDue(msg) )

    def _supports_cond_store(self):
        # type: () -> bool
        """True if the imap server support RFC4551 which has
        things like HIGHESTMODSEQ

        Returns:
            bool: whether or not the imap server supports cond store
        """
        return self._imap_client.has_capability('CONDSTORE')

    def _run_user_code(self):
        # type: () -> t.Optional[t.Dict[t.AnyStr, t.Any]]
        from browser.sandbox import interpret
        res = interpret(self, self._imap_account.current_mode)
        # if res['imap_log']:
        #     logger.info('user output: %s' % res['imap_log'])
        return res


    def _find_or_create_folder(self, name):
        # type: (t.AnyStr) -> Folder
        """Return a reference to the folder with the given name.

        Returns:
            Folder: Folder associated with the passed in name
        """

        folder_schema = None  # type: FolderSchema
        try:
            folder_schema = FolderSchema.objects.get(
                imap_account=self._imap_account, name=name)
        except FolderSchema.DoesNotExist:
            folder_schema = FolderSchema(
                imap_account=self._imap_account, name=name)
            folder_schema.save()
            logger.debug("created folder %s in database" % name)

        return Folder(folder_schema, self._imap_client)

    def _list_selectable_folders(self, root=''):
        # type: (str) -> t.Generator[Folder]
        """Generate all the folders in the Mailbox
        """

        # we want to avoid listing all the folders
        # https://www.imapwiki.org/ClientImplementation/MailboxList
        # we basically only want to list folders when we have to
        for (flags, delimiter, name) in self._imap_client.list_folders('', root + '%'):
            # TODO check if the user is using the gmail
            # If it is gmail, then skip All Mail folder
            if name == "[Gmail]/All Mail":
                continue
            folder = self._find_or_create_folder(name)  # type: Folder

            # TODO maybe fire if the flags have changed
            folder.flags = flags

            # assume there are children unless specifically told otherwise
            recurse_children = True

            # we look at all the flags here
            if '\\HasNoChildren' in flags:
                recurse_children = False

            # do depth first search and return child folders if they exist
            if recurse_children:
                for child_folder in self._list_selectable_folders(name + delimiter):
                    yield child_folder

            # do not yield folders which are not selectable
            if '\\Noselect' in flags:
                folder._is_selectable = False
                continue
            else:
                # TODO we should verify this in the return from select_folder
                folder._is_selectable = True

            yield folder

    def _create_message_wrapper(self, subject="", to="", cc="", bcc="", content="", content_html=""):
        new_message = MIMEMultipart('alternative')
        new_message["Subject"] = subject
        
        to = format_email_address(to)
        cc = format_email_address(cc)
        bcc = format_email_address(bcc)
         
        new_message["To"] = to
        new_message["Cc"] = cc
        new_message["Bcc"] = bcc

        header_charset = 'ISO-8859-1'

        # We must choose the body charset manually
        for body_charset in 'US-ASCII', 'ISO-8859-1', 'UTF-8':
            try:
                content.encode(body_charset)
            except UnicodeError:
                pass
            else:
                break
        
        # We must choose the body charset manually
        for body_charset2 in 'US-ASCII', 'ISO-8859-1', 'UTF-8':
            try:
                content_html.encode(body_charset2)
            except UnicodeError:
                pass
            else:
                break

        part1 = MIMEText(content.encode(body_charset), 'plain', body_charset)
        new_message.attach(part1)
        
        if content_html:
            part2 = MIMEText(content_html.encode(body_charset2), 'html', body_charset2)
            new_message.attach(part2)
    
        return new_message

    def create_draft(self, subject="", to="", cc="", bcc="", content="", draft_folder=None):
        """Create a draft message and save it to user's draft folder

            Args:
                subject (string): the subject line of the draft message
                to (a single instance|list of string|Contact): addresses that go in to field
                cc (a single instance|list of string|Contact): addresses that go in cc field
                bcc (a single instance|list of string|Contact): addresses that go in bcc field
                content (string): content of the draft message 
                draft_folder (string): a name of draft folder 
        """
        
        new_message = self._create_message_wrapper(subject, to, cc, bcc, content)
            
        if not self.is_simulate:
            try:
                if draft_folder is not None:
                    self._imap_client.append(draft_folder, str(new_message))
                elif self._imap_account.is_gmail:
                    self._imap_client.append('[Gmail]/Drafts', str(new_message))
                else:
                    import imapclient
                    drafts = self._imap_client.find_special_folder(imapclient.DRAFTS)
                    if drafts is not None:
                        self._imap_client.append(drafts, str(new_message))
            except IMAPClient.Error, e:
                logger.critical('create_draft() failed')
                return 

            logger.debug("create_draft(): Your draft %s has been created" % subject)

    def create_folder(self, folder_name):
        if not self.is_simulate: 
            if "csail" in self._imap_account.host:
                folder_name = "INBOX." + folder_name
            self._imap_client.create_folder( folder_name )

        print("create_folder(): A new folder %s has been created" % folder_name)

    def get_email_mode(self):
        if self._imap_account.current_mode:
            return self._imap_account.current_mode.uid
        else:
            return None

    def set_email_mode(self, uid):
        if not self.is_simulate: 
            self._imap_account.current_mode = MailbotMode.objects.get(imap_account=self._imap_account, uid=uid)
            self._imap_account.save()

        print ("Change a current email mode to %s (%d)" % (self._imap_account.current_mode.name, self._imap_account.current_mode.uid))

    def rename_folder(self, old_name, new_name):
        if not self.is_simulate: 
            self._imap_client.rename_folder( old_name, new_name )

        logger.debug("rename_folder(): Rename a folder %s to %s" % (old_name, new_name))

    def send(self, subject="", to="", cc="", bcc="", body="", body_html="", smtp=""):  # TODO add "cc", "bcc"
        # if len(to) == 0:
        #     raise Exception('send(): recipient email address is not provided')
        msg_wrapper = self._create_message_wrapper(subject, to, cc, bcc, body, body_html)

        if not self.is_simulate:
            # send_email(subject, self._imap_account.email, to, body)
            self._send_message( msg_wrapper )

        logger.debug("send(): sent a message to  %s" % str(to))

    def _send_message(self, new_message_wrapper):
        # type: (MIMEMultipart) -> None
        """Send out a message with the user's credential  
        """

        try:
            # SMTP authenticate
            if self._imap_account.is_oauth:
                oauth = GoogleOauth2()
                response = oauth.RefreshToken(
                    self._imap_account.refresh_token)

                auth_string = oauth.generate_oauth2_string(
                    self._imap_account.email, response['access_token'], as_base64=True)
                s = smtplib.SMTP('smtp.gmail.com', 587)
                s.ehlo(CLIENT_ID)
                s.starttls()
                s.docmd('AUTH', 'XOAUTH2 ' + auth_string)

            else:
                try:
                    smtp_host = ""
                    login_id = self._imap_account.email
                    if "imap.exchange.mit.edu" == self._imap_account.host:
                        smtp_host = "outgoing.mit.edu"
                        login_id = login_id.split("@")[0]
                    else:
                        smtp_host = self._imap_account.host.replace("imap", "smtp")

                    s = smtplib.SMTP(smtp_host, 587)
                except Exception:
                    raise NameError
                s.ehlo()
                s.starttls()
                s.ehlo()

                s.login(login_id, decrypt_plain_password(
                    self._imap_account.password))

            receip_list = []
            for i in ["To", "Cc", "Bcc"]:
                if i in new_message_wrapper and new_message_wrapper[i]:
                    receip_list.append( new_message_wrapper[i] )


            # TODO check if it sent to cc-ers
            s.sendmail(self._imap_account.email,
                       ', '.join(receip_list), new_message_wrapper.as_string())
        except NameError:
            raise RuntimeError("Error occur during sending your message: it has been reported to admins")
        except Exception as e:
            logger.exception ("%s %s" % (e, traceback.format_exc()))
            raise RuntimeError('Failed to send a message: %s' % str(e))