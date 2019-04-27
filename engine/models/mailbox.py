from __future__ import unicode_literals, print_function, division
from __future__ import absolute_import
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing
from .event import Event
import logging
import datetime
import typing as t  # noqa: F401 ignore unused we use it for typing
from schema.youps import ImapAccount, FolderSchema, MailbotMode, EmailRule  # noqa: F401 ignore unused we use it for typing
from .folder import Folder
from engine.models.contact import Contact
from smtp_handler.utils import format_email_address, send_email
from email import message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger('youps')  # type: logging.Logger


class MailBox(object):
    def __init__(self, imap_account, imap_client):
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

        self.event_data_list = []  # type: t.List[AbstractEventData]
        self.is_simulate = False

    def __str__(self):
        # type: () -> t.AnyStr
        """Produce a string representation of the mailbox

        Returns:
            str: string representation of the mailbox
        """

        return "mailbox: %s" % (self._imap_account.email)

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
            response = self._imap_client.select_folder(folder.name)

            # our algorithm doesn't work without these
            if not ('UIDNEXT' in response and 'UIDVALIDITY' in response):
                logger.critical("%s Missing UID Information" % folder)
                continue

            uid_next, uid_validity = response['UIDNEXT'], response['UIDVALIDITY']
            highest_mod_seq = response.get('HIGHESTMODSEQ')

            # check if we are doing a total refresh or just a normal refresh
            # total refresh occurs the first time we see a folder and
            # when the UIDVALIDITY changes
            if folder._should_completely_refresh(uid_validity):
                folder._completely_refresh_cache()
            else:
                folder._refresh_cache(uid_next, highest_mod_seq, self.event_data_list)

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
        
        for folder_schema in email_rule.folders.all():
            folder = Folder(folder_schema, self._imap_client)
            time_start = email_rule.executed_at - datetime.timedelta(seconds=time_span)
            time_end = now - datetime.timedelta(seconds=time_span)

            logger.info("deadline range %s %s" % (time_start, time_end))
            folder._search_due_message(self.event_data_list, time_start, time_end)

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
        # type: (t.Text) -> t.Generator[Folder]
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
        
        new_message = MIMEMultipart('alternative')
        new_message["Subject"] = subject
        
        to = format_email_address(to)
        cc = format_email_address(cc)
        bcc = format_email_address(bcc)
         
        new_message["To"] = to
        new_message["Cc"] = cc
        new_message["Bcc"] = bcc
        
        # new_message.set_payload(content.encode('utf-8')) 
        if "text" in content and "html" in content:
            part1 = MIMEText(content["text"].encode('utf-8'), 'plain')
            part2 = MIMEText(content["html"].encode('utf-8'), 'html')
            new_message.attach(part1)
            new_message.attach(part2)
        else: 
            part1 = MIMEText(content.encode('utf-8'), 'plain')
            new_message.attach(part1)
            
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
            except IMAPClient.Error as e:
                logger.critical('create_draft() failed')
                return 

            logger.debug("create_draft(): Your draft %s has been created" % subject)

    def create_folder(self, folder_name):
        if not self.is_simulate: 
            self._imap_client.create_folder( folder_name )

        logger.debug("create_folder(): A new folder %s has been created" % folder_name)

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

    def send(self, subject="", to="", body="", smtp=""):  # TODO add "cc", "bcc"
        if len(to) == 0:
            raise Exception('send(): recipient email address is not provided')

        if not self.is_simulate:
            send_email(subject, self._imap_account.email, to, body)
        logger.debug("send(): sent a message to  %s" % str(to))