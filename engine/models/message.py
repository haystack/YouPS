from __future__ import unicode_literals, print_function, division
import typing as t  # noqa: F401 ignore unused we use it for typing
from schema.youps import MessageSchema  # noqa: F401 ignore unused we use it for typing
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing
from datetime import datetime  # noqa: F401 ignore unused we use it for typing
from engine.models.contact import Contact
import logging
from collections import Sequence
import email
import inspect
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase 
from email import encoders  
from smtp_handler.utils import get_attachments, format_email_address
import smtplib
from pytz import timezone as tz
from django.utils import timezone

from engine.google_auth import GoogleOauth2
from browser.imap import decrypt_plain_password
from http_handler.settings import CLIENT_ID

userLogger = logging.getLogger('youps.user')  # type: logging.Logger
logger = logging.getLogger('youps')  # type: logging.Logger


class Message(object):

    # the descriptors we are cacheing for each message
    _descriptors = ['FLAGS', 'INTERNALDATE',
                    'RFC822.SIZE']  # type: t.List[t.Text]
    _header_descriptors= ['BODY[HEADER.FIELDS (SUBJECT FROM TO CC BCC DATE IN-REPLY-TO MESSAGE-ID)]']
    _user_level_func = ['on_message']

    def __init__(self, message_schema, imap_client, is_simulate=False):
        # type: (MessageSchema, IMAPClient) -> Message

        self._schema = message_schema  # type: MessageSchema

        # the connection to the server
        self._imap_client = imap_client  # type: IMAPClient
        
        # if True, then only local execute and don't transmit to the server. 
        self.is_simulate = is_simulate  # type: bool

        # local copy of flags for simulating
        self._flags = self._schema.flags
        logger.debug( 'caller name: %s', inspect.stack()[1][3] )

    def __str__(self):
        # type: () -> t.AnyStr
        return "Message %d" % self._uid

    def _before(self):
        pass

    def _after(self):
        pass

    @property
    def _uid(self):
        # type: () -> int
        return self._schema.uid

    @_uid.setter
    def _uid(self, value):
        # type: (int) -> None
        self._schema.uid = value
        self._schema.save()

    @property
    def _msn(self):
        # type: () -> int
        return self._schema.msn

    @_msn.setter
    def _msn(self, value):
        # type: (int) -> None
        self._schema.msn = value
        self._schema.save()

    @property
    def _message_id(self):
        # type: () -> int
        return self._schema.message_id

    @property
    def flags(self):
        # type: () -> t.List[t.AnyStr]
        """Get the flags on the message

        Returns:
            List(str): List of flags on the message
        """
        return self._flags if self.is_simulate else self._schema.flags

    def diff_attr(self, obj_instance):
        for attr, value in self.__dict__.iteritems():
            if getattr(self, attr) != getattr(obj_instance, attr):
                print ("different val", attr, value)

    @flags.setter
    def flags(self, value):
        # type: (t.List[t.AnyStr]) -> None
        """Set the flags on the message
        """
        # TODO we probably don't want user's calling this directly since
        # we don't validate the input and it doesn't update the server
        # it shouldn't update the server though since we are using
        # this method to update only our local copy
        # users update the server using add_flags or one of the aliases
        if not self.is_simulate:
            self._schema.flags = value
            self._schema.save()

        self._flags = value

    @property
    def deadline(self):
        # type: () -> t.AnyStr
        """Get the user-defined deadline of the message

        Returns:
            str: The deadline
        """
        return self._schema.deadline

    @deadline.setter
    def deadline(self, value):
        # type: (datetime.datetime -> None
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            value = tz('US/Eastern').localize(value)
            value = timezone.localtime(value)
            logger.info(value)

        if not self.is_simulate:
            self._schema.deadline = value
            self._schema.save()

    @property
    def subject(self):
        # type: () -> t.AnyStr
        """Get the Subject of the message

        Returns:
            str: The subject of the message
        """
        return self._schema.subject

    @property
    def thread(self):
        # type: () -> t.Optional[Thread]
        from engine.models.thread import Thread
        if self._schema._thread is not None:
            return Thread(self._schema._thread, self._imap_client)
        return None

    @property
    def date(self):
        # type: () -> datetime
        """Get the date and time that the message was sent

        Returns:
            datetime: The date and time the message was sent
        """
        return self._schema.date

    @property
    def is_read(self):
        # type: () -> bool
        """Get if the message has been read

        Returns:
            bool: True if the message has been read
        """
        # logger.info('caller name: %s', inspect.stack())
        caller_line_no = inspect.stack()[1][2]
        caller_func_name = inspect.stack()[1][3]

        if caller_func_name in self._user_level_func:
            pass
        # logger.info('caller name: %s %d' % (, )
        return '\\Seen' in self.flags

    @property
    def is_deleted(self):
        # type: () -> bool
        """Get if the message has been deleted

        Returns:
            bool: True if the message has been deleted
        """
        return '\\Deleted' in self.flags

    @property
    def is_recent(self):
        # type: () -> bool
        """Get if the message is recent

        Returns:
            bool: True if the message is recent
        """
        # TODO we will automatically remove the RECENT flag unless we make our imapclient ReadOnly
        return '\\Recent' in self.flags

    @property
    def to(self):
        # type: () -> t.List[Contact]
        """Get the Contacts the message is addressed to

        Returns:
            t.List[Contact]: The contacts in the to field of the message
        """
        
        return [Contact(contact_schema, self._imap_client) for contact_schema in self._schema.to.all()]

    @property
    def from_(self):
        # type: () -> Contact
        """Get the Contacts the message is addressed from

        Returns:
            Contact: The contact in the from field of the message
        """
        return Contact(self._schema.from_m, self._imap_client) if self._schema.from_m else None

    @property
    def sender(self):
        # type: () -> t.List[Contact]
        """Get the Contacts the message is sent from

        Returns:
            Contact: The contact in the sender field of the message
        """
        return Contact(self._schema.sender, self._imap_client)

    @property
    def reply_to(self):
        # type: () -> t.List[Contact]
        """Get the Contacts the message is replied to

        Returns:
            t.List[Contact]: The contacts in the reply_to field of the message
        """
        return [Contact(contact_schema, self._imap_client) for contact_schema in self._schema.reply_to.all()]

    @property
    def cc(self):
        # type: () -> t.List[Contact]
        """Get the Contacts the message is cced to

        Returns:
            t.List[Contact]: The contacts in the cc field of the message
        """
        return [Contact(contact_schema, self._imap_client) for contact_schema in self._schema.cc.all()]

    @property
    def bcc(self):
        # type: () -> t.List[Contact]
        """Get the Contacts the message is bcced to

        Returns:
            t.List[Contact]: The contacts in the bcc field of the message
        """
        return [Contact(contact_schema, self._imap_client) for contact_schema in self._schema.bcc.all()]

    @property
    def folder(self):
        # type: () -> Folder
        """Get the Folder the message is contained in

        Returns:
            Folder: the folder that the message is contained in
        """
        from engine.models.folder import Folder
        return Folder(self._schema.folder_schema, self._imap_client)

    @property
    def content(self, return_only_text=True):
        # type: () -> t.AnyStr
        """Get the content of the message

        Returns:
            dict {'text': t.AnyStr, 'html': t.AnyStr}: The content of the message
        """

        import pprint

        # check if the message is initially read
        initially_unread = self.is_read
        try:

            # fetch the data its a dictionary from uid to data so extract the data 
            response = self._imap_client.fetch(
                self._uid, ['RFC822'])  # type: t.Dict[t.AnyStr, t.Any]
            if self._uid not in response:
                raise RuntimeError('Invalid response missing UID')
            response = response[self._uid]

            # get the rfc data we're looking for
            if 'RFC822' not in response:
                logger.critical('%s:%s response: %s' % (self.folder, self, pprint.pformat(response)))
                logger.critical("%s did not return RFC822" % self)
                raise RuntimeError("Could not find RFC822")
            rfc_contents = email.message_from_string(
                response.get('RFC822'))  # type: email.message.Message

            text = ""
            html = ""
            extra = {}

            # walk the message
            for part in rfc_contents.walk():
                # TODO respect multipart/[alternative, mixed] etc... see RFC1341
                if part.is_multipart():
                    continue

                # for each part get the maintype and subtype
                main_type = part.get_content_maintype()
                sub_type = part.get_content_subtype()

                # parse text types
                if main_type == "text":
                    text_contents = None
                    # get the charset used to encode the message
                    charset = part.get_content_charset()

                    # get the text as encoded unicode
                    if charset is not None:
                        text_contents = unicode(part.get_payload(
                            decode=True), charset, "ignore")
                    else:
                        logger.critical("%s no charset found on" % self)
                        raise RuntimeError("Message had no charset")

                    # extract plain text
                    if sub_type == "plain":
                        text += text_contents
                    # extract html
                    elif sub_type == "html":
                        html += text_contents
                    # extract calendar
                    elif sub_type == "calendar":
                        if sub_type not in extra:
                            extra[sub_type] = ""
                        extra[sub_type] += text_contents
                    # fail otherwise
                    else:
                        logger.critical(
                            "%s unsupported sub type %s" % (self, sub_type))
                        raise NotImplementedError(
                            "Unsupported sub type %s" % sub_type)

            # return text if we have it otherwise html
            # return text if text else html
            if return_only_text:
                return {"text": text, "html": html}
            else:
                extra['text'] = text
                extra['html'] = html

                return extra

        finally:
            # mark the message unread if it is unread
            if initially_unread:
                self.mark_read() 

    def has_flag(self, flag):
        # type: (t.AnyStr) -> bool
        """Check if the message has a given flag

        Returns:
            bool: True if the flag is on the message else false
        """
        return flag in self.flags

    def add_flags(self, flags):
        # type: (t.Iterable[t.AnyStr]) -> None
        """Add each of the flags in a list of flags to the message

        Raises:
            TypeError: flags is not an iterable or a string
            TypeError: any flag is not a string
        """
        # cp_self = copy.deepcopy(self)

        ok, flags = self._check_flags(flags)
        if not ok:
            return

        if not self.is_simulate:
            # TODO the add methods return flags we should use those values instead of doing the work ourself
            if self._schema.imap_account.is_gmail:
                self._imap_client.add_gmail_labels(self._uid, flags)
            else:
                self._imap_client.add_flags(self._uid, flags)
        # update the local flags
        self.flags = list(set(self.flags + flags))

        # self.diff_attr(cp_self)

    def remove_flags(self, flags):
        # type: (t.Iterable[t.AnyStr]) -> None
        """Remove each of the flags in a list of flags from the message

        Raises:
            TypeError: flags is not an iterable or a string
            TypeError: any flag is not a string
        """
        ok, flags = self._check_flags()
        if not ok:
            return
        
        if not self.is_simulate:
            # TODO the remove methods return flags we should use those values instead of doing the work ourself
            if self._schema.imap_account.is_gmail:
                self._imap_client.remove_gmail_labels(self._uid, flags)
            else:
                self._imap_client.remove_flags(self._uid, flags)
                
        # update the local flags
        self.flags = set(self.flags) - set(flags)

    def copy(self, dst_folder):
        # type: (t.AnyStr) -> None
        """Copy the message to another folder.
        """
        self._check_folder(dst_folder)
        
        if not self._is_message_already_in_dst_folder(dst_folder):
            if not self.is_simulate:
                self._imap_client.copy(self._uid, dst_folder)

    def delete(self):
        # type: () -> None
        """Mark a message as deleted, the imap server will move it to the deleted messages.
        """
        if not self.is_simulate:
            self.add_flags('\\Deleted')

    def mark_read(self):
        # type: () -> None
        """Mark a message as read.
        """
        if not self.is_simulate:
            self._imap_client.add_flags(self._uid, ['\\Seen'])

    def mark_unread(self):
        # type: () -> None
        """Mark a message as unread
        """
        if not self.is_simulate:
            self._imap_client.remove_flags(self._uid, ['\\Seen'])

    def move(self, dst_folder):
        # type: (t.AnyStr) -> None
        """Move the message to another folder.
        """
        self._check_folder(dst_folder)
        if not self._is_message_already_in_dst_folder(dst_folder):
            if not self.is_simulate:
                self._imap_client.move(self._uid, dst_folder)

    def forward(self, to=[], cc=[], bcc=[], content=""):
        if not self.is_simulate:
            to = format_email_address(to)
            cc = format_email_address(cc)
            bcc = format_email_address(bcc)

            new_message_wrapper = self._create_message_instance("Fwd: " + self.subject, to, cc, bcc, content)

            if new_message_wrapper:
                self._send_message(new_message_wrapper)

    def reply(self, to=[], cc=[], bcc=[], content=""):
        # type: (t.Iterable[t.AnyStr], t.Iterable[t.AnyStr], t.Iterable[t.AnyStr], t.AnyStr) -> None
        """Reply to the sender of this message
        """
        if not self.is_simulate:
            to_addr = ""
            if isinstance(to, list):
                to_addr = to.append(self._schema.from_)
                to = format_email_address(to_addr)
            else:
                to = format_email_address([self._schema.from_, to])

            cc = format_email_address(cc)
            bcc = format_email_address(bcc)

            new_message_wrapper = self._create_message_instance("Re: " + self.subject, to, cc, bcc, content)

            if new_message_wrapper:
                self._send_message(new_message_wrapper)

    def reply_all(self, more_to=[], more_cc=[], more_bcc=[], content=""):
        if isinstance(more_cc, list):
            if len(self.cc) > 0:
                more_cc = more_cc + self.cc

        else:
            if more_cc:
                l = self.cc
                l.append(more_cc)
                more_cc = l

        if isinstance(more_bcc, list):
            if len(self.bcc) > 0:
                more_bcc = more_bcc + self.bcc

        else:
            if more_bcc:
                l = self.bcc
                l.append(more_bcc)
                more_bcc = l

        self.reply(more_to, more_cc, more_bcc, content)
            
    def _create_message_instance(self, subject='', to='', cc='', bcc='', additional_content=''):
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
                logger.critical('%s:%s response: %s' % (self.folder, self, pprint.pformat(response)))
                logger.critical("%s did not return RFC822" % self)
                raise RuntimeError("Could not find RFC822")

            # text content
            new_message = MIMEMultipart('alternative')   

            content = self.content
            separator = "On %s, (%s) wrote:" % (datetime.now().ctime(), self._schema.imap_account.email)
            text_content = additional_content + "\n\n" + separator + "\n\n" + content["text"]
            html_content = additional_content + "<br><br>" + separator + "<br><br>" + content["html"]

            part1 = MIMEText(text_content.encode('utf-8'), 'plain')
            part2 = MIMEText(html_content.encode('utf-8'), 'html')
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
                
                p.add_header('Content-Disposition', "attachment; filename= %s" % attachment['filename']) 
                new_message_wrapper.attach(p)

            new_message_wrapper.attach(new_message)
        except Exception as e:
            print (e)
            return
        finally:
            # mark the message unread if it is unread
            if not initially_read:
                self.mark_unread() 

        return new_message_wrapper

    def _send_message(self, new_message_wrapper):
        try: 
            # SMTP authenticate 
            if self._schema.imap_account.is_gmail:
                oauth = GoogleOauth2()
                response = oauth.RefreshToken(self._schema.imap_account.refresh_token)
            
                auth_string = oauth.generate_oauth2_string(self._schema.imap_account.email, response['access_token'], as_base64=True)
                s = smtplib.SMTP('smtp.gmail.com', 587)
                s.ehlo(CLIENT_ID)
                s.starttls()
                s.docmd('AUTH', 'XOAUTH2 ' + auth_string)
                
            else:
                s = smtplib.SMTP(self._schema.imap_account.host.replace("imap", "smtp"), 587)
                s.login(self._schema.imap_account.email, decrypt_plain_password(self._schema.imap_account.password))
                s.ehlo()

            # TODO check if it sent to cc-ers
            s.sendmail(self._schema.imap_account.email, new_message_wrapper["To"], new_message_wrapper.as_string())
        except Exception as e:
            print (e)

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
                            %(part.get_filename(), 
                            part.get_content_type(), 
                            len(part.get_payload(decode=True))))
                del part["Content-Disposition"]
                del part["Content-Transfer-Encoding"]

            if part.get_content_type().startswith("text/plain"):
                newtext += "\n"
                newtext += part.get_payload(decode=False)
                if google:
                    newtext = newtext.replace("\n","\n> ")

            elif part.get_content_type().startswith("text/html"):
                newhtml += "\n"
                newhtml += part.get_payload(decode=True).decode("utf-8")
                if google:
                    newhtml = newhtml.replace("\n", "\n> ")

        if newhtml == "":
            newhtml = newtext.replace('\n', '<br/>')

        return (text+'\n\n'+newtext, html+'<br/>'+newhtml)

    def _is_message_already_in_dst_folder(self, dst_folder):
        if dst_folder == self._schema.folder_schema.name:
            userLogger.info(
                "message already in destination folder: %s" % dst_folder)
            return False
        return True

    def _check_folder(self, dst_folder):
        if not isinstance(dst_folder, basestring):
            raise TypeError("folder named must be a string")
        if not self._imap_client.folder_exists(dst_folder):
            userLogger.info(
                "folder %s does not exist creating it for you" % dst_folder)
            self._imap_client.create_folder(dst_folder)

    def _check_flags(self, flags):
        # type: (t.Iterable[t.AnyStr]) -> bool, t.Iterable[t.AnyStr]
        """Check user defined flags

        Raises:
            TypeError: Flag is not an instance of a python Sequence
            TypeError: Some flag is not a string

        Returns:
            t.Tuple[bool, t.List[t.AnyStr]]: Tuple of whether the check passed and the flags as a list
        """

        ok = True
        # allow user to pass in a string
        if isinstance(flags, basestring):
            flags = [flags]
        elif not isinstance(flags, Sequence):
            raise TypeError("flags must be a sequence")

        if not isinstance(flags, list):
            flags = list(flags)

        # make sure all flags are strings
        for flag in flags:
            if not isinstance(flag, basestring):
                raise TypeError("each flag must be string")
        # remove extraneous white space
        flags = [flag.strip() for flag in flags]
        # remove empty strings
        flags = [flag for flag in flags if flag]
        if not flags:
            ok = False
            userLogger.info("No valid flags passed")
        return ok, flags
