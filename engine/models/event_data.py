from __future__ import unicode_literals, print_function, division
from abc import ABCMeta, abstractmethod
from event import Event  # noqa: F401 ignore unused we use it for typing
import typing as t  # noqa: F401 ignore unused we use it for typing
from engine.models.message import Message  # noqa: F401 ignore unused we use it for typing


class AbstractEventData(object):
    _metaclass_ = ABCMeta

    @abstractmethod
    def __init__(self, message):
        # type: (Message) -> AbstractEventData
        self.message = message  # type: Message 

    @abstractmethod
    def fire_event(self, event):
        # type : (Event) -> None
        """Takes in the appropriate event for the EventData object and fires it
        """
        pass

class MessageMovedData(AbstractEventData):
    def __init__(self, message):
        # type: (Message) -> MessageMovedData 
        super(MessageMovedData, self).__init__(message)

    def fire_event(self, event):
        # type : (Event) -> None
        self.message._imap_client.select_folder(
            self.message._schema.folder.name)
        event.fire(self.message)

class MessageArrivalData(AbstractEventData):
    def __init__(self, message):
        # type: (Message) -> MessageArrivalData
        super(MessageArrivalData, self).__init__(message)

    def fire_event(self, event):
        # type : (Event) -> None
        self.message._imap_client.select_folder(
            self.message._schema.folder.name)
        event.fire(self.message)

class NewMessageDataScheduled(MessageArrivalData):
    def __init__(self, message):
        # type: (Message) -> NewMessageDataScheduled
        super(NewMessageDataScheduled, self).__init__(message)

    def fire_event(self, event):
        # type : (Event) -> None
        super(NewMessageDataScheduled, self).fire_event(event)

class NewMessageDataDue(MessageArrivalData):
    def __init__(self, message):
        # type: (Message) -> NewMessageDataDue
        super(NewMessageDataDue, self).__init__(message)

    def fire_event(self, event):
        # type : (Event) -> None
        super(NewMessageDataDue, self).fire_event(event)

class NewFlagsData(AbstractEventData):
    def __init__(self, message, flags):
        # type: (Message, t.List[str]) -> NewFlagsData
        super(NewFlagsData, self).__init__(message)
        self.flags = flags  # type t.List[str]

    def fire_event(self, event):
        # type : (Event) -> None
        self.message._imap_client.select_folder(
            self.message._schema.folder.name)
        event.fire(self.message, self.flags)

class RemovedFlagsData(NewFlagsData):
    def __init__(self, message, flags):
        # type: (Message, t.List[str]) -> RemovedFlagsData
        super(RemovedFlagsData, self).__init__(message, flags)

    def fire_event(self, event):
        # type : (Event) -> None
        super(RemovedFlagsData, self).fire_event(event)
        
# class SeeLaterData(AbstractEventData):