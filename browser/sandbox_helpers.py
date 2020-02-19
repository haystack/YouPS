# coding: utf-8
from __future__ import print_function
from contextlib import contextmanager
import __builtin__
import typing as t
from engine.models.calendar import MyCalendar
import traceback
import logging 
if t.TYPE_CHECKING:
    from engine.models.mailbox import Mailbox  # noqa: F401 ignore unused we use it for typing

logger = logging.getLogger('youps')  # type: logging.Logger


def get_error_as_string_for_user():
    # type: () -> t.AnyStr
    """Call this to get a string representation of an error for the user
    
    Returns:
        t.AnyStr: a string representing an error message
    """
    # see this for other options https://docs.python.org/2.7/library/traceback.html
    # show just the error type
    error_messages = traceback.format_exc().splitlines()
    return error_messages[-1]

def get_default_user_environment(mailbox, fakeprint):
    return {
        'create_draft': mailbox.create_draft,
        'create_folder': mailbox.create_folder,
        'get_email_mode': mailbox.get_email_mode,
        'set_email_mode': mailbox.set_email_mode,
        'send': mailbox.send,
        'handle_on_message': lambda f: mailbox.new_message_handler.handle(f),
        'handle_on_flag_added': lambda f: mailbox.added_flag_handler.handle(f),
        'handle_on_flag_removed': lambda f: mailbox.removed_flag_handler.handle(f),
        'handle_on_deadline': lambda f: mailbox.deadline_handler.handle(f),
        'Calendar': MyCalendar,
        'print': fakeprint # TODO potentially get rid of this and use userlogger
    }


@contextmanager
def override_print(output):
    #  type: (t.TextIO) -> t.Generator[None, None, None]
    """Safely create a new version of print that prints to the passed in output

    If this isn't working make sure that from __future__ import print_function
    is at the top of every file that you are printing in

    Usage:
        output = StringIO() 
        with override_print(output):
            print("this will go to StringIO")
    
    Args:
        output (t.TextIO): Object that can be written to like a file
    
    Returns:
        t.Generator[None, None, None]: should be used in a with statement
    """
    original_print = __builtin__.print

    def fake_print(*args, **kwargs):
        if 'file' not in kwargs:
            kwargs['file'] = output
        return original_print(*args, **kwargs)
    # __builtin__.print = fake_print
    try:
        yield fake_print
    finally:
        __builtin__.print = original_print
