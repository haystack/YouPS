from __future__ import division, print_function, unicode_literals

import typing as t  # noqa: F401 ignore unused we use it for typing

from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing

from schema.youps import MessageSchema, ThreadSchema  # noqa: F401 ignore unused we use it for typing

from engine.models.message import Message

class Thread(object):

    def __init__(self, thread_schema, imap_client):
        # type: (ThreadSchema, IMAPClient) -> Thread 

        self._schema = thread_schema  # type: ThreadSchema 

        # the connection to the server
        self._imap_client = imap_client  # type: IMAPClient


    def __str__(self):
        return "Thread %d" % self._schema.id


    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, Thread):
            return self._schema == other._schema
        return False

    @property
    def messages(self):
        # type: () -> t.List[Message]
        """Get the messages associated with the thread

        Returns:
            t.List[Message]: Get all the messages in the thread
        """
        return [Message(m, self._imap_client) for m in self._schema.messages.all()]