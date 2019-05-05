from __future__ import unicode_literals, print_function, division
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing
import typing as t  # noqa: F401 ignore unused we use it for typing
import logging
from message import Message
from schema.youps import MessageSchema, FolderSchema, ContactSchema, ThreadSchema, ImapAccount  # noqa: F401 ignore unused we use it for typing
from django.db.models import Max
from imapclient.response_types import Address  # noqa: F401 ignore unused we use it for typing
from email.header import decode_header
from engine.models.event_data import NewMessageData, NewMessageDataScheduled, NewMessageDataDue, AbstractEventData, NewFlagsData, RemovedFlagsData
from datetime import datetime, timedelta
from email.utils import parseaddr
from dateutil import parser
from pytz import timezone
from django.utils import timezone as tz
from smtp_handler.utils import encoded_str_to_utf8_str, utf8_str_to_utf8_unicode
import chardet
import re
import heapq

logger = logging.getLogger('youps')  # type: logging.Logger


class Folder(object):

    def __init__(self, folder_schema, imap_client):
        # type: (FolderSchema, IMAPClient) -> Folder

        self._schema = folder_schema  # type: FolderSchema

        # the connection to the server
        self._imap_client = imap_client  # type: IMAPClient

    def __str__(self):
        # type: () -> t.AnyStr
        return "folder: %s" % (self.name)

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, Folder):
            return self._schema == other._schema
        return False


    @property
    def _uid_next(self):
        # type: () -> int
        return self._schema.uid_next

    @_uid_next.setter
    def _uid_next(self, value):
        # type: (int) -> None
        self._schema.uid_next = value
        self._schema.save()

    @property
    def _uid_validity(self):
        # type: () -> int
        return self._schema.uid_validity

    @_uid_validity.setter
    def _uid_validity(self, value):
        # type: (int) -> None
        self._schema.uid_validity = value
        self._schema.save()

    @property
    def _highest_mod_seq(self):
        # type: () -> int
        return self._schema.highest_mod_seq

    @_highest_mod_seq.setter
    def _highest_mod_seq(self, value):
        # type: (int) -> None
        self._schema.highest_mod_seq = value
        self._schema.save()

    @property
    def name(self):
        # type: () -> t.Text
        return self._schema.name

    @name.setter
    def name(self, value):
        # type: (t.Text) -> None
        self._schema.name = value
        self._schema.save()

    @property
    def flags(self):
        # type: () -> t.List[t.AnyStr]
        return self._schema.flags

    @flags.setter
    def flags(self, value):
        # type: (t.List[t.AnyStr]) -> None
        self._schema.flags = value
        self._schema.save()

    @property
    def _last_seen_uid(self):
        # type: () -> int
        return self._schema.last_seen_uid

    @_last_seen_uid.setter
    def _last_seen_uid(self, value):
        # type: (int) -> None
        self._schema.last_seen_uid = value
        self._schema.save()

    @property
    def _is_selectable(self):
        # type: () -> bool
        return self._schema.is_selectable

    @_is_selectable.setter
    def _is_selectable(self, value):
        # type: (bool) -> None
        self._schema.is_selectable = value
        self._schema.save()

    @property
    def _imap_account(self):
        # type: () -> ImapAccount
        return self._schema.imap_account

    def _completely_refresh_cache(self):
        # type: () -> None
        """Called when the uid_validity has changed or first time seeing the folder.

        Should completely remove any messages stored in this folder and rebuild
        the cache of messages from scratch.
        """

        logger.debug("%s completely refreshing cache" % self)

        # delete any messages already stored in the folder
        MessageSchema.objects.filter(folder_schema=self._schema).delete()

        # save new messages starting from the last seen uid of 0
        mail_ids = self._imap_client.search('SINCE 1-Jan-2019')
        if mail_ids:
            self._save_new_messages(min(mail_ids))
        else: # if there is no email in this year, save at least 5 latest messages. 
            mail_ids = self._imap_client.search()
            logger.info(mail_ids)
            if mail_ids:
                self._save_new_messages(min(heapq.nlargest(6, mail_ids)))
        # TODO maybe trigger the user

        # finally update our last seen uid (this uses the cached messages to determine last seen uid)
        self._update_last_seen_uid()
        logger.debug("%s finished completely refreshing cache" % self)

    def _update_last_seen_uid(self):
        # type () -> None
        """Updates the last seen uid to be equal to the maximum uid in this folder's cache
        """

        max_uid = MessageSchema.objects.filter(folder_schema=self._schema).aggregate(
            Max('uid'))  # type: t.Dict[t.AnyStr, int]
        max_uid = max_uid['uid__max']
        if max_uid is None:
            max_uid = 0
        if self._last_seen_uid != max_uid:
            self._last_seen_uid = max_uid
            logger.debug('%s updated max_uid %d' % (self, max_uid))

    def _refresh_cache(self, uid_next, highest_mod_seq, event_data_list):
        # type: (int, int, t.List[AbstractEventData]) -> None
        """Called during normal synchronization to refresh the cache.

        Should get new messages and build message number to UID map for the
        new messages.

        Should update cached flags on old messages, find out which old messages
        got expunged, build a message number to UID map for old messages.

        Args:
            uid_next (int): UIDNEXT returned from select command
        """
        # if the uid has not changed then we don't need to get new messages
        if uid_next != self._uid_next:
            # get all the descriptors for the new messages
            self._save_new_messages(self._last_seen_uid, event_data_list)
            # TODO maybe trigger the user

        # if the last seen uid is zero we haven't seen any messages
        if self._last_seen_uid != 0:
            self._update_cached_message_flags(highest_mod_seq, event_data_list)

        self._update_last_seen_uid()
        logger.debug("%s finished normal refresh" % (self))

    def _search_scheduled_message(self, event_data_list, time_start, time_end):
        message_schemas = MessageSchema.objects.filter(folder_schema=self._schema).filter(date__range=[time_start, time_end])
        
        # Check if there are messages arrived+time_span between (email_rule.executed_at, now), then add them to the queue
        for message_schema in message_schemas:
            logger.info("add schedule %s %s %s" % (time_start, message_schema.date, time_end))
            event_data_list.append(NewMessageDataScheduled(Message(message_schema, self._imap_client)))

    def _search_due_message(self, event_data_list, time_start, time_end):
        message_schemas = MessageSchema.objects.filter(folder_schema=self._schema).filter(deadline__range=[time_start, time_end])

        # Check if there are messages arrived+time_span between (email_rule.executed_at, now), then add them to the queue
        for message_schema in message_schemas:
            logger.info("add deadline queue %s %s %s" % (time_start, message_schema.deadline, time_end))
            event_data_list.append(NewMessageDataDue(Message(message_schema, self._imap_client)))

    def _should_completely_refresh(self, uid_validity):
        # type: (int) -> bool
        """Determine if the folder should completely refresh it's cache.

        Args:
            uid_validity (int): UIDVALIDITY returned from select command

        Returns:
            bool: True if the folder should completely refresh
        """

        if self._uid_validity == -1:
            return True
        if self._uid_validity != uid_validity:
            logger.debug(
                'folder %s uid_validity changed must rebuild cache' % self.name)
            return True
        return False

    def _update_cached_message_flags(self, highest_mod_seq, event_data_list):
        # type: (int, t.List[AbstractEventData]) -> None
        """Update the flags on any cached messages.
        """

        # we just check the highestmodseq and revert to full sync if they don't match
        # this is kind of what thunderbird does https://wiki.mozilla.org/Thunderbird:IMAP_RFC_4551_Implementation
        if highest_mod_seq is not None:
            if self._highest_mod_seq == highest_mod_seq:
                logger.debug("%s matching highest mod seq no flag update" % self)
                return

        logger.debug("%s started updating flags" % self)

        # get all the flags for the old messages
        fetch_data = self._imap_client.fetch('1:%d' % (self._last_seen_uid), [
                                             'FLAGS'])  # type: t.Dict[int, t.Dict[str, t.Any]]
        # update flags in the cache
        for message_schema in MessageSchema.objects.filter(folder_schema=self._schema):

            assert isinstance(message_schema, MessageSchema)
            # ignore cached messages that we just fetched
            if message_schema.uid > self._last_seen_uid:
                continue
            # if we don't get any information about the message we have to remove it from the cache
            if message_schema.uid not in fetch_data:
                message_schema.delete()
                logger.debug("%s deleted message with uid %d" %
                             (self, message_schema.uid))
                continue
            message_data = fetch_data[message_schema.uid]
            # TODO make this more DRY
            if 'SEQ' not in message_data:
                logger.critical('Missing SEQ in message data')
                logger.critical('Message data %s' % message_data)
                continue
            if 'FLAGS' not in message_data:
                logger.critical('Missing FLAGS in message data')
                logger.critical('Message data %s' % message_data)
                continue

            old_flags = set(message_schema.flags)
            new_flags = set(message_data['FLAGS'])

            if old_flags - new_flags:
                # flag removed old flag exists which does not exist in new flags
                event_data_list.append(RemovedFlagsData(Message(message_schema, self._imap_client), list(old_flags - new_flags)))
            elif new_flags - old_flags:
                # flag added, new flags exists which does not exist in old flags
                event_data_list.append(NewFlagsData(Message(message_schema, self._imap_client), list(new_flags - old_flags)))

            message_schema.flags = list(new_flags) 
            message_schema.msn = message_data['SEQ']
            message_schema.save()
            # TODO maybe trigger the user


        logger.debug("%s updated flags" % self)
        if highest_mod_seq is not None:
            self._highest_mod_seq = highest_mod_seq
            logger.debug("%s updated highest mod seq to %d" % (self, highest_mod_seq))


    def _save_new_messages(self, last_seen_uid, event_data_list = None, urgent=False):
        # type: (int, t.List[AbstractEventData]) -> None
        """Save any messages we haven't seen before

        Args:
            last_seen_uid (int): the max uid we have stored, should be 0 if there are no messages stored.
            urgent (bool): if True, save only one email 
        """

        # add thread id to the descriptors if there is a thread id
        descriptors = list(Message._descriptors) + ['X-GM-THRID'] if self._imap_account.is_gmail \
            else list(Message._descriptors)

        uid_criteria = ""
        if urgent:
            uid_criteria = '%d' % (last_seen_uid + 1)
        else: 
            uid_criteria = '%d:*' % (last_seen_uid + 1)
            
        fetch_data = self._imap_client.fetch(
            uid_criteria, descriptors)

        # seperate fetch in order to detect if the message is already read or not
        header_data = self._imap_client.fetch(
            uid_criteria, list(Message._header_descriptors))

        # if there is only one item in the return field
        # and we already have it in our database
        # delete it to be safe and save it again
        # TODO not sure why this happens maybe the folder._uid_next isn't getting updated properly
        if len(fetch_data) == 1 and last_seen_uid in fetch_data:
            already_saved = MessageSchema.objects.filter(folder_schema=self._schema, uid=last_seen_uid)
            if already_saved:
                logger.critical("%s found already saved message, deleting it" % self)
                already_saved[0].delete()

        logger.info("%s saving new messages" % (self))
        for uid in fetch_data:
            message_data = fetch_data[uid]
            header = header_data[uid]

            logger.debug("Message %d data: %s" % (uid, message_data))
            if 'SEQ' not in message_data:
                logger.critical('Missing SEQ in message data')
                logger.critical('Message data %s' % message_data)
                continue
            if 'FLAGS' not in message_data:
                logger.critical('Missing FLAGS in message data')
                logger.critical('Message data %s' % message_data)
                continue
            if 'INTERNALDATE' not in message_data:
                logger.critical('Missing INTERNALDATE in message data')
                logger.critical('Message data %s' % message_data)
                continue
            if 'RFC822.SIZE' not in message_data:
                logger.critical('Missing RFC822.SIZE in message data')
                logger.critical('Message data %s' % message_data)
                continue
            # if 'ENVELOPE' not in message_data:
            #     logger.critical('Missing ENVELOPE in message data')
            #     logger.critical('Message data %s' % message_data)
            #     continue
            if self._imap_account.is_gmail and 'X-GM-THRID' not in message_data:
                logger.critical('Missing X-GM-THRID in message data')
                logger.critical('Message data %s' % message_data)
                continue

            # check for supported thread algorithms here
            if not self._imap_account.is_gmail:
                capabilities = self._imap_client.capabilities()
                capabilities = list(capabilities)
                capabilities = filter(lambda cap: 'THREAD=' in cap, capabilities)
                capabilities = [cap.replace('THREAD=', '') for cap in capabilities]
                # logger.debug("Add support for one of the following threading algorithms %s" % capabilities)
                # raise NotImplementedError("Unsupported threading algorithm")

            # this is the date the message was received by the server
            internal_date = message_data['INTERNALDATE']  # type: datetime
            msn = message_data['SEQ']
            flags = message_data['FLAGS']

            if "\\Seen" not in flags:
                self._imap_client.remove_flags(uid, ['\\Seen'])

            # header = [h.replace('\r\n\t', ' ') for h in header]
            header = header[list(Message._header_descriptors)[0]]
            try:
                header = header.replace('\r\n\t', ' ')
                header = header.replace('\r\n', ' ')
            except UnicodeDecodeError:
                logger.exception('unicode error in headers, fixed in future branch')
                continue
            meta_data = {}

            # figure out text encoding issue here 
            # logger.info(header[uid][list(Message._header_descriptors)[0]])
            try:
                header = self._parse_email_header(header)
            except Exception as e:
                logger.critical("header parsing problem %s  %s, skip this message" % (header, e))
                continue
    
            try: 
                f_tmp = ""
                header_field = ['Subject:', 'From:', 'To:', 'Cc:', 'CC:', 'Bcc:', 'date:', 'Date:', 'In-Reply-To:', 'Message-Id:', 'Message-ID:', 'Message-id:']
                
                for v in re.split('('+ "|".join(header_field) +')', header):
                    if not v:
                        continue

                    if v.strip() in header_field:
                        # Remove a colon and add to a dict
                        f_tmp = v[:-1].lower().strip()

                    else:
                        meta_data[f_tmp] = v.strip()
            except Exception as e:
                logger.critical("header parsing problem %s, skip this message" % e)
                continue

            

            # if we have a gm_thread_id set thread_schema to the proper thread
            gm_thread_id = message_data.get('X-GM-THRID') 
            thread_schema = None
            if gm_thread_id is not None:
                result = self._imap_client.search(['X-GM-THRID', gm_thread_id])
                logger.debug("thread messages %s, current message %d" % (result, uid))
                thread_schema = self._find_or_create_thread(gm_thread_id)

            logger.debug("message %d envelope %s" % (uid, meta_data))

            try:
                if internal_date.tzinfo is None or internal_date.tzinfo.utcoffset(internal_date) is None:
                    internal_date = timezone('US/Eastern').localize(internal_date)
                    # logger.critical("convert navie %s " % internal_date)
            except Exception:
                logger.critical("Internal date parsing error %s" % internal_date)
                continue

            try:
                date = parser.parse(meta_data["date"])

                # if date is naive then reinforce timezone
                if date.tzinfo is None or date.tzinfo.utcoffset(date) is None:
                    date = timezone('US/Eastern').localize(date)
            except Exception:
                if "date" in meta_data:
                    logger.critical("Can't parse date %s, skip this message" % meta_data["date"])
                    continue
                else:
                    date = internal_date
                    logger.info("Date not exist, put internal date instead")


            # TODO seems like bulk email often not have a message-id
            if "message-id" not in meta_data:
                logger.critical("message-id not exist, skil this message %s" % meta_data)
                continue

            # create and save the message schema
            message_schema = MessageSchema(imap_account=self._schema.imap_account,
                                           folder_schema=self._schema,
                                           uid=uid,
                                           msn=msn,
                                           flags=flags,
                                           date=date,
                                           subject="" if "subject" not in meta_data else meta_data['subject'],
                                           message_id=meta_data["message-id"],
                                           internal_date=internal_date,
                                           _thread=thread_schema
                                           )

            if "from" in meta_data:
                message_schema.from_m = self._find_or_create_contacts(meta_data['from'])[0]
            # if envelope.from_ is not None:
            #     message_schema.from_m = self._find_or_create_contacts(envelope.from_)[0]

            try:
                message_schema.save()
            except Exception as e:
                logger.critical("%s failed to save message %d" % (self, uid))
                logger.critical("%s stored last_seen_uid %d, passed last_seen_uid %d" % (self, self._last_seen_uid, last_seen_uid))
                logger.critical("number of messages returned %d" % (len(fetch_data)))
                
                # to prevent dup saved email
                continue

            if last_seen_uid != 0 and event_data_list is not None:
                logger.critical(internal_date)
                if tz.now() - internal_date < timedelta(seconds=5*60):
                    event_data_list.append(NewMessageData(Message(message_schema, self._imap_client)))

            logger.debug("%s finished saving new messages..:" % self)

            # create and save the message contacts
            if "reply-to" in meta_data:
                message_schema.reply_to.add(*self._find_or_create_contacts(meta_data["reply-to"]))
            if "to" in meta_data:
                message_schema.to.add(*self._find_or_create_contacts(meta_data["to"]))
            if "cc" in meta_data:
                message_schema.cc.add(*self._find_or_create_contacts(meta_data["cc"]))
            if "bcc" in meta_data:
                message_schema.bcc.add(*self._find_or_create_contacts(meta_data["bcc"]))

            logger.debug("%s saved new message with uid %d" % (self, uid))

    def _find_or_create_thread(self, gm_thread_id):
        # type: (int) -> ThreadSchema
        """Return a reference to the thread schema.

        Returns:
            ThreadSchema: Thread associated with the passed in gm_thread_id

        """

        thread_schema = None  # type: ThreadSchema
        try:
            thread_schema = ThreadSchema.objects.get(
                imap_account=self._imap_account, folder=self._schema, gm_thread_id=gm_thread_id)
        except ThreadSchema.DoesNotExist:
            thread_schema = ThreadSchema(
                imap_account=self._imap_account, folder=self._schema, gm_thread_id=gm_thread_id)
            thread_schema.save()
            logger.debug("%s created thread %s in database" % (self, gm_thread_id))

        return thread_schema

    def _parse_email_subject(self, subject):
        # type: (t.AnyStr) -> t.AnyStr
        """This method parses a subject header which can contain unicode

        Args:
            subject (str): email subject header

        Returns:
            t.AnyStr: unicode string or a 8 bit string
        """

        if subject is None:
            return None
        text, encoding = decode_header(subject)[0]
        if encoding:
            if encoding != 'utf-8' and encoding != 'utf8':
                logger.debug('parse_subject non utf8 encoding: %s' % encoding)
            text = text.decode(encoding)
        return text

    def _parse_email_header(self, header):
        try:
            lines = decode_header(header)
        except Exception:
            header = header.replace('_', '/')
            lines = decode_header(header)

        header_text = ""
        for line in lines:
            text, encoding = line[0], line[1]
            if encoding:
                if encoding != 'utf-8' and encoding != 'utf8':
                    logger.info('parse_subject non utf8 encoding: %s' % encoding)
                text = text.decode(encoding, errors='ignore')
            else:
                text = unicode(text, encoding='utf8')
            header_text = header_text + text
        return header_text
            

    def _find_or_create_contacts(self, addresses):
        # type: (t.List[Address]) -> t.List[ContactSchema]
        """Convert a list of addresses into a list of contact schemas.

        Returns:
            t.List[ContactSchema]: List of contacts associated with the addresses
        """
        assert addresses is not None

        contact_schemas = []
        for address in addresses.split(","):
            contact_schema = None  # type: ContactSchema

            # email = "%s@%s" % (address.mailbox, address.host)
            name, email = parseaddr(address)
            logger.info(name, email)
            try:
                contact_schema = ContactSchema.objects.get(
                    imap_account=self._imap_account, email=email)
                
                # if we get a new name, then save the name to the contact
                if name:
                    contact_schema.name = name
                    contact_schema.save()
                    
            except ContactSchema.DoesNotExist:
                contact_schema = ContactSchema(
                    imap_account=self._imap_account, email=email, name=name)
                contact_schema.save()
                logger.debug("created contact %s in database" % name)

            contact_schemas.append(contact_schema)
        return contact_schemas
