# coding: utf-8
from __future__ import print_function
from contextlib import contextmanager
import __builtin__
import typing as t
from engine.models.calendar import MyCalendar
import traceback
import logging 
if t.TYPE_CHECKING:
    from engine.models.mailbox import Mailbox

logger = logging.getLogger('youps')  # type: logging.Logger


def handle_interpret_error(mailbox, output):
    # type: (Mailbox, t.Dict) -> None
    logger.exception("failure simulating user %s code" % mailbox._imap_account.email)
    output["error"] = True

    # show just the error type
    error_messages = traceback.format_exc().splitlines()
    print(error_messages[-1])

    # show the whole tracebook
    # exc_type, exc_value, exc_traceback = sys.exc_info()
    # for line in traceback.format_tb(exc_traceback):
    #     print(line)

    # show the line number and some file stufff
    # print(traceback.format_tb(exc_traceback))

def get_default_user_environment(mailbox):
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
    }


@contextmanager
def override_print(output):
    #  type: (t.TextIO) -> t.Generator[None, None, None]
    """Temporarily override builtin print to go to output object

    If this isn't working make sure that from __future__ import print_function
    is at the top of every file that you are printing in

    Usage:
        output = StringIO() 
        with override_print(output):
            print("this will go to standard out")
    
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
    __builtin__.print = fake_print
    try:
        yield
    finally:
        __builtin__.print = original_print
