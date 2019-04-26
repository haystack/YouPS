# Store utilities for use in the engine for some future where the engine
# can potentially exist by itself
import logging
import typing as t  # noqa: F401 ignore unused we use it for typing
from itertools import izip, tee

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

def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(iterable)
    next(b, None)
    return izip(a, b)


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

    # sanity check
    assert '@' in message_id
    assert not any(s in message_id for s in ['>', '"', '<'])
    return message_id


def strip_wrapping_quotes(string):
    if string[0] == '"' and string[-1] == '"':
        return string[1:-1]
    return string


def message_exists(msg_id):
    """Check to see if a message exists with the passed in msg_id
    
    Args:
        msg_id (str): message id
    
    Returns:
        bool: true if the message exists in the database
    """
    from schema.youps import BaseMessage
    return BaseMessage.objects.filter(message_id=msg_id).exists()



def references_algorithm(start_msg):
    # type: (Message) -> t.List[Message]
    from anytree import Node, LoopError

    # glossary
    # FWS = \r\n followed by 1 or more whitespace characters
    # comments can occur which are delimited with parentheses
    # fields we are interested in
    #   in-reply-to: one or more message ids
    #   references: one or more message ids
    #   message-id: one or more message ids
    #   the part of a message id before the @ sign can contain quotes
    #       these quotes should be stripped

    # find references
    #    # first try message ids in the references header line
    #    #   if that fails use the first valid messageid in the in-reply-to header line as the only valid parent
    #    #   if the reply to doesn't work then there are no references
    references = start_msg.references or start_msg.in_reply_to[:1]
    


    # determine if a message is a reply or a forward
    #    #  A message is considered to be a reply or forward if the base
    #    #  subject extraction rules, applied to the original subject,
    #    #  remove any of the following: a subj-refwd, a "(fwd)" subj-
    #    #  trailer, or a subj-fwd-hdr and subj-fwd-trl

    #    # see https://tools.ietf.org/html/rfc5256#section-2.1 for base subject extraction
    #    # see https://tools.ietf.org/html/rfc5256#section-5 for def of abnf


    # PART 1
    # using the message ids in the messages references link corresponding messages
    # first is parent of second, second is parent of third, etc...
    # make sure there are no loops
    # if a message already has a parent don't change the existing link
    # if no message exists with the reference then create a dummy message

    # Part 1 a from https://tools.ietf.org/html/rfc5256#section-5
    # TODO not sure how to check valid message ids
    roots = []
    current = None 
    node_map = {}
    for msg_id in references:
        node = node_map.get(msg_id, Node(msg_id))
        if current is not None and node.parent is None:
            try:
                node.parent = current
            except LoopError:
                current = node 
                roots.append(current)
        else:
            current = node 
            roots.append(current)

    dummy_nodes = filter(lambda msg_id: not message_exists(msg_id), set(references))


    # PART 1 B
    # create a parent child link between the last references and the current message.
    # if the current message already has a parent break the current parent child link unless this would create a loop
    # 
    current = Node(start_msg._message_id, parent=current)

    # PART 2
    # make any messages without parents children of a dummy root

    
    # PART 3
    # prune dummy messages from the tree
    #    # If it is a dummy message with NO children, delete it.
    #    #
    #    # If it is a dummy message with children, delete it, but
    #    # promote its children to the current level.  In other
    #    # words, splice them in with the dummy's siblings.
    #    #
    #    # Do not promote the children if doing so would make them
    #    # children of the root, unless there is only one child.
    #    #
    #    # Sort the messages under the root (top-level siblings only)
    #    # by sent date as described in section 2.2.  In the case of a
    #    # dummy message, sort its children by sent date and then use
    #    # the first child for the top-level sort. 

    pass
