from __future__ import division, print_function, unicode_literals

import typing as t  # noqa: F401 ignore unused we use it for typing

from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing

from schema.youps import MessageSchema, ThreadSchema, FolderSchema  # noqa: F401 ignore unused we use it for typing

from engine.models.message import Message

from itertools import chain, ifilter

import logging 

logger = logging.getLogger('youps')  # type: logging.Logger

class Thread(object):

    def __init__(self, thread_schema, imap_client, is_simulate=False, folder_schema=None):
        # type: (ThreadSchema, IMAPClient, t.Optional[bool], t.Optional[FolderSchema]) -> Thread

        self._schema = thread_schema  # type: ThreadSchema

        self._folder_schema = folder_schema  # type: t.Optional[FolderSchema]

        # the connection to the server
        self._imap_client = imap_client  # type: IMAPClient

        self._is_simulate = is_simulate


    # TODO ideally we would have a __str__ method for printing thread which
    # outputs the subject but the subject can have unicode in it which 
    # screws things up since __str__ has to return bytes
    # def __str__(self):
    #     return "Thread: %s" % self._schema.baseMessages.order_by('date').first().subject


    def __repr__(self):
        return "Thread object %d" % self._schema.id

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, Thread):
            return self._schema == other._schema
        return False

    def __len__(self):
        return self._schema.baseMessages.all().count()

    @property
    def messages(self):
        # type: () -> t.List[Message]
        """Get the messages associated with the thread

        Returns:
            t.List[Message]: Get all the messages in the thread
        """
        return list(m for m in self)

    def __iter__(self):
        # type: () -> t.Iterator[Message]
        """Iterate over the messages in the thread ordered by date ascending

        Returns:
            t.Iterator[Message]: iterator of the messages in the thread in ascending order
        """
        base_messages = self._schema.baseMessages.all().order_by('date').iterator()
        messages = chain.from_iterable(m.messages.all().iterator() for m in base_messages)
        filter_messages_by_folder = ifilter(lambda m: m.folder == self._folder_schema if self._folder_schema is not None else True, messages)
        return iter((Message(m, self._imap_client, self._is_simulate) for m in filter_messages_by_folder))
