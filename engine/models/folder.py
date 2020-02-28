from __future__ import division, print_function, unicode_literals

import heapq
import logging
import typing as t  # noqa: F401 ignore unused we use it for typing
import json
from datetime import datetime
from email.header import decode_header
from email.utils import getaddresses
from itertools import chain
from engine.parser.header_parser import parse_msg_data, parse_flags

from django.db.models import Max
from django.core.serializers.json import DjangoJSONEncoder
from imapclient import \
    IMAPClient  # noqa: F401 ignore unused we use it for typing
from imapclient.response_types import \
    Address  # noqa: F401 ignore unused we use it for typing

from engine.models.event_data import (AbstractEventData, ThreadArrivalData, MessageArrivalData, 
                                      MessageMovedData, NewFlagsData, ContactArrivalData,
                                      NewMessageDataScheduled,
                                      RemovedFlagsData)
from engine.models.message import Message
from schema.youps import (  # noqa: F401 ignore unused we use it for typing
    BaseMessage, ContactSchema, ContactAlias, EventManager, FolderSchema, ImapAccount,
    MessageSchema, ThreadSchema)
from engine.models.helpers import CustomProperty
from engine.utils import auth_to_nylas

from http_handler.settings import NYLAS_ID, NYLAS_SECRET
from nylas import APIClient
from duckling import Duckling

logger = logging.getLogger('youps')  # type: logging.Logger


class Folder(object):

    def __init__(self, folder_schema, imap_client):
        # type: (FolderSchema, IMAPClient) -> Folder

        self._schema = folder_schema  # type: FolderSchema

        # the connection to the server
        self._imap_client = imap_client  # type: IMAPClient

        self.time_entity_extractor = None

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
    
    def messages(self):
        # type: () -> t.List[Message]
        """Get the messages associated with the folder

        Returns:
            t.List[Message]: Get all the messages in the folder
        """

        if self.name.lower() == "inbox":
            raise Exception("messages(): not allowed to use it for your default folder to prevent overload")
        
        return list(Message(m, self._imap_client) for m in MessageSchema.objects.filter(folder=self._schema))

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

    def _get_time_entity_extractor(self):
        if self.time_entity_extractor is None:
            logger.exception("loading extractor")
            self.time_entity_extractor = Duckling()
            self.time_entity_extractor.load()
        
        return self.time_entity_extractor

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
            if self._last_seen_uid != 0:
                logger.info("Update flags information")
                self._update_cached_message_flags(highest_mod_seq, event_data_list)

        # if the last seen uid is zero we haven't seen any messages
        # if self._last_seen_uid != 0:
        #     self._update_cached_message_flags(highest_mod_seq, event_data_list)

        self._update_last_seen_uid()
        logger.debug("%s finished normal refresh" % (self))

    def _refresh_flag_changes(self, highest_mod_seq):
        # type: (int) -> t.List[MessageSchema]
        query_fields = ['FLAGS']
        if self._imap_account.is_gmail:
            query_fields = query_fields + ['X-GM-THRID', 'X-GM-LABELS']

        messages_with_flag_changes = []
        # for old messages check flags and determine if any messages were deleted
        # but only if we have to
        if highest_mod_seq is None:
            query_fields = ['FLAGS']
            if self._imap_account.is_gmail:
                query_fields = query_fields + ['X-GM-LABELS']
            chunk = 100
            curr_uid = 1
            
            for i in range(curr_uid, self._schema.last_seen_uid + 1, chunk):
                end_range = min(self._schema.last_seen_uid, i + chunk)
                messages = {m.uid: m for m in MessageSchema.objects.filter(folder=self._schema, uid__range=[i, end_range])}
                # logger.info(messages.keys())
                res = self._imap_client.fetch("{}:{}".format(i, end_range), query_fields)
                for uid in messages:
                    for key, attribute in ((b'FLAGS', 'flags'), (b'X-GM-LABELS', 'gm_labels')):
                        if key in res[uid] and uid in messages:
                            cached_flags = set(getattr(messages[uid], attribute, []))
                            server_flags = set(parse_flags(res[uid][key]))
                            deleted_flags = cached_flags - server_flags
                            new_flags = server_flags - cached_flags
                            if cached_flags != server_flags:
                                messages_with_flag_changes.append(messages[uid])
                            # if deleted_flags or new_flags:
                            #     logger.info('detect flags %s: deleted %s. new %s',
                            #                 messages[uid], deleted_flags, new_flags)

                            #     messages_with_flag_changes.append(messages[uid])

            return messages_with_flag_changes


        # here we can use condstore to be faster
        elif self._schema.highest_mod_seq < highest_mod_seq:
            query_fields = ['FLAGS']
            if self._imap_account.is_gmail:
                query_fields = query_fields + ['X-GM-LABELS']
            # only fetch messages changed since our cached highest_mod_seq
            logger.debug("modseq %d " % self._schema.highest_mod_seq)
            res = self._imap_client.fetch("1:*", query_fields, ['CHANGEDSINCE {}'.format(self._schema.highest_mod_seq)])
            messages = {m.uid: m for m in MessageSchema.objects.filter(folder=self._schema, uid__in=res.keys()).all()}
            if self._imap_account.email== "soya@csail.mit.edu":
                logger.exception(messages)
            # for each message compare the flags
            for uid in res:
                for key, attribute in ((b'FLAGS', 'flags'), (b'X-GM-LABELS', 'gm_labels')):
                    if (key in res[uid]) and (uid in messages):
                        # TODO this line broke when the message is not saved in db due to errors e.g., encoding issue
                        cached_flags = set(getattr(messages[uid], attribute, []))
                        server_flags = set(parse_flags(res[uid][key]))
                        deleted_flags = cached_flags - server_flags
                        new_flags = server_flags - cached_flags
                        if deleted_flags or new_flags:
                            logger.debug('detect flags %s: deleted %s. new %s',
                                        messages[uid], deleted_flags, new_flags)

                            messages_with_flag_changes.append(messages[uid])
            return messages_with_flag_changes

        return []

    def _search_scheduled_message(self, event_data_list, time_start, time_end):
        message_schemas = MessageSchema.objects.filter(
            folder=self._schema).filter(base_message__date__range=[time_start, time_end])

        # Check if there are messages arrived+time_span between (email_rule.executed_at, now),
        # then add them to the queue
        for message_schema in message_schemas:
            logger.info("add schedule %s %s %s" %
                        (time_start, message_schema.base_message.date, time_end))
            event_data_list.append(NewMessageDataScheduled(
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
        descriptors = Message._get_flag_descriptors(self._imap_account.is_gmail)
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
            message_data = parse_msg_data(message_data)

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
                         (self, self._highest_mod_seq))

    def _check_fields_in_fetch(self, fields, message_data):
        # type: (t.List[str], t.Dict[str, t.Any]) -> bool

        for field in fields:
            if field not in message_data:
                logger.critical(
                    'Missing {field} in message data'.format(field=field))
                logger.critical('Message data %s' % message_data)
                return False
        return True

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
            urgent (bool): if True, save only one email. This is used to save a message and bypass syncing loop.
                e.g. when users try to manipulate this message but when it is not registered yet
        """

        # get the descriptors for the message
        is_gmail = self._imap_account.is_gmail
        descriptors = Message._get_descriptors(is_gmail)

        uid_criteria = ""
        if urgent:
            uid_criteria = '%d' % last_seen_uid
        else:
            uid_criteria = '%d:*' % (last_seen_uid + 1)
        if self._imap_account.email == "karger@mit.edu" and self.name=="INBOX.Archives.Topics.ISAT - Innovation":
            logger.info('karger folder {f}: message_arrival skip '.format(
                f=self.name))
            return
        
        # all the data we're iterating over
        fetch_data = self._imap_client.fetch(uid_criteria, descriptors)

        # remove the last seen uid if we can
        if last_seen_uid in fetch_data:
            del fetch_data[last_seen_uid]

        if self._imap_account.email == "karger@mit.edu":
            logger.info('karger folder {f}: message_arrival'.format(
                f=self.name))

        # iterate over the fetched data
        for uid in fetch_data:
            if self._imap_account.email == "karger@mit.edu":
                logger.info("karger {u}".format(u=uid))
            
            # dictionary of general data about the message
            message_data = fetch_data[uid]

            # make sure all the fields we're interested in are in the message_data
            ok = self._check_fields_in_fetch(
                ['SEQ'] + Message._get_descriptors(is_gmail, True), message_data)
            if not ok:
                continue
            if self._imap_account.email == "karger@mit.edu":
                logger.info("karger {u}".format(u=uid))

            self._cleanup_message_data(message_data)
            message_data = parse_msg_data(message_data)
            metadata = message_data[Message._header_fields_key]

            # TODO currently have a bug with parsing, if encoding fails we return None
            if metadata.get('message-id') is None:
                logger.critical("%s::%s::%s missing message-id", self._imap_account.email, self.name, uid)
                continue

            try:
                base_message = BaseMessage.objects.get(
                    imap_account=self._imap_account, message_id=metadata['message-id'])  # type: BaseMessage
            except BaseMessage.DoesNotExist:
                internal_date = message_data.get('INTERNALDATE', '')
                assert internal_date is not None
                date = metadata.get('date', '') or internal_date
                from_ = self._find_or_create_contacts(metadata.get('from', []))
                
                base_message = BaseMessage(
                    imap_account=self._imap_account,
                    message_id=metadata['message-id'],
                    in_reply_to=metadata.get('in-reply-to', []),
                    references=metadata.get('references', []),
                    date=date,
                    subject=metadata.get('subject', ''),
                    internal_date=internal_date,
                    from_m=from_[0] if from_ else None,
                    _thread=None  # self._find_or_create_gmail_thread(message_data['X-GM-THRID']) if is_gmail else
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

            # during normal sync, not initialization
            if event_data_list is not None:
                assert new_message_ids is not None
                if metadata['message-id'] in new_message_ids:
                    m = Message(new_message, self._imap_client)
                    te = self._get_time_entity_extractor()
                    t = m.extract_response()
                    t = m.subject +" "+ t
                    time_entities = te.parse(t, reference_time=str(base_message.date))

                    a = []
                    values = []

                    for e in time_entities:
                        try: 
                            if e["dim"] not in ["time", "interval"]: # extract url?
                                continue
                            if "grain" in e["value"] and (e["value"]["grain"] in ["year", "month"]):
                                continue
                            
                            if "body" in e and e["body"].lower().strip() in ["now", "spring", "summer", "fall", "winter"]:
                                continue

                            if "body" in e and len(e["body"]) >= 3 and e['value'] not in values:
                                logger.debug(e)
                                body = t[max(e["start"]-20, 0):min(e["end"]+20, len(t))].replace(e["body"], "*%s*" % e["body"]).replace("\n", " ")
                                start = end = ""

                                if len(e["value"]["values"]) > 0:
                                    if "type" in e["value"]["values"][0] and e["value"]["values"][0]["type"] == "interval":
                                        start = e["value"]["values"][0]["from"]["value"]
                                        end = e["value"]["values"][0]["to"]["value"]
                                    else:
                                        start = e["value"]["values"][0]["value"]

                                        logger.info(e["value"]["values"][0]["value"])
                                else:
                                    if "from" in e["value"]:
                                        start = e["value"]["from"]["value"]
                                        logger.info(e["value"]["from"]["value"])

                                    else:
                                        end = e["value"]["to"]["value"]
                                        logger.info(e["value"]["to"]["value"])

                                if start or end:
                                    # if the extracted date is too old or too far future, jump
                                    if start:
                                        # parse start
                                        # e.g., 1980-01-01T00:00:00.000Z
                                        start = start.split(".")[0]
                                        start = datetime.strptime(start, '%Y-%m-%dT%H:%M:%S')
                                        if start.year < datetime.today().year or start.year > (datetime.today().year +1):
                                            continue

                                    if end:
                                        end = end.split(".")[0]
                                        end = datetime.strptime(end, '%Y-%m-%dT%H:%M:%S')
                                        if end.year < datetime.today().year or end.year > (datetime.today().year +1):
                                            continue
                                    
                                    a.append({"body": ".. %s .." % body, "start": start, "end": end}) # TODO only take duration of event start, end, m
                                    values.append(e['value'])
                        except Exception as e:
                            logger.exception(str(e))    
                        
                    logger.info(a)
                    base_message.extracted_time = json.dumps(a,cls=DjangoJSONEncoder)
                    base_message.save()

                    # Check thread arrival event
                    if self._imap_account.nylas_access_token:
                        nylas = APIClient(
                            NYLAS_ID,
                            NYLAS_SECRET,
                            self._imap_account.nylas_access_token
                        )
                        # find thread in nylas        
                        if m._get_nylas_message():
                            logger.debug("Find Nylas msg for the new msg")
                            nylas_thread = nylas.threads.get(m._get_nylas_message().thread_id)
                            if nylas_thread:
                                logger.debug(nylas_thread.id)
                                thread_schema = ThreadSchema.objects.filter(nylas_id=nylas_thread.id)
                                if thread_schema.exists(): 
                                    base_message._thread = thread_schema[0]
                                    base_message.save()
                                    # add events to event_data_list
                                    event_data_list.append(ThreadArrivalData(
                                        m))
                                    logger.info('folder {f}: uid {u}: thread arrival'.format(
                                        f=self.name, u=uid))

                    # Check message arrived from a contact event
                    if base_message.from_m:
                        events = EventManager.objects.filter(contact=base_message.from_m)
                        if events.exists():
                            event_data_list.append(ContactArrivalData(
                                Message(new_message, self._imap_client)))

                            logger.info('folder {f}: uid {u}: contact arrival'.format(
                                f=self.name, u=uid))

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

    def _find_or_create_contacts(self, addresses):
        # type: (t.List[Address]) -> t.List[ContactSchema]
        """Convert a list of addresses into a list of contact schemas.

        Returns:
            t.List[ContactSchema]: List of contacts associated with the addresses
        """
        assert addresses is not None
        contact_schemas = []

        for address in addresses:
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
