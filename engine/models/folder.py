from __future__ import division, print_function, unicode_literals

import heapq
import logging
import typing as t  # noqa: F401 ignore unused we use it for typing
from datetime import datetime
from email.header import decode_header
from email.utils import getaddresses
from itertools import chain

import chardet
from django.db.models import Max
from imapclient import \
    IMAPClient  # noqa: F401 ignore unused we use it for typing
from imapclient.response_types import \
    Address  # noqa: F401 ignore unused we use it for typing
from pytz import timezone

from dateutil import parser
from engine.models.event_data import (AbstractEventData, MessageArrivalData,
                                      MessageMovedData, NewFlagsData,
                                      NewMessageDataDue,
                                      NewMessageDataScheduled,
                                      RemovedFlagsData)
from engine.models.message import Message
from engine.utils import normalize_msg_id, FOLDING_WS_RE, ENCODED_WORD_STRING_RE, HEADER_COMMENT_RE
from schema.youps import (  # noqa: F401 ignore unused we use it for typing
    BaseMessage, ContactSchema, ContactAlias, FolderSchema, ImapAccount,
    MessageSchema, ThreadSchema)
from engine.models.helpers import CustomProperty

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
        if isinstance(other, basestring):
            return other == self.name
        return False

    @CustomProperty
    def _uid_next(self):
        # type: () -> int
        return self._schema.uid_next

    @_uid_next.setter
    def _uid_next(self, value):
        # type: (int) -> None
        self._schema.uid_next = value
        self._schema.save()

    @CustomProperty
    def _uid_validity(self):
        # type: () -> int
        return self._schema.uid_validity

    @_uid_validity.setter
    def _uid_validity(self, value):
        # type: (int) -> None
        self._schema.uid_validity = value
        self._schema.save()

    @CustomProperty
    def _highest_mod_seq(self):
        # type: () -> int
        return self._schema.highest_mod_seq

    @_highest_mod_seq.setter
    def _highest_mod_seq(self, value):
        # type: (int) -> None
        self._schema.highest_mod_seq = value
        self._schema.save()

    @CustomProperty
    def name(self):
        # type: () -> str
        return self._schema.name

    @name.setter
    def name(self, value):
        # type: (str) -> None
        self._schema.name = value
        self._schema.save()

    @CustomProperty
    def _last_seen_uid(self):
        # type: () -> int
        return self._schema.last_seen_uid

    @_last_seen_uid.setter
    def _last_seen_uid(self, value):
        # type: (int) -> None
        self._schema.last_seen_uid = value
        self._schema.save()

    @CustomProperty
    def _is_selectable(self):
        # type: () -> bool
        return self._schema.is_selectable

    @_is_selectable.setter
    def _is_selectable(self, value):
        # type: (bool) -> None
        self._schema.is_selectable = value
        self._schema.save()

    @CustomProperty
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
        MessageSchema.objects.filter(folder=self._schema).delete()

        min_mail_id = self._get_min_mail_id()
        if min_mail_id is not None:
            self._save_new_messages(min_mail_id)

        # finally update our last seen uid (this uses the cached messages to determine last seen uid)
        self._update_last_seen_uid()
        logger.debug("%s finished completely refreshing cache" % self)

    def _update_last_seen_uid(self):
        # type () -> None
        """Updates the last seen uid to be equal to the maximum uid in this folder's cache
        """

        max_uid = MessageSchema.objects.filter(folder=self._schema).aggregate(
            Max('uid'))  # type: t.Dict[t.AnyStr, int]
        max_uid = max_uid['uid__max']
        if max_uid is None:
            max_uid = 0
        if self._last_seen_uid != max_uid:
            self._last_seen_uid = max_uid
            logger.debug('%s updated max_uid %d' % (self, max_uid))

    def _refresh_cache(self, uid_next, highest_mod_seq, event_data_list, new_message_ids):
        # type: (int, int, t.List[AbstractEventData], t.Set[str]) -> None
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
            self._save_new_messages(self._last_seen_uid, event_data_list, new_message_ids)

        # if the last seen uid is zero we haven't seen any messages
        if self._last_seen_uid != 0:
            self._update_cached_message_flags(highest_mod_seq, event_data_list)

        self._update_last_seen_uid()
        logger.debug("%s finished normal refresh" % (self))

    def _search_scheduled_message(self, event_data_list, time_start, time_end):
        message_schemas = MessageSchema.objects.filter(
            folder=self._schema).filter(date__range=[time_start, time_end])

        # Check if there are messages arrived+time_span between (email_rule.executed_at, now), then add them to the queue
        for message_schema in message_schemas:
            logger.info("add schedule %s %s %s" %
                        (time_start, message_schema.date, time_end))
            event_data_list.append(NewMessageDataScheduled(
                Message(message_schema, self._imap_client)))

    def _search_due_message(self, event_data_list, time_start, time_end):
        message_schemas = MessageSchema.objects.filter(
            folder=self._schema).filter(deadline__range=[time_start, time_end])

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

        min_mail_id = self._get_min_mail_id()

        # this can happen if we delete all the messages in a folder
        if min_mail_id == 0:
            return

        logger.debug("%s started updating flags" % self)

        # get all the flags for the old messages
        uid_criteria = '%d:%d' % (min_mail_id, self._last_seen_uid)
        descriptors = Message._get_flag_descriptors( self._imap_account.is_gmail)
        fetch_data = self._imap_client.fetch(uid_criteria, descriptors)  # type: t.Dict[int, t.Dict[str, t.Any]]

        # update flags in the cache
        for message_schema in MessageSchema.objects.filter(folder=self._schema).iterator():
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
            ok = self._check_fields_in_fetch(descriptors + ['SEQ'], message_data)
            if not ok:
                continue

            self._cleanup_message_data(message_data)

            old_flags = set(message_schema.flags)
            new_flags = set(message_data['FLAGS'])

            flags_removed = old_flags - new_flags
            flags_added = new_flags - old_flags

            if flags_removed:
                # flag removed old flag exists which does not exist in new flags
                logger.info('folder {f}: uid {u}: flags_removed {a}'.format(
                    f=self.name, u=message_schema.uid, a=flags_removed))
                event_data_list.append(RemovedFlagsData(
                    Message(message_schema, self._imap_client), list(flags_removed)))
            if flags_added:
                # flag added, new flags exists which does not exist in old flags
                logger.info('folder {f}: uid {u}: flags_added {a}'.format(
                    f=self.name, u=message_schema.uid, a=flags_added))
                event_data_list.append(NewFlagsData(
                    Message(message_schema, self._imap_client), list(flags_added)))

            if flags_added or flags_removed:
                message_schema.flags = list(new_flags)
                message_schema.save()

            if message_schema.msn != message_data['SEQ']:
                message_schema.msn = message_data['SEQ']
                message_schema.save()

        logger.debug("%s updated flags" % self)
        if highest_mod_seq is not None:
            self._highest_mod_seq = highest_mod_seq
            logger.debug("%s updated highest mod seq to %d" %
                         (self, highest_mod_seq))

    def _check_fields_in_fetch(self, fields, message_data):
        # type: (t.List[str], t.Dict[str, t.Any]) -> bool

        for field in fields:
            if field not in message_data:
                logger.critical(
                    'Missing {field} in message data'.format(field=field))
                logger.critical('Message data %s' % message_data)
                return False
        return True

    def _parse_header_date(self, str_date):
        # type: (t.Union[str, datetime]) -> datetime
        # TODO coonvert all this parsing to https://docs.python.org/2/library/email.utils.html#email.utils.parsedate_tz
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

    def _cleanup_metadata(self, metadata):
        metadata['message-id'] = normalize_msg_id(metadata['message-id'])[0]
        if metadata.has_key('in-reply-to'):
            metadata['in-reply-to'] = normalize_msg_id(metadata['in-reply-to']) 
        else:
            metadata['in-reply-to'] = []
        if metadata.has_key('references'):
            metadata['references'] = normalize_msg_id(metadata['references']) 
        else:
            metadata['references'] = []

    def _cleanup_message_data(self, message_data):
        message_data['FLAGS'] = list(message_data['FLAGS'])
        if self._imap_account.is_gmail:
            # basically treat FLAGS and GMAIL-LABELS as the same thing but don't duplicate
            combined_flags = set(message_data['FLAGS'] + list(message_data['X-GM-LABELS']))
            message_data['FLAGS'] = list(combined_flags) 

    def _save_new_messages(self, last_seen_uid, event_data_list=None, new_message_ids=None, urgent=False):
        # type: (int, t.List[AbstractEventData]) -> None
        """Save any messages we haven't seen before

        Args:
            last_seen_uid (int): the max uid we have stored, should be 0 if there are no messages stored.
            urgent (bool): if True, save only one email 
        """

        # get the descriptors for the message
        is_gmail = self._imap_account.is_gmail
        descriptors = Message._get_descriptors(is_gmail)

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
                ['SEQ'] + Message._get_descriptors(is_gmail, True), message_data)
            if not ok:
                continue

            # dictionary of header key value pairs
            metadata = self._parse_email_header(
                message_data[Message._header_fields_key])

            # TODO currently have a bug with parsing, if encoding fails we return None
            if metadata is None or metadata.get('message-id') is None:
                continue

            self._cleanup_message_data(message_data)
            self._cleanup_metadata(metadata)

            try:
                base_message = BaseMessage.objects.get(
                    imap_account=self._imap_account, message_id=metadata['message-id'])  # type: BaseMessage
            except BaseMessage.DoesNotExist:
                internal_date = self._parse_header_date(message_data.get('INTERNALDATE', ''))
                assert internal_date is not None
                date = self._parse_header_date(metadata.get('date', '')) or internal_date
                base_message = BaseMessage(
                    imap_account=self._imap_account,
                    message_id=metadata['message-id'],
                    in_reply_to=metadata['in-reply-to'],
                    references=metadata['references'],
                    date=date,
                    subject=metadata.get('subject', ''),
                    internal_date=internal_date,
                    from_m=self._find_or_create_contacts(metadata['from'])[
                        0] if 'from' in metadata else None,
                    _thread=self._find_or_create_gmail_thread(
                        message_data['X-GM-THRID']) if is_gmail else None
                )
                base_message.save()
                if new_message_ids is not None:
                    new_message_ids.add(metadata['message-id'])
                # create and save the message contacts
                if "reply-to" in metadata:
                    base_message.reply_to.add(
                        *self._find_or_create_contacts(metadata["reply-to"]))
                if "to" in metadata:
                    base_message.to.add(
                        *self._find_or_create_contacts(metadata["to"]))
                if "cc" in metadata:
                    base_message.cc.add(
                        *self._find_or_create_contacts(metadata["cc"]))
                # TODO test if bcc is working - LM (use yagmail and look at original on GMAIL)
                if "bcc" in metadata:
                    base_message.bcc.add(
                        *self._find_or_create_contacts(metadata["bcc"]))

            new_message = MessageSchema(
                base_message=base_message,
                imap_account=self._imap_account,
                flags=message_data['FLAGS'],
                folder=self._schema,
                uid=uid,
                msn=message_data['SEQ']
            )

            try:
                new_message.save()
            except Exception:
                logger.critical("%s failed to save message %d" % (self, uid))
                logger.critical("%s stored last_seen_uid %d, passed last_seen_uid %d" % (
                    self, self._last_seen_uid, last_seen_uid))
                logger.critical("number of messages returned %d" %
                                (len(fetch_data)))

                # to prevent dup saved email
                continue

            if event_data_list is not None:
                assert new_message_ids is not None
                if metadata['message-id'] in new_message_ids:
                    event_data_list.append(MessageArrivalData(
                        Message(new_message, self._imap_client)))
                    logger.info('folder {f}: uid {u}: message_arrival'.format(
                        f=self.name, u=uid))
                else:
                    event_data_list.append(MessageMovedData(
                        Message(new_message, self._imap_client)))
                    logger.info('folder {f}: uid {u}: message_moved'.format(
                        f=self.name, u=uid))

    def _find_or_create_gmail_thread(self, gm_thread_id):
        # type: (int) -> ThreadSchema
        """Return a reference to the thread schema.

        Returns:
            ThreadSchema: Thread associated with the passed in gm_thread_id

        """

        try:
            return ThreadSchema.objects.get(
                imap_account=self._imap_account, gm_thread_id=gm_thread_id)
        except ThreadSchema.DoesNotExist:
            thread_schema = ThreadSchema(
                imap_account=self._imap_account, gm_thread_id=gm_thread_id)
            thread_schema.save()
            return thread_schema

    # TODO header keys can show up more than once we should check if we support that
    def _parse_email_header(self, header):
        # type: (str) -> t.Dict[str, str]
        """Parse a potentially multiline email header into a dict of key value pairs.

        Returns:
            t.Dict[str, str]: Dictionary of key value pairs found in the header
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

        # replace instance of folding white space with nothing
        header = FOLDING_WS_RE.sub('', header)
        for field in header.split('\r\n'):
            # header can have multiple encoded parts
            # we can remove this in python3 but its a bug in python2
            parts = chain.from_iterable(decode_header(f) for f in filter(None, ENCODED_WORD_STRING_RE.split(field)))
            combined_parts = u""
            for part in parts:
                text, encoding = part[0], part[1]
                if encoding:
                    text = text.decode(encoding, errors='ignore')
                    if encoding != 'utf-8' and encoding != 'utf8':
                        logger.debug(
                            'parse_subject non utf8 encoding: %s' % encoding)
                        # TODO not sure if we want everything in utf8 we need some native speakers to test this
                        # text = text.encode('utf8')
                else:
                    text = unicode(text, encoding='utf8')
                combined_parts += text

            # ignore whitespace fields
            if not combined_parts:
                continue

            fields.append(combined_parts)
        fields = {k.lower().strip(): v.strip() for (k, v) in [f.split(':', 1) for f in fields]}
        
        # TODO move this somewhere else
        # remove comments from message ids, check rfc5322 when 
        # adding fields to determine if comments need to be removed
        for k in fields:
            # these fields contain message ids
            if k not in ['message-id', 'in-reply-to', 'references']:
                continue
            v = fields[k]
            # nested comments cannot be queried with regex
            # this hack removes them from the inside out
            while HEADER_COMMENT_RE.search(v):
                v = HEADER_COMMENT_RE.sub('', v)
            fields[k] = v
        return fields

    def _find_or_create_contacts(self, addresses):
        # type: (t.List[Address]) -> t.List[ContactSchema]
        """Convert a list of addresses into a list of contact schemas.

        Returns:
            t.List[ContactSchema]: List of contacts associated with the addresses
        """
        assert addresses is not None
        contact_schemas = []

        for address in getaddresses([addresses]):
            name, email = address
            # this can happen when i send emails to myself - LM not sure why
            if not email or "@" not in email:
                continue
            contact_schema = None  # type: ContactSchema

            try:
                contact_schema = ContactSchema.objects.prefetch_related(
                    'aliases').get(imap_account=self._imap_account, email=email)
            except ContactSchema.DoesNotExist:
                contact_schema = ContactSchema(
                    imap_account=self._imap_account, email=email)
                contact_schema.save()
                logger.debug("created contact %s in database" % email)

            if name:
                try:
                    alias = contact_schema.aliases.get(name=name)
                    alias.count += 1
                    alias.save()
                except ContactAlias.DoesNotExist:
                    alias = ContactAlias(contact=contact_schema, imap_account=self._imap_account, name=name, count=1)
                    alias.save()
                    logger.debug("created contact alias %s in database" % name)

            contact_schemas.append(contact_schema)
        return contact_schemas
