# Store utilities for use in the engine for some future where the engine
# can potentially exist by itself
import logging
import re
import typing as t  # noqa: F401 ignore unused we use it for typing
from itertools import izip, tee
import json 
import requests
from schema.youps import LogSchema
from datetime import (datetime,  # noqa: F401 ignore unused we use it for typing
                      timedelta)
from django.utils import timezone
from pytz import timezone as tz
from http_handler.settings import NYLAS_ID

if t.TYPE_CHECKING:
    from engine.models.message import Message
    from engine.models.folder import Folder
    from schema.youps import ImapAccount, MessageSchema, FolderSchema, BaseMessage  # noqa: F401 ignore unused we use it for typing
    from imapclient import IMAPClient

logger = logging.getLogger('youps')  # type: logging.Logger

class YoupsException(Exception):
    """Base Exception for custom YoupsExceptions
    """
    def __init__(self, *args, **kwargs):
        super(YoupsException, self).__init__(*args, **kwargs)

class IsNotGmailException(YoupsException):
    """Exception for code which only works for gmail accounts
    """
    def __init__(self):
        # Call super constructor
        super(IsNotGmailException, self).__init__(
            'This code only works on gmail accounts')


class InvalidFlagException(YoupsException):
    """Exception for when the user passes an invalid flag
    """

    def __init__(self, *args, **kwargs):
        default_message = 'Could not set imap flags'
        if not (args or kwargs):
            args = (default_message,)
        # Call super constructor
        super(InvalidFlagException, self).__init__(*args, **kwargs)

def auth_to_nylas(imapAccount):
    if imapAccount.nylas_access_token:
        return imapAccount.nylas_access_token

    response_body = None
    if "csail" in imapAccount.host:
        response_body = {
            "client_id": NYLAS_ID,
            "email_address": imapAccount.email,
            "name": imapAccount.email.split("@")[0],
            "provider": "imap",
            "settings":      {
                "imap_host":     "imap.csail.mit.edu",
                "imap_port":     993,
                "imap_username": imapAccount.email.split("@")[0],
                "imap_password": imapAccount.password,
                "smtp_host":     "outgoing.csail.mit.edu",
                "smtp_port":     587,
                "smtp_username": imapAccount.email.split("@")[0],
                "smtp_password": imapAccount.password,
                "ssl_required":  True
            },
            "scopes": "email,calendar,contacts"
        }

    elif "exchange" in imapAccount.host:
        response_body = {
        	"client_id": NYLAS_ID,
            "email_address": imapAccount.email,
            "name": imapAccount.email.split("@")[0],
            "provider":      "exchange",
            "settings": {
        		"username": imapAccount.email.split("@")[0],
        		"password": imapAccount.password,
        		"eas_server_host": "owa.exchange.mit.edu",
        	},
            "scopes": "email,calendar,contacts"
        }

    else:
        response_body = {
            "client_id": NYLAS_ID,
            "email_address": imapAccount.email,
            "name": imapAccount.email.split("@")[0],
            "provider": "imap",
            "settings":      {
                "imap_host":     imapAccount.host,
                "imap_port":     993,
                "imap_username": imapAccount.email,
                "imap_password": imapAccount.password,
                "smtp_host":     imapAccount.host.replace("imap", "smtp"),
                "smtp_port":     587,
                "smtp_username": imapAccount.email,
                "smtp_password": imapAccount.password,
                "ssl_required":  True
            },
            "scopes": "email,calendar,contacts"
        }

    nylas_authorize_resp = requests.post(
        "https://api.nylas.com/connect/authorize", json=response_body
    )

    if not nylas_authorize_resp.ok:
        message = nylas_authorize_resp.json()["message"]
        logger.exception(message)
        raise Exception("You need to log in to add-on in order to use this function. Log in here: https://youps.csail.mit.edu/%s" % "settings")

    nylas_code = nylas_authorize_resp.json()["code"]
    imapAccount.nylas_access_token = nylas_code
    imapAccount.save()

    return nylas_code



def get_datetime_from_now(later_at):
    if not isinstance(later_at, datetime) and not isinstance(later_at, (int, long, float)):
        raise TypeError("see_later(): later_at " +
            later_at + " is not number or datetime")

    if isinstance(later_at, (int, long, float)):
        later_at = timezone.now().replace(microsecond=0) + \
            timedelta(seconds=later_at*60)

    return convertToUserTZ(later_at)

def convertToUserTZ(datetime_obj, tz=tz('US/Eastern')):
    if not isinstance(datetime_obj, datetime):
        return None
    # If timezone is not provided aka naive
    elif datetime_obj.tzinfo is None or datetime_obj.tzinfo.utcoffset(datetime_obj) is None:
        datetime_obj = tz.localize(datetime_obj)
        datetime_obj = timezone.localtime(datetime_obj)
        logger.info(datetime_obj)

    # when there is time zone
    else:
        datetime_obj= datetime_obj.astimezone(tz)

    return datetime_obj

def prettyPrintTimezone(datetime_obj, tz=tz('US/Eastern')):
    datetime_obj= convertToUserTZ(datetime_obj, tz)

    return datetime_obj.strftime("%m/%d %H:%M") if datetime_obj else ""
    
def print_execution_log(message):
    new_msg = {}

    # This is to log for users
    from_field = message._get_from_friendly()

    to_field = message._get_to_friendly()

    cc_field = message._get_cc_friendly()

    new_msg["timestamp"] = str(datetime.now().strftime("%m/%d %H:%M:%S,%f"))
    new_msg["type"] = "new_message"
    new_msg["from_"] = from_field
    new_msg["to"] = to_field
    new_msg["cc"] = cc_field
    new_msg["log"] = ""

    new_msg.update(message._get_meta_data_friendly())

    return new_msg

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
    # type: (str) -> t.List[str]
    """Converts a string into a list of all the message ids contained within it.

    This method will try to make message ids standardized. So that they can be
    compared with one another. They may have to be destandardized to be used as 
    headers in emails. 
    Returns:
        str: standard message_id for comparison with other message ids
    """
    # clean up empty strings
    message_ids = MESSAGE_ID_SPLIT_RE.findall(message_id)

    # TODO better sanity checking from rfc5322
    # sanity check
    for message_id in message_ids:
        assert '@' in message_id
        assert not any(s in message_id for s in ['>', '"', '<'])
    return message_ids


def strip_wrapping_quotes(string):
    if string[0] == '"' and string[-1] == '"':
        return string[1:-1]
    return string


def message_from_message_id(msg_id, imap_account, folder, imap_client):
    # type: (str, ImapAccount, Folder, IMAPClient) -> Message
    """Check to see if a message exists with the passed in msg_id

    Args:
        msg_id (str): message id
        imap_account (ImapAccount): imap account

    Returns:
        bool: true if the message exists in the database
    """
    from engine.models.message import Message
    from schema.youps import ImapAccount, MessageSchema, BaseMessage

    try:
        base_message = BaseMessage.objects.get(
            message_id=msg_id, imap_account=imap_account)
        message_schema = MessageSchema.objects.get(
            folder=folder._schema, imap_account=imap_account, base_message=base_message)
    except (BaseMessage.DoesNotExist, MessageSchema.DoesNotExist):
        return None
    return Message(message_schema, imap_client)


def references_algorithm(start_msg):
    # type: (Message) -> t.List[Message]
    from anytree import Node, LoopError, PreOrderIter

    # find references
    #    # first try message ids in the references header line
    #    # if that fails use the first valid messageid in the in-reply-to header line as the only valid parent
    #    # if the reply to doesn't work then there are no references
    references = start_msg.references or start_msg.in_reply_to[:1]

    # determine if a message is a reply or a forward
    #    #  A message is considered to be a reply or forward if the base
    #    #  subject extraction rules, applied to the original subject,
    #    #  remove any of the following: a subj-refwd, a "(fwd)" subj-
    #    #  trailer, or a subj-fwd-hdr and subj-fwd-trl

    #    # see https://tools.ietf.org/html/rfc5256#section-2.1 for base subject extraction
    #    # see https://tools.ietf.org/html/rfc5256#section-5 for def of abnf

    # PART 1 A from https://tools.ietf.org/html/rfc5256 REFERENCES
    # using the message ids in the messages references link corresponding messages
    # first is parent of second, second is parent of third, etc...
    # make sure there are no loops
    # if a message already has a parent don't change the existing link
    # if no message exists with the reference then create a dummy message
    # TODO not sure how to check valid message ids

    # nodes which don't have parents
    orphan_nodes = set()  # type: t.Set[Node]
    current = None
    # Map of msg ids to Nodes
    node_map = {}  # type: t.Dict[str, Node]
    for msg_id in references:
        node = node_map.get(msg_id, Node(msg_id))
        node_map[msg_id] = node
        # if we are in a child and the child does not already have a parent
        # try to add the node
        if current is not None and node.parent is None:
            try:
                node.parent = current
            except LoopError:
                current = None
        # otherwise the node is a new orphan
        if current is None:
            current = node
            orphan_nodes.append(current)

    # nodes which are not in our database
    msg_map = {node_map[msg_id]: message_from_message_id(
        msg_id, start_msg._imap_account, start_msg.folder, start_msg._imap_client) for msg_id in references}  # t.Dict[Node, t.Optional[Message]]
    dummy_nodes = {node for node, msg in msg_map.iteritems()
                   if msg is None}  # t.Set[Node]

    # PART 1 B
    # create a parent child link between the last reference and the current message.
    # if the current message already has a parent break the current parent child link unless this would create a loop
    node = node_map.get(start_msg._message_id, Node(
        start_msg._message_id))  # type: Node
    node_map[start_msg._message_id] = node
    try:
        node.parent = current
    except LoopError:
        pass

    # PART 2
    # make any messages without parents children of a dummy root
    root = Node('root')  # type: Node
    for orphan in orphan_nodes:
        orphan.parent = root

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
    for node in list(PreOrderIter(root)):
        if node not in dummy_nodes:
            continue
        dummy_node = node
        # if there are no children
        if not dummy_node.children:
            dummy_node.parent = None
        # promote children but only promote at most one child to the root
        elif dummy_node.parent != root or len(dummy_node.children) == 1:
            for child in dummy_node.children:
                child.parent = dummy_node.parent

    # PART 4
    # Sort the messages under the root (top-level siblings only)
    # by sent date as described in section 2.2.  In the case of a
    # dummy message, sort its children by sent date and then use
    # the first child for the top-level sort.
    def sortkey(node):
        if node not in dummy_nodes:
            return msg_map[node].date
        node.children = sorted(node.children, key=sortkey)
        # assumes we have no dummies in the middle of the tree
        return min(msg_map[n].date for n in node.children)

    root.children = sorted(root.children, key=sortkey)
    assert isinstance(root.children, list)

    # TODO PART 5 and PART 6 RFC 5256

def dump_execution_log(imapAccount, new_log, action_log):
    '''
        Args:
            imapAccount
            new_log: a dictinary where the key is timestamp of each log
            action_log: a list that contains all the actions. This will be used by the undo feature
    '''
    from django.core.serializers.json import DjangoJSONEncoder
    if new_log != {}:
        l = LogSchema(imap_account=imapAccount, content=json.dumps(new_log,cls=DjangoJSONEncoder), action=json.dumps(action_log,cls=DjangoJSONEncoder))
        l.save()
        logger.info(new_log)

def turn_on_youps(imapAccount, turn_on, verbose):
    if turn_on:
        logger.info("Turning on account %s / %s" % (imapAccount.email, verbose))
    else:
        logger.info("Turning OFF account %s / %s " % (imapAccount.email, verbose))

    imapAccount.is_running = turn_on 
    imapAccount.save()

# REGEXES
# Match carriage return new lines followed by whitespace. For example "\r\n   \t\t"
# this is used to indicate multi line fields in email headers
FOLDING_WS_RE = re.compile(r'\r\n[\ \t]+')    


# Match encoded-word strings in the form =?charset?q?Hello_World?=
# this is used to indicate encoding in email headers
# the regex used in python2 decode_header is incorrect, this is from the
# python3 version and can be removed when/if the project moves to python3
ENCODED_WORD_STRING_RE = re.compile(r'(=\?[^?]*?\?[qQbB]\?.*?\?=)', re.VERBOSE | re.MULTILINE)

# basically find Parentheses containing text surrounded by optional white space
# TODO might have to rewrite with RFC5322
HEADER_COMMENT_RE = re.compile(r'\((?:(?:[\ \t]*\r\n){0,1}[\ \t]*[\x01-\x08\x0B\x0C\x0E-\x1F\x21-\x27\x2A-\x5B\x5D-\x7F]|\\[\x01-\x09\x0B\x0C\x0E-\x7F])*(?:[\ \t]*\r\n){0,1}[\ \t]*\)')


MESSAGE_ID_SPLIT_RE = re.compile(r'<(.*?)>')

ATTACHMENTS_RE = re.compile(r'(?<="name"\s").+?(?=")')
