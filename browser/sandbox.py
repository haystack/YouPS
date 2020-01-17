from __future__ import division, unicode_literals, print_function

import copy
import datetime
import logging
import sys
import traceback
import json
import typing as t  # noqa: F401 ignore unused we use it for typing
from StringIO import StringIO

from django.utils import timezone
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing

from engine.models.calendar import MyCalendar
from engine.models.mailbox import MailBox  # noqa: F401 ignore unused we use it for typing
from engine.models.message import Message
from engine.utils import dump_execution_log
from schema.youps import MailbotMode, MessageSchema, TaskManager  # noqa: F401 ignore unused we use it for typing
from http_handler.settings import TEST_ACCOUNT_EMAIL
import sandbox_helpers
from smtp_handler.utils import send_email
logger = logging.getLogger('youps')  # type: logging.Logger

def interpret_bypass_queue(mailbox, extra_info):
    # type: (MailBox, t.Dict[t.AnyStr, t.Any]) -> None

    # assert mailbox.is_simulate or mailbox._imap_account.email == TEST_ACCOUNT_EMAIL, "if you change this then we risk committing fake info to user accounts"

    # set up the default result
    res = {'status': True, 'imap_error': False, 'imap_log': "", 'appended_log': {}}

    # create a string buffer to store stdout
    user_std_out = StringIO()
    with sandbox_helpers.override_print(user_std_out) as fakeprint:
        if mailbox.is_simulate:
            print ("Simulating: this only simulates your rule behavior and won't affect your messages")

        code = extra_info['code']
        message_schemas = MessageSchema.objects.filter(id=extra_info['msg-id'])
        
        # define the variables accessible to the user
        user_environ = sandbox_helpers.get_default_user_environment(mailbox, fakeprint)

        # Applying diff msgs to a same source code
        # TODO this code is completely broken and fires events based on function names
        for message_schema in message_schemas:
            msg_log = {"log": "", "error": False}
            logger.debug(message_schema.base_message.subject)

            # create a read-only message object to prevent changing the message
            new_message = Message(message_schema, mailbox._imap_client, is_simulate=mailbox.is_simulate)

            try:
                user_environ['new_message'] = new_message
                mailbox._imap_client.select_folder(message_schema.folder.name)

                # execute the user's code
                if "on_message" in code:
                    exec(code + "\non_message(new_message)", user_environ)    

                elif "on_flag_change" in code:
                    user_environ['new_flag'] = 'test-flag'
                    exec(code + "\non_flag_change(new_message, new_flag)", user_environ)    

                elif "on_command" in code:
                    user_environ['kargs'] = extra_info['shortcut']
                    exec(code + "\non_command(new_message, kargs)", user_environ)

                elif "on_deadline" in code:
                    exec(code + "\non_deadline(new_message)", user_environ)    

            except Exception:   
                # Get error message for users if occurs
                # print out error messages for user
                logger.exception("failure simulating user %s code" % mailbox._imap_account.email)
                msg_log["error"] = True
                fakeprint(sandbox_helpers.get_error_as_string_for_user())
            finally:
                msg_log["log"] += user_std_out.getvalue()
                logger.debug(msg_log)
                # msg_log["log"] = "%s\n%s" % (user_std_out.getvalue(), msg_log["log"])
                res['appended_log'][message_schema.id] = msg_log

                if not mailbox.is_simulate:
                    msg_log2 = print_execution_log(new_message)
                    msg_log2.update( copy.deepcopy(msg_log) )
                    logger.debug(msg_log2)
                    msg_log2["trigger"] = extra_info["rule_name"] or "untitled" if "rule_name" in extra_info else "untitled"
                    logger.debug(msg_log2)
                    log_to_dump = {msg_log2["timestamp"]: msg_log2}
                    dump_execution_log(mailbox._imap_account, log_to_dump)

                # clear current input buffer
                user_std_out.truncate(0)

    return res


def print_execution_log(message):
    new_msg = {}

    # This is to log for users
    from_field = message._get_from_friendly()

    to_field = message._get_to_friendly()

    cc_field = message._get_cc_friendly()

    new_msg["timestamp"] = str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f"))
    new_msg["type"] = "new_message"
    new_msg["from_"] = from_field
    new_msg["to"] = to_field
    new_msg["cc"] = cc_field
    new_msg["log"] = ""

    new_msg.update(message._get_meta_data_friendly())

    return new_msg


def interpret(mailbox, mode):
    """This function executes users' code.  

        Args:
            mailbox (Mailbox): user's mailbox
            mode (MailbotMode or None): current mode. if mode is null, it will bypass executing user's code and just print logs
            is_simulate (boolean): if True, it looks into extra_info to test run user's code
            extra_info (dict): it includes code, which is to be test ran, and msg-id, which is a id field of MessageSchema 

    """
    # type: (MailBox, MailbotMode, bool) -> t.Dict[t.AnyStr, t.Any]

    from schema.youps import EmailRule, MailbotMode

    # set up the default result
    res = {'status': True, 'imap_error': False, 'imap_log': ""}

    # assert we actually got a mailbox
    assert isinstance(mailbox, MailBox)
    # assert the mode is the mailboat mode
    # assert isinstance(mode, MailbotMode)
    assert mailbox.new_message_handler is not None

    def on_message_arrival(func):
        mailbox.new_message_handler += func


    # get the logger for user output
    userLogger = logging.getLogger('youps.user')  # type: logging.Logger
    # get the stream handler associated with the user output
    userLoggerStreamHandlers = filter(lambda h: isinstance(h, logging.StreamHandler), userLogger.handlers)
    userLoggerStream = userLoggerStreamHandlers[0].stream if userLoggerStreamHandlers else None
    assert userLoggerStream is not None

    # create a string buffer to store stdout
    user_std_out = StringIO()

    new_log = {}

    # execute user code
    try:
        # set the stdout to a string
        sys.stdout = user_std_out

        # set the user logger to
        userLoggerStream = user_std_out

        from schema.youps import FolderSchema

        # define the variables accessible to the user
        user_environ = {
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

        # iterate through event queue
        for event_data in mailbox.event_data_list:
            # Iterate through email rule at the current mode
            # TODO maybe use this instead of mode.rules
            if mode is None:
                continue
                
            for rule in EmailRule.objects.filter(mode=mode):
                is_fired = False
                copy_msg = {}
                copy_msg["timestamp"] = str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f"))

                assert isinstance(rule, EmailRule)

                # TODO why the reassignment of valid folders
                valid_folders = []
                
                code = rule.code

                # logger.info(code)

                # add the user's functions to the event handlers
                # basically at the end of the user's code we need to attach the user's code to
                # the event
                # user code strings can be found at http_handler/static/javascript/youps/login_imap.js ~ line 300
                # our handlers are in mailbox and the user environment
                if rule.type.startswith("new-message"):
                    valid_folders = FolderSchema.objects.filter(imap_account=mailbox._imap_account, rules=rule)
                    code = code + "\nhandle_on_message(on_message)"
                elif rule.type == "flag-change":
                    code = code + "\nhandle_on_flag_added(on_flag_added)"
                    code = code + "\nhandle_on_flag_removed(on_flag_removed)"
                elif rule.type.startswith("deadline"):
                    valid_folders = FolderSchema.objects.filter(imap_account=mailbox._imap_account).filter(is_selectable=True)
                    code = code + "\nhandle_on_deadline(on_deadline)"
                # else:
                #     continue
                #     # some_handler or something += repeat_every


                try:
                    # execute the user's code
                    # exec cant register new function (e.g., on_message_arrival) when there is a user_env
                    # logger.exception(rule.id)
                    # logger.exception(code)
                    exec(code, user_environ)


                    # TODO this should be cleaned up. accessing class name is ugly and this is very wet (Not DRY)
                    if event_data.message._schema.folder in valid_folders:
                        event_class_name = type(event_data).__name__
                        if (event_class_name == "MessageArrivalData" and rule.type =="new-message") or \
                                (event_class_name == "NewMessageDataScheduled" and rule.type.startswith("new-message-")):
                            is_fired = True
                            event_data.fire_event(mailbox.new_message_handler)                            
                        if (event_class_name == "NewFlagsData" and rule.type == "flag-change"):
                            is_fired = True
                            event_data.fire_event(mailbox.added_flag_handler)
                        if (event_class_name == "RemovedFlagsData" and rule.type == "flag-change"):
                            is_fired = True
                            event_data.fire_event(mailbox.removed_flag_handler)
                        if (event_class_name == "NewMessageDataDue" and rule.type.startswith("deadline")):
                            is_fired = True
                            event_data.fire_event(mailbox.deadline_handler)                            

                        if is_fired:
                            logger.debug("firing %s %s" % (rule.name, event_data.message.subject))

                except Exception as e:
                    # Get error message for users if occurs
                    # print out error messages for user
                    # if len(inspect.trace()) < 2:
                    #     logger.exception("System error during running user code")
                    # else:

                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    logger.exception("failure running user %s code" % mailbox._imap_account.email)
                    error_msg = str(e) + traceback.format_tb(exc_tb)[-1]
                    try:
                        send_email("failure running user %s code" % mailbox._imap_account.email, "youps.help@youps.csail.mit.edu", "youps.help@gmail.com", error_msg.decode('utf-8'), error_msg.decode('utf-8'))
                    except Exception:
                        logger.exception("Can't send error emails to admin :P")
                    copy_msg["log"] = error_msg
                    copy_msg["error"] = True
                finally:
                    if is_fired:
                        copy_msg.update(print_execution_log(event_data.message))
                        logger.debug("handling fired %s %s" % (rule.name, event_data.message.subject))
                        copy_msg["trigger"] = rule.name or (rule.type.replace("_", " ") + " untitled")

                        copy_msg["log"] = "%s\n%s" % (user_std_out.getvalue(), copy_msg["log"] if "log" in copy_msg else "")
                        
                        new_log[copy_msg["timestamp"]] = copy_msg

                    # flush buffer
                    user_std_out = StringIO()

                    # set the stdout to a string
                    sys.stdout = user_std_out

                    # set the user logger to
                    userLoggerStream = user_std_out

                mailbox.new_message_handler.removeAllHandles()
                mailbox.added_flag_handler.removeAllHandles()
                mailbox.deadline_handler.removeAllHandles()

        # Task manager
        for task in TaskManager.objects.filter(imap_account=mailbox._imap_account):
            now = timezone.now().replace(microsecond=0)
            is_fired = False
            logger.critical("%s %s" % (task.date, now))
            if task.date > now:
                continue

            new_msg = {}

            new_msg["timestamp"] = str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f"))
            new_msg["type"] = "see-later"

            copy_msg = copy.deepcopy(new_msg)
            copy_msg["timestamp"] = str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f"))

            try:
                if new_msg["type"] == "see-later":
                    user_environ = json.loads(task.email_rule.code) if len(task.email_rule.code) else {}
                    
                    msg_schema = MessageSchema.objects.get(base_message__id=user_environ["base_message_id"], folder__name=user_environ["hide_in"])
                    mailbox._imap_client.select_folder(user_environ["hide_in"])
                    msg=Message(msg_schema, mailbox._imap_client)
                    msg.move(user_environ["current_folder"])
                elif new_msg["type"] == "remind":
                    user_environ = json.loads(task.email_rule.code) if len(task.email_rule.code) else {}
                    
                    for msg_schema in task.base_message.messages.all():
                        mailbox._imap_client.select_folder(user_environ["hide_in"])
                        msg=Message(msg_schema, mailbox._imap_client)
                        msg.forward(user_environ["note"])
                        break
                else:
                    # TODO replace with Task schema and make it more extensible
                    # TODO task; id, type="hide-show", string='{}'
                    pass
                is_fired = True
            except Exception as e:
                logger.critical("Error during task managing %s " % e)
                copy_msg["error"] = True
                exc_type, exc_obj, exc_tb = sys.exc_info()
                logger.info(e)
                logger.debug(exc_obj)
                # logger.info(traceback.print_exception())

                # TODO find keyword 'in on_message' or on_flag_change
                logger.info(traceback.format_tb(exc_tb))
                logger.info(sys.exc_info())
                
                copy_msg["log"] = str(e) + traceback.format_tb(exc_tb)[-1]
                task.delete()
            finally:
                if is_fired:
                    copy_msg["trigger"] = task.email_rule.name
                    task.delete()
                        
                    # copy_msg["log"] = "%s\n%s" % (user_std_out.getvalue(), copy_msg["log"] )

                    # new_log[copy_msg["timestamp"]] = copy_msg    

                # flush buffer
                user_std_out = StringIO()

                # set the stdout to a string
                sys.stdout = user_std_out

                # set the user logger to
                userLoggerStream = user_std_out                

    except Exception as e:
        res['status'] = False
        logger.exception("failure running user %s code" % mailbox._imap_account.email)
    finally:
        # set the stdout back to what it was
        sys.stdout = sys.__stdout__
        userLoggerStream = sys.__stdout__

        # if it is simulate don't save to db
        if mailbox.is_simulate:
            logger.debug(res)

        # save logs to db
        else:
            # logger.info(new_log)
            res['imap_log'] = new_log

        user_std_out.close()
        return res
