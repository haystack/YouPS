"""Contains a parser for rfc2822 headers.
"""
import logging
from decode_header_patch import decode_header
from email.utils import parsedate_tz, mktime_tz
from email._parseaddr import AddressList
from datetime import datetime
from regexes import CFWS, COMMENT
import re

from django.utils import timezone
import pytz

re_cfws = re.compile(CFWS)
re_comment = re.compile(COMMENT)


log = logging.getLogger('parser')
debug = log.debug
info = log.info
error = log.error


def _make_date_tz_aware(date):
    # type: (datetime.datetime) -> datetime.datetime
    if date is not None:
        if date.tzinfo is None or date.tzinfo.utcoffset(date) is None:
            date = pytz.timezone('US/Eastern').localize(date)
            date = timezone.localtime(date)
    return date


def _strip_ws_and_comments(val):
    while re_cfws.findall(val):
        val = re_cfws.sub('', val)
    while re_comment.findall(val):
        val = re_comment.sub('', val)
    return val


def _header_to_unicode(val):
    val = decode_header(val)
    return ''.join([v.decode(enc if enc is not None else 'utf8',
                             errors='replace') for v, enc in val])


def _parse_address_list(addresses):
    address_list = AddressList(addresses).addresslist
    # if len(address) > 1:
    #     raise Exception('failure to parse from address')
    for i, addr in enumerate(address_list):
        address_list[i] = tuple(_header_to_unicode(v) for v in addr)
    return address_list


def _parse_single_address(address_str, field=''):
    addresses = _parse_address_list(address_str)
    # raise an error if necessary
    if len(addresses) > 1:
        error("to many addresses %s: %s || %s", field, addresses, address_str)
    # replace empty list with empty tuple
    address = addresses[0] if addresses else ('', '')
    return address


def header_parse_from(from_):
    # type: (str) -> tuple(str, str)
    from_ = _strip_ws_and_comments(from_)
    return _parse_address_list(from_)


def header_parse_cc(cc):
    # parse the addresses
    cc = _strip_ws_and_comments(cc)
    return _parse_address_list(cc)


def header_parse_bcc(bcc):
    bcc = _strip_ws_and_comments(bcc)
    return _parse_address_list(bcc)


def header_parse_to(to):
    to = _strip_ws_and_comments(to)
    return _parse_address_list(to)


def header_parse_references(references):
    references = _strip_ws_and_comments(references)
    references = [a[1] for a in _parse_address_list(references)]
    return references


def header_parse_in_reply_to(in_reply_to):
    in_reply_to = _strip_ws_and_comments(in_reply_to)
    in_reply_to = [a[1] for a in _parse_address_list(in_reply_to)]
    return in_reply_to


def header_parse_date(date):
    date = parsedate_tz(date)
    if date is not None:
        date = datetime.fromtimestamp(mktime_tz(date))
        date = _make_date_tz_aware(date)
    return date


def header_parse_reply_to(reply_to):
    return _parse_address_list(reply_to)


def header_parse_message_id(message_id):
    message_id = _strip_ws_and_comments(message_id)
    message_id = [a[1] for a in _parse_address_list(message_id)]
    return message_id[0] if message_id else None


def header_parse_subject(subject):
    return _header_to_unicode(subject)
