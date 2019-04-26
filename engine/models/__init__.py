# # this was creating circular import errors
# from folder import Folder
# from contact import Contact
# from message import Message
# from event_data import (MessageArrivalData, NewMessageDataScheduled, NewMessageDataDue,
#                         AbstractEventData, NewFlagsData, RemovedFlagsData, MessageMovedData)
# from thread import Thread
# from mailbox import Mailbox
# __all__ = ["Mailbox", "Thread", "Contact", "Folder", "Message",
#            "MessageArrivalData", "NewMessageDataScheduled",
#            "NewMessageDataDue", "AbstractEventData", "NewFlagsData",
#            "RemovedFlagsData", "MessageMovedData"
#            ]
