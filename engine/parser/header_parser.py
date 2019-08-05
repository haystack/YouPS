"""A parser for email headers."""

from __future__ import print_function
import sqlite3
import cPickle as pickle
import six
import sys
import email

import typing as t

import logging

import datetime

from rfc2822_parser import (header_parse_bcc, header_parse_cc,
                            header_parse_date, header_parse_from,
                            header_parse_in_reply_to, header_parse_message_id,
                            header_parse_references, header_parse_reply_to,
                            header_parse_subject, header_parse_to)


logger = logging.getLogger('youps')  # type: logging.Logger

HEADER_KEY = 'BODY[HEADER.FIELDS (DATE MESSAGE-ID SUBJECT FROM TO CC BCC REPLY-TO IN-REPLY-TO REFERENCES)]'


def parse_internal_date(internal_date):
    # type: (datetime.datetime) -> datetime.datetime
    return internal_date


def parse_flags(flags):
    # type: (t.Tuple[str]) -> t.List[str]
    return list(flags)


def parse_seq(seq):
    # type: (int) -> int
    return seq


def parse_gm_labels(labels):
    # type: (t.Tuple[str]) -> t.List[str]
    return list(labels)


def parse_gm_thrid(thrid):
    # type: (int) -> int
    return thrid


def parse_headers(headers):
    msg = email.message_from_string(headers)
    header_parsers = {
        'from': header_parse_from,
        'cc': header_parse_cc,
        'bcc': header_parse_bcc,
        'to': header_parse_to,
        'references': header_parse_references,
        'in-reply-to': header_parse_in_reply_to,
        'date': header_parse_date,
        'reply-to': header_parse_reply_to,
        'message-id': header_parse_message_id,
        'subject': header_parse_subject,
    }

    output = {}

    for key in msg.keys():
        key = key.lower()
        # if key missing you need to write a new parser
        try:
            output[key] = header_parsers[key](msg[key])
        except KeyError:
            logger.exception('implement a header_parser for key %s', key)
            raise

    return output


def parse_msg_data(msg_data):
    # type: (t.Dict[str, t.Any]) -> None

    parsers = {
        'INTERNALDATE': parse_internal_date,
        'FLAGS': parse_flags,
        'SEQ': parse_seq,
        'X-GM-LABELS': parse_gm_labels,
        'X-GM-THRID': parse_gm_thrid,
        HEADER_KEY: parse_headers
    }

    output = {}

    for key in msg_data:
        try:
            output[key] = parsers[key](msg_data[key])
        except KeyError:
            logger.exception('implement parser for key %s', key)
            raise

    return output


def parse_sqlite_row(row):
    logger.debug('%s::%s::%s', row['email'], row['folder'], row['uid'])
    msg_data = pickle.loads(six.ensure_str(row['data']))
    return parse_msg_data(msg_data)


def main():
    conn = sqlite3.connect('./message_data.db')
    try:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM data')
        import pprint
        pprint.pprint([parse_sqlite_row(r) for r in c], indent=2, width=120)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
