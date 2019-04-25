from __future__ import unicode_literals, print_function, division
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing
import typing as t  # noqa: F401 ignore unused we use it for typing
import chardet
import logging
from engine.models.message import Message
from schema.youps import MessageSchema, FolderSchema, ContactSchema, ThreadSchema, ImapAccount, UniqueMessageSchema  # noqa: F401 ignore unused we use it for typing
from django.db.models import Max
from imapclient.response_types import Address  # noqa: F401 ignore unused we use it for typing
from email.header import decode_header
from engine.models.event_data import MessageArrivalData, NewMessageDataScheduled, NewMessageDataDue, AbstractEventData, NewFlagsData, RemovedFlagsData, MessageMovedData
from datetime import datetime, timedelta
from email.utils import parseaddr
from dateutil import parser
from pytz import timezone
from django.utils import timezone as tz
import re
import heapq
from string import whitespace

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

    def _get_min_mail_id(self):
        # we should save new messages starting from the last seen uid of 0
        # instead we save new messages starting from the current year

        # to return all mail just comment out the following line
        # return 1

        mail_ids = self._imap_client.search(
            'SINCE 1-Jan-{year}'.format(year=datetime.now().year))
        if mail_ids:
            return min(mail_ids)
        else:  # if there is no email in this year, save at least 5 latest messages.
            mail_ids = self._imap_client.search()
            if mail_ids:
                return min(heapq.nlargest(6, mail_ids))
        # return 0 if there are no messages
        return 0

    def _completely_refresh_cache(self):
        # type: () -> None
        """Called when the uid_validity has changed or first time seeing the folder.

        Should completely remove any messages stored in this folder and rebuild
        the cache of messages from scratch.
        """

        logger.debug("%s completely refreshing cache" % self)

        # delete any messages already stored in the folder
        MessageSchema.objects.filter(folder_schema=self._schema).delete()

        min_mail_id = self._get_min_mail_id()
        if min_mail_id is not None:
            self._save_new_messages(min_mail_id)
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
        message_schemas = MessageSchema.objects.filter(
            folder_schema=self._schema).filter(date__range=[time_start, time_end])

        # Check if there are messages arrived+time_span between (email_rule.executed_at, now), then add them to the queue
        for message_schema in message_schemas:
            logger.info("add schedule %s %s %s" %
                        (time_start, message_schema.date, time_end))
            event_data_list.append(NewMessageDataScheduled(
                Message(message_schema, self._imap_client)))

    def _search_due_message(self, event_data_list, time_start, time_end):
        message_schemas = MessageSchema.objects.filter(
            folder_schema=self._schema).filter(deadline__range=[time_start, time_end])

        # Check if there are messages arrived+time_span between (email_rule.executed_at, now), then add them to the queue
        for message_schema in message_schemas:
            logger.info("add deadline queue %s %s %s" %
                        (time_start, message_schema.deadline, time_end))
            event_data_list.append(NewMessageDataDue(
                Message(message_schema, self._imap_client)))

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
                logger.debug(
                    "%s matching highest mod seq no flag update" % self)
                return

        logger.debug("%s started updating flags" % self)

        min_mail_id = self._get_min_mail_id()
        # get all the flags for the old messages
        fetch_data = self._imap_client.fetch('%d:%d' % (min_mail_id, self._last_seen_uid), Message._get_flag_descriptors(
            self._imap_account.is_gmail))  # type: t.Dict[int, t.Dict[str, t.Any]]

        # update flags in the cache
        for message_schema in MessageSchema.objects.filter(folder_schema=self._schema).iterator():
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
            ok = self._check_fields_in_fetch(Message._get_flag_descriptors(
                self._imap_account.is_gmail) + ['SEQ'], message_data)
            if not ok:
                continue

            self._cleanup_message_data(message_data)

            old_flags = set(message_schema.base_message.flags)
            new_flags = set(message_data['FLAGS'])

            flags_removed = old_flags - new_flags
            flags_added = new_flags - old_flags

            if flags_removed:
                # flag removed old flag exists which does not exist in new flags
                logger.info('folder {f}: uid {u}: flags_removed {a}'.format(f=self.name, u=message_schema.uid, a=flags_removed))
                event_data_list.append(RemovedFlagsData(
                    Message(message_schema, self._imap_client), list(flags_removed)))
            if flags_added:
                # flag added, new flags exists which does not exist in old flags
                logger.info('folder {f}: uid {u}: flags_added {a}'.format(f=self.name, u=message_schema.uid, a=flags_added))
                event_data_list.append(NewFlagsData(
                    Message(message_schema, self._imap_client), list(flags_added)))

            if flags_added or flags_removed:
                message_schema.base_message.flags = list(new_flags)
                message_schema.base_message.save()

            if message_schema.msn != message_data['SEQ']:
                message_schema.msn = message_data['SEQ']
                message_schema.save()

        logger.debug("%s updated flags" % self)
        if highest_mod_seq is not None:
            self._highest_mod_seq = highest_mod_seq
            logger.debug("%s updated highest mod seq to %d" %
                         (self, highest_mod_seq))

    def _check_fields_in_fetch(self, fields, message_data):
        # type: (t.List[t.Text], t.Dict[t.Text, t.Any]) -> bool
        for field in fields:
            if field not in message_data:
                logger.critical(
                    'Missing {field} in message data'.format(field=field))
                logger.critical('Message data %s' % message_data)
                return False
        return True

    def _parse_header_date(self, str_date):
        # type: (t.Union[t.Text, datetime]) -> datetime
        try:
            try:
                date = parser.parse(str_date) if not isinstance(
                    str_date, datetime) else str_date
            except Exception:
                date = parser.parse(str_date, fuzzy=True) if not isinstance(
                    str_date, datetime) else str_date
            # if date is naive then reinforce timezone
            if date.tzinfo is None or date.tzinfo.utcoffset(date) is None:
                date = timezone('US/Eastern').localize(date)
            return date
        except Exception:
            logger.exception("failed in parsing date: %s: %s" %
                             (type(str_date), str_date))
        return None

    def _cleanup_message_data(self, message_data):

        message_data['FLAGS'] = list(message_data['FLAGS'])
        if self._imap_account.is_gmail:
            # basically treat FLAGS and GMAIL-LABELS as the same thing
            message_data['FLAGS'] += list(message_data['X-GM-LABELS'])

            # X-GM-LABELS does not include the label associated with the current
            # folder. Here we have all the known labels for gmail
            # other folders are the same as the label name
            gmail_map = {
                u'INBOX': u'\\Inbox',
                u'[Gmail]/All Mail': u'\\AllMail',
                u'[Gmail]/Drafts': u'\\Draft',
                u'[Gmail]/Important': u'\\Important',
                u'[Gmail]/Sent Mail': u'\\Sent',
                u'[Gmail]/Spam': u'\\Spam',
                u'[Gmail]/Starred': u'\\Starred',
                u'[Gmail]/Trash': u'\\Trash',
            }
            # add the label for the current folder to the flags
            if self.name in gmail_map:
                message_data['FLAGS'] += [gmail_map[self.name]]
            else:
                message_data['FLAGS'] += [self.name]

    def _save_new_messages(self, last_seen_uid, event_data_list=None, urgent=False):
        # type: (int, t.List[AbstractEventData]) -> None
        """Save any messages we haven't seen before

        Args:
            last_seen_uid (int): the max uid we have stored, should be 0 if there are no messages stored.
            urgent (bool): if True, save only one email 
        """

        # get the descriptors for the message
        descriptors = Message._get_descriptors(self._imap_account.is_gmail)

        uid_criteria = ""
        if urgent:
            uid_criteria = '%d' % (last_seen_uid + 1)
        else:
            uid_criteria = '%d:*' % (last_seen_uid + 1)

        # all the data we're iterating over
        fetch_data = self._imap_client.fetch(uid_criteria, descriptors)

        # remove the last seen uid if we can
        if last_seen_uid in fetch_data:
            del fetch_data[last_seen_uid]

        # iterate over the fetched data
        for uid in fetch_data:
            # dictionary of general data about the message
            message_data = fetch_data[uid]

            # make sure all the fields we're interested in are in the message_data
            ok = self._check_fields_in_fetch(
                ['SEQ'] + Message._get_descriptors(self._imap_account.is_gmail, True), message_data)
            if not ok:
                continue

            self._cleanup_message_data(message_data)

            # dictionary of header key value pairs
            metadata = self._parse_email_header(
                message_data[Message._header_fields_key])

            # currently have a bug with parsing
            if metadata is None:
                continue

            is_message_arrival = False
            try:
                base_message = UniqueMessageSchema.objects.get(
                    imap_account=self._imap_account, message_id=metadata['message-id'])  # type: UniqueMessageSchema
                if base_message.flags != message_data['FLAGS']:
                    base_message.flags = message_data['FLAGS']
                    base_message.save()
            except UniqueMessageSchema.DoesNotExist:
                is_message_arrival = True
                base_message = UniqueMessageSchema(
                    imap_account=self._imap_account,
                    message_id=metadata['message-id'],
                    flags=message_data['FLAGS'],
                    date=self._parse_header_date(metadata.get('date', '')),
                    subject=metadata.get('subject', ''),
                    internal_date=self._parse_header_date(
                        message_data.get('INTERNALDATE', '')),
                    from_m=self._find_or_create_contacts(metadata['from'])[
                        0] if 'from' in metadata else None,
                    _thread=None  # TODO
                )
                base_message.save()
                # create and save the message contacts
                if "in-reply-to" in metadata:
                    base_message.reply_to.add(
                        *self._find_or_create_contacts(metadata["in-reply-to"]))
                if "to" in metadata:
                    base_message.to.add(
                        *self._find_or_create_contacts(metadata["to"]))
                if "cc" in metadata:
                    base_message.cc.add(
                        *self._find_or_create_contacts(metadata["cc"]))
                if "bcc" in metadata:
                    base_message.bcc.add(
                        *self._find_or_create_contacts(metadata["bcc"]))

            new_message = MessageSchema(
                base_message=base_message,
                imap_account=self._imap_account,
                folder_schema=self._schema,
                uid=uid,
                msn=message_data['SEQ']
            )

            try:
                new_message.save()
            except Exception as e:
                logger.critical("%s failed to save message %d" % (self, uid))
                logger.critical("%s stored last_seen_uid %d, passed last_seen_uid %d" % (
                    self, self._last_seen_uid, last_seen_uid))
                logger.critical("number of messages returned %d" %
                                (len(fetch_data)))

                # to prevent dup saved email
                continue

            if event_data_list is not None:
                if is_message_arrival:
                    event_data_list.append(MessageArrivalData(
                        Message(new_message, self._imap_client)))
                    logger.info('folder {f}: uid {u}: message_arrival'.format(f=self.name, u=uid))
                else:
                    event_data_list.append(MessageMovedData(
                        Message(new_message, self._imap_client)))
                    logger.info('folder {f}: uid {u}: message_moved'.format(f=self.name, u=uid))

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
            logger.debug("%s created thread %s in database" %
                         (self, gm_thread_id))

        return thread_schema

    def _parse_email_header(self, header):
        # type: (t.Text) -> t.Dict[t.Text, t.Text]
        """Parse a potentially multiline email header into a dict of key value pairs.

        Returns:
            t.Dict[t.Text, t.Text]: Dictionary of key value pairs found in the header
        """
        # the fields that will be returned
        fields = []

        try:
            header.split('\r\n')
        except Exception:
            encoding = chardet.detect(header)['encoding']
            header = header.decode(encoding, errors='replace')
            logger.exception('failed to split header, encoding: {enc}, header:\n{h}'.format(
                enc=encoding, h=header))
            return None

        for field in header.split('\r\n'):
            # decode each part of the header
            parts = decode_header(field)
            decoded_field = u""
            for part in parts:
                text, encoding = part[0], part[1]
                if encoding:
                    if encoding != 'utf-8' and encoding != 'utf8':
                        logger.debug(
                            'parse_subject non utf8 encoding: %s' % encoding)
                    text = text.decode(encoding, errors='ignore')
                else:
                    text = unicode(text, encoding='utf8')
                decoded_field += text

            # ignore whitespace fields
            if not decoded_field:
                continue

            # if the line starts with whitespace it is part of the previous line
            if field[0] in whitespace:
                assert fields
                fields[-1] += decoded_field
            else:
                fields.append(decoded_field)
        return {k.lower(): v for (k, v) in [f.split(':', 1) for f in fields]}

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
