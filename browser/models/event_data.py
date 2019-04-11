from __future__ import unicode_literals, print_function, division
from abc import ABCMeta, abstractmethod
from event import Event  # noqa: F401 ignore unused we use it for typing
import typing as t  # noqa: F401 ignore unused we use it for typing
from browser.models.message import Message  # noqa: F401 ignore unused we use it for typing
from schema.youps import MessageSchema


class AbstractEventData(object):
    _metaclass_ = ABCMeta

    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def fire_event(self, event):
        # type : (Event) -> None
        """Takes in the appropriate event for the EventData object and fires it
        """
        pass


class NewMessageData(AbstractEventData):
    def __init__(self, message_id, imap_client):
        # type: (Message) -> NewMessageData
        super(NewMessageData, self).__init__()
        self.message_id = message_id  # type: int 
        self.imap_client = imap_client

    def fire_event(self, event):
        # type : (Event) -> None
        message = Message(MessageSchema.objects.get(id=self.message_id), self.imap_client)
        message._imap_client.select_folder(
            message._schema.folder_schema.name)
        event.fire(message)

class NewMessageDataScheduled(NewMessageData):
    def __init__(self, message):
        # type: (Message) -> NewMessageDataScheduled
        super(NewMessageDataScheduled, self).__init__(message)
        self.message = message  # type: Message

    def fire_event(self, event):
        # type : (Event) -> None
        super(NewMessageDataScheduled, self).fire_event(event)
    

