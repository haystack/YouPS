# Store utilities for use in the engine for some future where the engine
# can potentially exist by itself
import logging
import typing as t  # noqa: F401 ignore unused we use it for typing
from itertools import izip

from imapclient import \
    IMAPClient  # noqa: F401 ignore unused we use it for typing

if t.TYPE_CHECKING:
    from engine.models.message import Message


logger = logging.getLogger('youps')  # type: logging.Logger


def grouper(iterable, n):
    """Group data from an iterable into chunks of size n

    The last chunk can be of size 1 to n

    Args:
        iterable (t.Iterable): iterable object
        n (int): chunk size

    Returns:
        t.Iterable: iterable containing n elements
    """
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return izip(*args)


def is_gmail_label(possible_label):
    # type: (str) -> bool
    """Check if a label is a known gmail label 

    Note: this only works on gmail accounts

    Returns:
        bool: true if the label is a gmail label
    """

    known_labels = {u'\\Inbox', u'\\AllMail', u'\\Draft',
                    u'\\Important', u'\\Sent', u'\\Spam', u'\\Starred', u'\\Trash'}
    return possible_label in known_labels
    # TODO if we want to recognize user labels as well requires imapclient
    # # gmail labels are folders which don't start with [Gmail]
    # all_labels = {f[2] for f in imap_client.list_folders()
    #               if not f[2].startswith('[Gmail]') and f[2] != 'INBOX'}
    # return possible_label in all_labels


def is_imap_flag(possible_flag):
    # type: (str) -> bool
    """Check if a flag is a known imap flag 

    Returns:
        bool: true if the label is an imap flag 
    """
    known_flags = {"\\Seen", "\\Answered", "\\Flagged",
                   "\\Deleted", "\\Draft", "\\Recent"}
    return possible_flag in known_flags


def normalize_msg_id(message_id):
    # type: (str) -> str
    """Return a standard message_id which can be compared consistently with other message ids.

    Message ids can contain optional double quotes and are often surrounded by <>.
    These double quotes should not be used in string comparison and the brackets 
    have no semantic meaning. This method removes both if they exist.

    Returns:
        str: standard message_id for comparison with other message ids
    """

    message_id = message_id.strip()
    # strip angle brackets
    if message_id[0] == '<' and message_id[-1] == '>':
        message_id = message_id[1:-1]
    # strip quotes
    if '"' in message_id:
        message_id = ''.join((strip_wrapping_quotes(s)
                              for s in message_id.split('@', 1)))

    # TODO add somet method to check that the message id is valid        
    return message_id


def strip_wrapping_quotes(string):
    if string[0] == '"' and string[-1] == '"':
        return string[1:-1]
    return string


def references_algorithm(start_msg):
    # type: (Message) -> t.List[Message]

    # glossary
    # FWS = \r\n followed by 1 or more whitespace characters
    # comments can occur which are delimited with parentheses
    # fields we are interested in
    #   in-reply-to: one or more message ids
    #   references: one or more message ids
    #   message-id: one or more message ids
    #   the part of a message id before the @ sign can contain quotes
    #       these quotes should be stripped

    pass
