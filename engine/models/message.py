from __future__ import division, print_function, unicode_literals, absolute_import

import email
import inspect
import logging
import re
import smtplib
import typing as t  # noqa: F401 ignore unused we use it for typing
import traceback
import json
from datetime import (datetime,  # noqa: F401 ignore unused we use it for typing
                      timedelta)
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from itertools import ifilter, islice, chain

from django.utils import timezone
from imapclient import \
    IMAPClient, exceptions  # noqa: F401 ignore unused we use it for typing
from pytz import timezone as tz

from engine.models.contact import Contact
from schema.youps import (EmailRule,  # noqa: F401 ignore unused we use it for typing
                          ImapAccount, BaseMessage, MessageSchema, TaskManager)
from smtp_handler.utils import format_email_address, get_attachments
from engine.utils import IsNotGmailException, convertToUserTZ, prettyPrintTimezone
from engine.models.helpers import message_helpers, CustomProperty, ActionLogging

from email_reply_parser import EmailReplyParser

from http_handler.settings import NYLAS_ID, NYLAS_SECRET
from nylas import APIClient

userLogger = logging.getLogger('youps.user')  # type: logging.Logger
logger = logging.getLogger('youps')  # type: logging.Logger


class Message(object):

    # the most basic descriptors we get for all messages
    _descriptors = ['FLAGS', 'INTERNALDATE']
    # the descriptors used to get header metadata about the messages
    _header_descriptors = 'BODY.PEEK[HEADER.FIELDS (DATE MESSAGE-ID SUBJECT FROM TO CC BCC REPLY-TO IN-REPLY-TO REFERENCES)]'
    # the key used to access the header descriptors after a fetch
    _header_fields_key = _header_descriptors.replace('.PEEK', '')
    # the descriptors used when we are updating flags
    _flags_descriptors = ['FLAGS']

    _user_level_func = ['on_message']

    def __init__(self, message_schema, imap_client, is_simulate=False):
        # type: (MessageSchema, IMAPClient, t.Optional[bool]) -> Message

        self._schema = message_schema  # type: MessageSchema

        # the connection to the server
        self._imap_client = imap_client  # type: IMAPClient

        # if True, then only local execute and don't transmit to the server.
        self._is_simulate = is_simulate  # type: bool

        # local copy of flags for simulating
        self._flags = self._schema.flags

        self._nylas_message = None

        self._imap_client.select_folder(self.folder.name)

        logger.debug('caller name: %s', inspect.stack()[1][3])

    @staticmethod
    def _get_flag_descriptors(is_gmail):
        # type: (bool) -> t.List[str]
        """get the descriptors for an imap fetch call when updating flags

        Returns:
            t.List[str]: descriptors for an imap fetch call 
        """
        descriptors = Message._flags_descriptors
        if is_gmail:
            return descriptors + ['X-GM-LABELS']
        return descriptors

    @staticmethod
    def _get_descriptors(is_gmail, use_key=False):
        # type: (bool, bool) -> t.List[str]
        """Get the descriptors for an imap fetch call when saving messages

        Returns:
            t.List[str]: descriptors for an imap fetch call
        """
        descriptors = Message._descriptors + [Message._header_descriptors]
        if use_key:
            descriptors = Message._descriptors + [Message._header_fields_key]
        return descriptors + ['X-GM-THRID', 'X-GM-LABELS'] if is_gmail else descriptors

    def __str__(self):
        # type: () -> t.AnyStr
        return "Message %s" % self.subject

    def __repr__(self):
        return repr('Message object "%s"' % str(self.subject))

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, Message):
            return self._schema == other._schema
        return False

    @CustomProperty
    def _imap_account(self):
        # type: () -> ImapAccount
        return self._schema.imap_account

    @CustomProperty
    def _uid(self):
        # type: () -> int
        return self._schema.uid

    @_uid.setter
    def _uid(self, value):
        # type: (int) -> None
        self._schema.uid = value
        self._schema.save()

    @CustomProperty
    def _msn(self):
        # type: () -> int
        return self._schema.msn

    @_msn.setter
    def _msn(self, value):
        # type: (int) -> None
        self._schema.msn = value
        self._schema.save()

    @CustomProperty
    def _message_id(self):
        # type: () -> int
        return self._schema.base_message.message_id

    @CustomProperty
    def flags(self):
        # type: () -> t.List[t.AnyStr]
        """Get the flags on the message

        Returns:
            List(str): List of flags on the message
        """
        return self._flags

    @CustomProperty
    def in_reply_to(self):
        # type: () -> t.List[t.AnyStr]
        """Get the message ids in the in_reply_to field 

        Returns:
            List(str): List of in_reply_to message ids on the message
        """
        return self._schema.base_message.in_reply_to

    @CustomProperty
    def references(self):
        # type: () -> t.List[t.AnyStr]
        """Get the message ids in the references field 

        Returns:
            List(str): List of references message ids on the message
        """
        return self._schema.base_message.references

    @CustomProperty
    def deadline(self):
        # type: () -> datetime.datetime
        """Get the user-defined deadline of the message

        Returns:
            datetime: The deadline
        """
        if not self._is_simulate:
            return self._schema.base_message.deadline
        else:
            if not hasattr(self, '_deadline'):
                self._deadline = None
            return self._deadline
        

    @deadline.setter
    def deadline(self, value):
        # type: (datetime.datetime) -> None
        value = convertToUserTZ(value)

        logger.info(self.subject)
        logger.info(self._is_simulate)
        
        if not self._is_simulate:
            logger.info("here")
            self._schema.base_message.deadline = value
            self._schema.base_message.save()
        else:
            self._deadline = value

    @CustomProperty
    def task(self):
        # type: () -> t.AnyStr
        """Get the user-defined task of the message

        Returns:
            str: The tasks
        """
        return self._schema.base_message.task

    @task.setter
    def task(self, value):
        # type: (t.AnyStr) -> None
        self._schema.base_message.task = value
        self._schema.base_message.save()

    @CustomProperty
    def subject(self):
        # type: () -> t.AnyStr
        """Get the Subject of the message

        Returns:
            str: The subject of the message
        """
        return self._schema.base_message.subject

    def _get_nylas_message(self):
        if self._nylas_message is None:
            logger.exception("here")
            nylas = APIClient(
                NYLAS_ID,
                NYLAS_SECRET,
                self._imap_account.nylas_access_token
            )
            
            from calendar import timegm
            import pytz
            datetime_obj = self.date.replace(tzinfo=pytz.utc).astimezone(self.date.tzinfo)
            timestamp = timegm(datetime_obj.timetuple())
            FIVE_MIN = 3 * 60

            for m in nylas.messages.where(limit=1, received_after=timestamp- FIVE_MIN, received_before=timestamp+FIVE_MIN, from_=self.from_.email, subject=self.subject.replace("\r\n", ""), view='expanded'):
                self._nylas_message = m
                return m

        return self._nylas_message

    @CustomProperty
    def c(self):
        if self._imap_account.nylas_access_token:
            nylas = APIClient(
                NYLAS_ID,
                NYLAS_SECRET,
                self._imap_account.nylas_access_token
            )

            a = []

            from calendar import timegm
            
            now_timestamp = timegm(datetime.now().timetuple())

            # get upcoming events 
            for e in nylas.events.where(limit=3, starts_after=now_timestamp):
                a.append(e.title)

        return a

    @CustomProperty
    def snippet(self):
        return self._get_nylas_message.snippet

    @CustomProperty
    def thread(self):
        # type: () -> t.List[Message]
        nylas = APIClient(
            NYLAS_ID,
            NYLAS_SECRET,
            self._imap_account.nylas_access_token
        )

        # p = re.compile( '([\[\(] *)?(RE?S?|FWD?) *([-:;)\]][ :;\])-]*|$)|\]+ *$', re.IGNORECASE)
        # t = nylas.threads.where(limit=1,subject=p.sub( '', self.subject).strip(),from_=self.from_.email)[0]
        message_ids = []

        # skip automatic email generated by Youps
        for m in nylas.messages.where(thread_id=self._get_nylas_message().thread_id,view='expanded'):
            if "@youps.csail.mit.edu" not in m.from_[0]["email"]:
                message_ids.append(m.headers['Message-Id'] )
        logger.info(message_ids)

        messages = []
        for m_id in message_ids:
            try:
                message =  MessageSchema.objects.get(base_message__message_id=m_id.replace("<", "").replace(">",""))
                messages.append(Message(message, self._imap_client))
            except Exception:
                pass
        return messages

    @CustomProperty
    def date(self):
        # type: () -> datetime
        """Get the date and time that the message was sent

        Returns:
            datetime: The date and time the message was sent
        """
        return self._schema.base_message.date

    @CustomProperty
    def is_read(self):
        # type: () -> bool
        """Get if the message has been read

        Returns:
            bool: True if the message has been read
        """
        return '\\Seen' in self.flags

    @CustomProperty
    def is_unread(self):
        # type: () -> bool
        """Get if the message is unread

        Returns:
            bool: True if the message is unread
        """
        return not self.is_read

    @CustomProperty
    def is_deleted(self):
        # type: () -> bool
        """Get if the message has been deleted

        Returns:
            bool: True if the message has been deleted
        """
        return '\\Deleted' in self.flags

    @CustomProperty
    def is_recent(self):
        # type: () -> bool
        """Get if the message is recent

        Returns:
            bool: True if the message is recent
        """
        # TODO we will automatically remove the RECENT flag unless we make our imapclient ReadOnly
        return '\\Recent' in self.flags

    @CustomProperty
    def is_replied(self):
        # type: () -> bool
        """Get if the message is replied

        Returns:
            bool: True if the message is replied
        """
        # check if messages attached to this thread and it is sent by someone else in the thread 

        return BaseMessage.objects.filter(imap_account=self._imap_account, _in_reply_to__contains=self._message_id).exclude(from_m__email=self._imap_account.email).exclude(from_m__email__icontains="@youps.csail.mit.edu").exists()

    @CustomProperty
    def to(self):
        # type: () -> t.List[Contact]
        """Get the Contacts the message is addressed to

        Returns:
            t.List[Contact]: The contacts in the to field of the message
        """

        return [Contact(contact_schema, self._imap_client) for contact_schema in self._schema.base_message.to.all()]

    @CustomProperty
    def from_(self):
        # type: () -> Contact
        """Get the Contact the message is addressed from

        Returns:
            Contact: The contact in the from field of the message
        """
        return Contact(self._schema.base_message.from_m, self._imap_client) if self._schema.base_message.from_m else None

    @CustomProperty
    def sender(self):
        # type: () -> Contact
        """Get the Contact the message is addressed from

        See also Message.from_

        Returns:
            Contact: The contact in the from field of the message
        """
        return self.from_

    @CustomProperty
    def reply_to(self):
        # type: () -> t.List[Contact]
        """Get the Contacts the message is replied to

        These are the addresses the message is meant to be sent to if the client
        hits reply.

        Returns:
            t.List[Contact]: The contacts in the reply_to field of the message
        """
        return [Contact(contact_schema, self._imap_client) for contact_schema in self._schema.base_message.reply_to.all()]

    @CustomProperty
    def cc(self):
        # type: () -> t.List[Contact]
        """Get the Contacts the message is cced to

        Returns:
            t.List[Contact]: The contacts in the cc field of the message
        """
        return [Contact(contact_schema, self._imap_client) for contact_schema in self._schema.base_message.cc.all()]

    @CustomProperty
    def bcc(self):
        # type: () -> t.List[Contact]
        """Get the Contacts the message is bcced to

        Returns:
            t.List[Contact]: The contacts in the bcc field of the message
        """
        return [Contact(contact_schema, self._imap_client) for contact_schema in self._schema.base_message.bcc.all()]

    @CustomProperty
    def recipients(self):
        # type: () -> t.List[Contact]
        """Shortcut method to get a list of all the recipients of an email.

        Returns the people in the to field, cc field, and bcc field 
        Useful for doing things like getting the total number of people a message is sent to

        Returns:
            t.List[Contact]: All the visible recipients of an email
        """
        return list(set(chain(self.to, self.cc, self.bcc)))

    @CustomProperty
    def folder(self):
        # type: () -> Folder
        """Get the Folder the message is contained in

        Returns:
            Folder: the folder that the message is contained in
        """
        from engine.models.folder import Folder
        return Folder(self._schema.folder, self._imap_client)

    @CustomProperty
    def content(self, return_only_text=True):
        # type: () -> t.AnyStr
        """Get the content of the message

        Returns:
            dict {'text': t.AnyStr, 'html': t.AnyStr}: The content of the message
        """
        return message_helpers.get_content_from_message(self)

    def _has_flag(self, flag):
        # type: (t.AnyStr) -> bool
        """Check if the message has a given flag

        Returns:
            bool: True if the flag is on the message else false
        """
        return flag in self.flags

    def _add_flags(self, flags):
        # type: (t.Union[t.Iterable[t.AnyStr], t.AnyStr]) -> None
        """Add each of the flags in a list of flags to the message

        Args: 
            flags (string[]): a list of flags to be added

        This method can also optionally take a single string as a flag.
        """
        if not isinstance(flags, list):
            flags = [flags]

        if self._is_simulate:
            flags = message_helpers._check_flags(self, flags)
        # add known flags to the correct place. i.e. \\Seen flag is not a gmail label
        if not self._is_simulate:
            message_helpers._flag_change_helper(self, self._uid, flags, self._imap_client.add_gmail_labels, self._imap_client.add_flags)

        self._flags = list(set(self.flags + flags))
        # message_helpers._save_flags(self, list(set(self.flags + flags)))

    def aggregate_response(self):
        # type: None -> t.List[(Contact, t.AnyStr)]
        """Aggregate responses of messages in this thread and return a list of pairs of sender and their response

        Returns:
            t.List[(Contact, t.AnyStr)]: pairs of sender and their response
        """
        
        a = []
        for m in self.thread:
            a.append((m.from_, EmailReplyParser.parse_reply(m.content['text'])))

        return a

    def _remove_flags(self, flags):
        # type: (t.Union[t.Iterable[t.AnyStr], t.AnyStr]) -> None
        """Remove each of the flags in a list of flags from the message

        This method can also optionally take a single string as a flag.
        """
        if not isinstance(flags, list):
            flags = [flags]

        if self._is_simulate:
            flags = message_helpers._check_flags(self, flags)
        if not self._is_simulate:
            message_helpers._flag_change_helper(self, self._uid, flags, self._imap_client.remove_gmail_labels, self._imap_client.remove_flags)

        # update the local flags
        self._flags = list(set(self.flags) - set(flags))
        # message_helpers._save_flags(self, list(set(self.flags) - set(flags)))

    def copy(self, dst_folder):
        # type: (t.AnyStr) -> None
        """Copy the message to another folder.
        """
        self._check_folder(dst_folder)

        if not self._is_message_already_in_dst_folder(dst_folder):
            if not self._is_simulate:
                self._imap_client.copy(self._uid, dst_folder)

    def delete(self):
        # type: () -> None
        """Mark a message as deleted, the imap server will move it to the deleted messages.
        """
        self._add_flags('\\Deleted')

    @ActionLogging
    def mark_read(self):
        # type: () -> None
        """Mark a message as read.
        """
        self._add_flags('\\Seen')

    @ActionLogging
    def mark_unread(self):
        # type: () -> None
        """Mark a message as unread
        """
        logger.exception("HEELo")
        self._remove_flags('\\Seen')

    def move(self, dst_folder):
        # type: (t.AnyStr) -> None
        """Move the message to another folder.
        """
        self._check_folder(dst_folder)
        if not self._is_message_already_in_dst_folder(dst_folder):
            if not self._is_simulate:
                try:
                    self._imap_client.move([self._uid], dst_folder)
                except exceptions.CapabilityError:
                    self.copy(dst_folder)
                    self.delete()
                    self._imap_client.expunge()

    @ActionLogging
    def _move(self, src_folder, dst_folder):
        """helper function for move() for logging and undo
        """
        pass

    @ActionLogging
    def forward(self, to=[], cc=[], bcc=[], subject="", content=""):
        to = format_email_address(to)
        cc = format_email_address(cc)
        bcc = format_email_address(bcc)

        new_message_wrapper = self._create_message_instance(
            subject or "Fwd: " + self.subject, to, cc, bcc, content)

        if not self._is_simulate:
            if new_message_wrapper:
                from engine.models.mailbox import MailBox  # noqa: F401 ignore unused we use it for typing
                mailbox = MailBox(self._schema.imap_account, self._imap_client)
                mailbox._send_message( new_message_wrapper )

    def contains(self, string):
        # type: (t.AnyStr) -> bool
        """check if a string is contained in the content of a message

        Args:
            string (str): string to check for

        Returns:
            bool: true if the passed in string is in the message content
        """
        if string is None:
            raise TypeError("contains(): input string should not be None")

        return string in self.content["text"] if self.content["text"] else False

    @CustomProperty
    def attachments(self):
        return message_helpers.get_attachments(self)

    @ActionLogging
    def reply(self, to=[], cc=[], bcc=[], content=""):
        # type: (t.Iterable[t.AnyStr], t.Iterable[t.AnyStr], t.Iterable[t.AnyStr], t.AnyStr) -> None
        """Reply to the sender of this message
        """
        if not self._is_simulate:
            to_addr = ""
            if isinstance(to, list):
                to.append(self.from_)
                to = format_email_address(to)
            else:
                to = format_email_address([self.from_, to])

            cc = format_email_address(cc)
            bcc = format_email_address(bcc)

            new_message_wrapper = self._create_message_instance(
                "Re: " + self.subject, to, cc, bcc, content)

            if len((to + cc + bcc).strip()) == 0:
                raise Exception("there has to be at least one recipient")

            if new_message_wrapper:
                from engine.models.mailbox import MailBox  # noqa: F401 ignore unused we use it for typing
                mailbox = MailBox(self._schema.imap_account, self._imap_client)
                mailbox._send_message( new_message_wrapper )

    @ActionLogging
    def reply_all(self, more_to=[], more_cc=[], more_bcc=[], content=""):
        if isinstance(more_cc, list):
            if len(self.cc) > 0:
                more_cc = more_cc + self.cc

        else:
            if more_cc:
                more_cc = self.cc + more_cc

        if isinstance(more_bcc, list):
            if len(self.bcc) > 0:
                more_bcc = more_bcc + self.bcc

        else:
            if more_bcc:
                more_bcc = self.bcc + more_bcc

        self.reply(more_to, more_cc, more_bcc, content)

    def on_response(self, handler):
        """add an event handler that is triggered everytime when there is a new message arrived at its thread

        Args:
            handler (function): A function to execute each time when there are messaged arrvied to this thread.
        """
        # add 

        pass
    
    def on_time(self, later_at, handler):
        """The number of hours to wait before executing the code. If omitted, the value 0 is used

        Args:
            later_at (int): when to move this message back to inbox (in minutes)
            handler (function): A function that will be executed
        """
        pass

    def see_later(self, later_at=60, hide_in='YouPS see later'):
        """Hide a message to a folder and move it back to a original folder

        my_message.on_time(now+later_at, f(message){ message.move('original_location') })

        Args:
            later_at (int): when to move this message back to inbox (in minutes)
            hide_in (string): a name of folder to hide this message temporarily
        """
        if not isinstance(later_at, datetime) and not isinstance(later_at, (int, long, float)):
            raise TypeError("see_later(): later_at " +
                            later_at + " is not number or datetime")

        if isinstance(later_at, (int, long, float)):
            later_at = timezone.now().replace(microsecond=0) + \
                timedelta(seconds=later_at*60)

        later_at = convertToUserTZ(later_at)

        current_folder = self._schema.folder.name
        if self._schema.imap_account.is_gmail and current_folder == "INBOX":
            current_folder = 'inbox'

        if not self._is_simulate:
            self.move(hide_in)

            # find message schema (at folder hide_in) of base message then move back to original message schema 
            code= {"base_message_id": self._schema.base_message.id,
                "hide_in": hide_in,
                "current_folder": current_folder}
            
            er = EmailRule(name='see later', type='see-later', code=json.dumps(code))
            er.save()

            
            
            t = TaskManager(email_rule=er, date=later_at,
                            imap_account=self._schema.imap_account)
            t.save()
            logger.critical("here %s" % hide_in)

        print("see_later(): Hide the message until %s at %s" %
              (prettyPrintTimezone(later_at), hide_in))

    def recent_messages(self, N=3):
        # type: (t.integer) -> t.List[Message]
        """Get the N Messages of this thread

        Returns:
            t.List[Message]: The messages in this thread before this message
        """

        if self._schema.imap_account.is_gmail:
            other_messages = ifilter(lambda m: m != self, self.thread.messages)
            return list(islice(other_messages, N))

        else:
            cnt_n = 0
            uid_to_fecth = self._uid
            prev_msg_id = None
            prev_messages = []
            logger.critical("recentmessages ")
            while cnt_n < N:
                if uid_to_fecth is None and prev_msg_id:
                    prev_msg_schema = MessageSchema.objects.filter(
                        folder__name=self.folder.name, message_id=prev_msg_id)
                    if prev_msg_schema.exists():
                        uid_to_fecth = prev_msg_schema[0].uid
                    else:
                        break
                    # uid_to_fecth = self._imap_client.search(["HEADER", "Message-ID", prev_msg_id])

                if uid_to_fecth:
                    in_reply_to_field = 'BODY[HEADER.FIELDS (IN-REPLY-TO)]'
                    prev_msg = self._imap_client.fetch(
                        [uid_to_fecth], ['FLAGS', in_reply_to_field])
                else:
                    break

                # TODO check if it is read
                for key, value in prev_msg.iteritems():
                    v = value[in_reply_to_field]
                    v.replace('\r\n\t', ' ')
                    v = v.replace('\r\n', ' ')

                    if not v:
                        continue

                    prev_msg_id = re.split(
                        '(IN-REPLY-TO:|In-Reply-To:)', v.strip())[-1].strip()
                    logger.critical(prev_msg_id)
                    uid_to_fecth = None

                    m_schema = MessageSchema.objects.filter(
                        message_id=prev_msg_id)
                    logger.critical(m_schema)
                    if m_schema.exists():
                        prev_messages.append(
                            Message(m_schema[0], self._imap_client))
                    # else:
                    #     break
                    # TODO message repr()
                    # TODO move run_simulate spinning bar under the table, not global

                cnt_n = cnt_n + 1
            # TODO mark as unread

            return prev_messages

    def _create_message_instance(self, subject='', to='', cc='', bcc='', additional_content=''):
        import pprint
        new_message_wrapper = MIMEMultipart('mixed')

        new_message_wrapper["Subject"] = subject

        new_message_wrapper["To"] = to
        new_message_wrapper["Cc"] = cc
        new_message_wrapper["Bcc"] = bcc

        new_message_wrapper['In-Reply-To'] = self._message_id
        new_message_wrapper['References'] = self._message_id

        # check if the message is initially read
        initially_read = self.is_read
        try:
            # fetch the data its a dictionary from uid to data so extract the data
            response = self._imap_client.fetch(
                self._uid, ['RFC822'])  # type: t.Dict[t.AnyStr, t.Any]
            if self._uid not in response:
                raise RuntimeError('Invalid response missing UID')
            response = response[self._uid]

            if 'RFC822' not in response:
                logger.critical('%s:%s response: %s' %
                                (self.folder, self, pprint.pformat(response)))
                logger.critical("%s did not return RFC822" % self)
                raise RuntimeError("Could not find RFC822")

            # text content
            new_message = MIMEMultipart('alternative')

            content = self.content
            separator = "On %s, (%s) wrote:" % (
                datetime.now().ctime(), self._schema.imap_account.email)
            text_content = additional_content.replace("<br>", "\n") + "\n\n" + \
                separator + "\n\n" + (content["text"] if content["text"] else "")
            html_content = additional_content.replace("\n", "<br>") + "<br><br>" + \
                separator + "<br><br>" + (content["html"] if content["html"] else content["text"] or "")

            # We must choose the body charset manually
            for body_charset in 'US-ASCII', 'ISO-8859-1', 'UTF-8':
                try:
                    text_content.encode(body_charset)
                except UnicodeError:
                    pass
                else:
                    break
            
            # We must choose the body charset manually
            for body_charset2 in 'US-ASCII', 'ISO-8859-1', 'UTF-8':
                try:
                    html_content.encode(body_charset2)
                except UnicodeError:
                    pass
                else:
                    break

            part1 = MIMEText(text_content.encode(body_charset), 'plain', body_charset)
            part2 = MIMEText(html_content.encode(body_charset2), 'html', body_charset2)
            new_message.attach(part1)
            new_message.attach(part2)

            # get attachments
            rfc_contents = email.message_from_string(
                response.get('RFC822'))  # type: email.message.Message

            res = get_attachments(rfc_contents)

            attachments = res['attachments']

            for attachment in attachments:
                p = MIMEBase('application', 'octet-stream')

                # To change the payload into encoded form
                p.set_payload(attachment['content'])

                # encode into base64
                encoders.encode_base64(p)

                p.add_header('Content-Disposition',
                             "attachment; filename= %s" % attachment['filename'])
                new_message_wrapper.attach(p)

            new_message_wrapper.attach(new_message)
        except Exception as e:
            logger.exception ("%s %s" % (e, traceback.format_exc()))
            raise RuntimeError('Failed to deal with a message: %s' % str(e))
            return
        finally:
            # mark the message unread if it is unread
            if not initially_read:
                self.mark_unread()

        return new_message_wrapper

    def _append_original_text(self, text, html, orig, google=False):
        """
        Append each part of the orig message into 2 new variables
        (html and text) and return them. Also, remove any 
        attachments. If google=True then the reply will be prefixed
        with ">". The last is not tested with html messages...
        """
        newhtml = ""
        newtext = ""

        for part in orig.walk():
            if (part.get('Content-Disposition')
                    and part.get('Content-Disposition').startswith("attachment")):

                part.set_type("text/plain")
                part.set_payload("Attachment removed: %s (%s, %d bytes)"
                                 % (part.get_filename(),
                                    part.get_content_type(),
                                    len(part.get_payload(decode=True))))
                del part["Content-Disposition"]
                del part["Content-Transfer-Encoding"]

            if part.get_content_type().startswith("text/plain"):
                newtext += "\n"
                newtext += part.get_payload(decode=False)
                if google:
                    newtext = newtext.replace("\n", "\n> ")

            elif part.get_content_type().startswith("text/html"):
                newhtml += "\n"
                newhtml += part.get_payload(decode=True).decode("utf-8")
                if google:
                    newhtml = newhtml.replace("\n", "\n> ")

        if newhtml == "":
            newhtml = newtext.replace('\n', '<br/>')

        return (text+'\n\n'+newtext, html+'<br/>'+newhtml)

    def _is_message_already_in_dst_folder(self, dst_folder):
        if dst_folder == self._schema.folder.name:
            userLogger.info(
                "message already in destination folder: %s" % dst_folder)
            return True
        return False

    def _check_folder(self, dst_folder):
        if not isinstance(dst_folder, basestring):
            raise TypeError("folder named must be a string")
        if not self._imap_client.folder_exists(dst_folder):
            userLogger.info(
                "folder %s does not exist creating it for you" % dst_folder)
            self._imap_client.create_folder(dst_folder)


    def _get_from_friendly(self):
        if self.from_._schema:
            return {
                "name": self.from_.name,
                "email": self.from_.email,
                "organization": self.from_.organization,
                "geolocation": self.from_.geolocation
            }

        return {}

    def _get_to_friendly(self):
        to = []
        for contact in self.to:
            to.append({
                "name": contact.name,
                "email": contact.email,
                "organization": contact.organization,
                "geolocation": contact.geolocation
            })

        return to

    def _get_cc_friendly(self):
        to = []
        for contact in self.cc:
            to.append({
                "name": contact.name,
                "email": contact.email,
                "organization": contact.organization,
                "geolocation": contact.geolocation
            })

        return to

    def _get_meta_data_friendly(self):
        return {
            "folder": self.folder.name,
            "subject": self.subject,
            "flags": [f.encode('utf8', 'replace') for f in self.flags],
            "date": prettyPrintTimezone(self.date), # convert it to users timezone
            "deadline": prettyPrintTimezone(self.deadline),
            "task": self.task,
            "is_read": self.is_read,
            "error": False
        }

    def add_flags_gmail(self, flags):
        # TODO see remove_flags_gmail same issue applies here
        if not self._imap_account.is_gmail:
            raise IsNotGmailException()
        if self._is_simulate:
            flags = message_helpers._check_flags(self, flags)
        uids = [m._uid for m in self.thread]
        if not self._is_simulate:
            message_helpers._flag_change_helper(self, uids, flags, self._imap_client.add_gmail_labels, self._imap_client.add_flags)
        for m in self.thread:
            message_helpers._save_flags(m, list(set(m.flags + flags)))

    def remove_flags_gmail(self, flags):

        # TODO this still feels broken. flags need to be removed from each message which has that flag
        # we need to go from the base message of this message to all the related messages
        # and then for each of those related messages if it contains a flag we want to remove
        # this from we need to remove that flag. but that requires calling imap_client.select_folder() which
        # i want to avoid

        if not self._imap_account.is_gmail:
            raise IsNotGmailException()
        uids = [m._uid for m in self.thread]
        if not self._is_simulate:
            message_helpers._flag_change_helper(self, uids, flags, self._imap_client.remove_gmail_labels, self._imap_client.remove_flags)
        for m in self.thread:
            message_helpers._save_flags(m, list(set(m.flags) - set(flags)))

    def mark_spam_gmail(self):
        # marks all emails in the thread as spam
        # gmail does this by removing the Inbox flag and adding the spam flag
        self.add_flags_gmail('\\Spam')
        self.remove_flags_gmail('\\Inbox')

    def unmark_spam_gmail(self):
        # unmark any email which has been marked as spam
        self.remove_flags_gmail('\\Spam')
        self.add_flags_gmail('\\Inbox')

    def archive_gmail(self):
        # marks all emails in the thread as archived
        # gmail does this by removing the Inbox, Spam, and Trash labels
        self.remove_flags_gmail(['\\Spam', '\\Inbox', '\\Trash'])

    def unarchive_gmail(self):
        # unarchive any messages that have been archived
        self.add_flags_gmail(['\\Inbox'])

    def delete_gmail(self):
        # marks all emails in the thread as deleted
        # gmail does this by removing the Inbox label, and adding the Trash label
        self.remove_flags_gmail(['\\Inbox'])
        self.add_flags_gmail(['\\Trash'])

    def undelete_gmail(self):
        # undelete any deleted email
        self.add_flags_gmail(['\\Inbox'])
        self.remove_flags_gmail(['\\Trash'])