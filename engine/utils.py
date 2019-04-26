# Store utilities for use in the engine for some future where the engine
# can potentially exist by itself
from itertools import izip
import typing as t  # noqa: F401 ignore unused we use it for typing
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing


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
    # type (t.Text) -> bool
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
    # type (t.Text) -> bool
    """Check if a flag is a known imap flag 

    Returns:
        bool: true if the label is an imap flag 
    """
    known_flags = { "\\Seen", "\\Answered", "\\Flagged", "\\Deleted", "\\Draft", "\\Recent"  }
    return possible_flag in known_flags
