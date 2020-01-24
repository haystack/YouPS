import email
import logging
import pprint
import typing as t
from collections import Sequence, namedtuple
from contextlib import contextmanager
from itertools import izip

from engine.utils import InvalidFlagException, is_gmail_label

if t.TYPE_CHECKING:
    from engine.models.message import Message


logger = logging.getLogger('youps')  # type: logging.Logger


@contextmanager
def _open_rfc822(message):
    #  type: (Message) -> t.Generator[email.message.Message, None, None]
    """convert a Message into a python email.message.Message.

    Usage:
        with open_rfc822(message) as rfc_contents:

    Raises:
        RuntimeError: if the fetched content doesn't have the correct uid
        RuntimeError: if the fetched content is missing the RFC822

    Returns:
        email.message.Message: python email message representation
    """

    # check if the message is initially read
    initially_unread = message.is_unread
    try:
        response = message._imap_client.fetch(
            message._uid, ['RFC822'])  # type: t.Dict[t.AnyStr, t.Any]
        if message._uid not in response:
            raise RuntimeError('Failed to get message content')
        response = response[message._uid]

        # get the rfc data we're looking for
        if 'RFC822' not in response:
            logger.critical('%s:%s response: %s' %
                            (message.folder, message, pprint.pformat(response)))
            logger.critical("%s did not return RFC822" % message)
            raise RuntimeError("Failed to get message content")
        rfc_contents = email.message_from_string(
            response.get('RFC822'))  # type: email.message.Message
        yield rfc_contents
    finally:
        # if the message was read mark it as unread
        if initially_unread:
            logger.critical("INITIALLLY UNREAD")
            # TODO see remove_flags_gmail, marking unread doesn't actually work
            message.mark_unread()


def _get_text_from_python_message(part):
    # type: (email.message.Message) -> t.Optional[t.AnyStr]

    # don't even try to convert non text parts
    main_type = part.get_content_maintype()
    if main_type != "text":
        return None

    # get the charset used to encode the message
    charset = part.get_content_charset()

    # return decoded text if possible otherwise fall back to non
    # decoded text otherwise fail
    if charset is not None:
        return unicode(part.get_payload(decode=True), charset, "ignore")
    else:
        try:
            return unicode(part.get_payload(decode=True))
        except Exception:
            raise RuntimeError("failed to convert message to etext")


# TODO refactor this to do some kind of visitor pattern or something
# make things open to extension but closed for modification
def get_content_from_message(message, return_only_text=False):
    # type: (Message) -> None
    with _open_rfc822(message) as rfc_contents:
        text = ""
        html = ""
        extra = {}

        # walk the message
        for part in rfc_contents.walk():
            # TODO respect multipart/[alternative, mixed] etc... see RFC1341
            if part.is_multipart():
                continue

            # for each part get the maintype and subtype
            sub_type = part.get_content_subtype()

            text_contents = _get_text_from_python_message(part)

            # extract plain text
            if text_contents is not None:
                text += text_contents if sub_type == "plain" else ""
                html += text_contents if sub_type == "html" else ""
            # extract calendar
            elif sub_type == "calendar":
                if sub_type not in extra:
                    extra[sub_type] = ""
                extra[sub_type] += text_contents
            # fail otherwise
            else:
                logger.critical(
                    "%s unsupported sub type %s" % (message, sub_type))
                # raise NotImplementedError(
                #     "Unsupported sub type %s" % sub_type)

        # I think this is less confusing than returning an empty string - LM
        text = text if text else None
        html = html if html else None
        # return text if we have it otherwise html
        # return text if text else html
        if return_only_text:
            return text
        else:
            extra['text'] = text
            extra['html'] = html

            return extra

def _flag_change_helper(message, uids, flags, gmail_label_func, imap_flag_func):
    # type: (Message, t.List[int], t.List[str], t.Callable[[t.List[int], t.List[str]]])
    import pprint
    flags = _check_flags(message, flags)
    if message._imap_account.is_gmail:
        # gmail_labels = filter(is_gmail_label, flags)
        # returned_labels = gmail_label_func(uids, gmail_labels)
        # logger.debug("flag change returned labels {flags}".format(
        #     flags=pprint.pformat(returned_labels)))
        
        # Wouldn't Gmail users would want to use gmail labels which is visible in their interface?
        not_gmail_labels = filter(lambda f: not is_gmail_label(f), flags)
        logger.exception(not_gmail_labels)
        returned_flags = gmail_label_func(uids, not_gmail_labels)
        logger.exception("flag change returned flags {flags}".format(
            flags=pprint.pformat(returned_flags)))
    else:
        returned_flags = imap_flag_func(uids, flags)
        logger.debug("flag change returned flags {flags}".format(
            flags=pprint.pformat(returned_flags)))

def _check_flags(message, flags):
    # type: (Message, t.Iterable[t.AnyStr]) -> t.Iterable[t.AnyStr]
    """Check user defined flags

    Raises:
        InvalidFlagException: The flags are invalid

    Returns:
        t.List[t.AnyStr]: the valid flags as a list
    """

    # allow user to pass in a string
    if isinstance(flags, basestring):
        flags = [flags]
    elif not isinstance(flags, Sequence):
        raise InvalidFlagException(
            "flags must be a sequence or a a string")

    if not isinstance(flags, list):
        flags = list(flags)

    # make sure all flags are strings
    for flag in flags:
        if not isinstance(flag, basestring):
            raise InvalidFlagException("each flag must be string")
    # remove extraneous white space
    flags = [flag.strip() for flag in flags]
    # remove empty strings
    flags = [flag for flag in flags if flag]
    if not flags:
        raise InvalidFlagException(
            "No valid flags. Check if flags are empty strings")
    return flags


def _save_flags(message, flags):
    # type: (Message, t.List[t.AnyStr]) -> None
    """Save new flags to the database

    removed the setter from flags since it was too dangerous.
    """
    if not message._is_simulate:
        message._schema.flags = flags
        message._schema.save()

    message._flags = flags


# TODO test this attachment parsing stuff somoe more and make it more legible

Part = namedtuple('Part', ['maintype', 'subtype', 'parameters', 'id_',
                  'description', 'encoding', 'size']
                  )

def _walk_bodystructure(part):
    yield part
    if part.is_multipart:
        for sub_part in part[0]:
            for p in _walk_bodystructure(sub_part):
                yield p

def _pairwise(iterable):
    "s -> (s0, s1), (s2, s3), (s4, s5), ..."
    a = iter(iterable)
    return izip(a, a)

def _parse_part(part):
    # type: (t.Tuple) -> Part
    assert not part.is_multipart
    part = list(part)
    parameter_dict = {k: v for k, v in _pairwise(list(part[2]))}
    part[2] = parameter_dict
    parsed_part = Part(*(list(part)[:7]))
    return parsed_part

def get_attachments(message):
    import pprint
    response = message._imap_client.fetch(message._uid, ['BODYSTRUCTURE'])
    if message._uid not in response:
        raise RuntimeError('Failed to get message content')
    response = response[message._uid]

    # get the rfc data we're looking for
    if 'BODYSTRUCTURE' not in response:
        logger.critical('%s:%s response: %s' %
                        (message.folder, message, pprint.pformat(response)))
        logger.critical("%s did not return BODYSTRUCTURE" % message)
        raise RuntimeError("Failed to get message attachment names")
    bodystructure = response['BODYSTRUCTURE']

    parts = [_parse_part(p) for p in _walk_bodystructure(bodystructure) if not p.is_multipart]
    file_names = []
    for part in parts:
        if 'NAME' in part.parameters:
            file_names.append(part.parameters['NAME'])
    return file_names
