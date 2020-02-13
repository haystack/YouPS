from __future__ import division, unicode_literals, print_function

import copy
import datetime
import logging
import sys
import traceback
import json
import typing as t  # noqa: F401 ignore unused we use it for typing
from StringIO import StringIO

from django.db.models import Q
from django.utils import timezone
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing

from engine.models.calendar import MyCalendar
from engine.models.mailbox import MailBox  # noqa: F401 ignore unused we use it for typing
from engine.models.message import Message
from engine.models.contact import Contact
from engine.utils import dump_execution_log, prettyPrintTimezone, print_execution_log
from schema.youps import MailbotMode, MessageSchema, EventManager  # noqa: F401 ignore unused we use it for typing
from http_handler.settings import TEST_ACCOUNT_EMAIL
import sandbox_helpers
from smtp_handler.utils import send_email, codeobject_loads

logger = logging.getLogger('youps')  # type: logging.Logger

def interpret_bypass_queue(mailbox, extra_info):
    # type: (MailBox, t.Dict[t.AnyStr, t.Any]) -> None
    """This function execute the given code

        Args:
            mailbox (Mailbox): user's mailbox
            extra_info (dict): it includes code, which is to be test ran, and msg-id, which is a id field of MessageSchema 

    """

    # assert mailbox.is_simulate or mailbox._imap_account.email == TEST_ACCOUNT_EMAIL, "if you change this then we risk committing fake info to user accounts"

    # set up the default result
    res = {'status': True, 'imap_error': False, 'imap_log': "", 'appended_log': {}}

    # get the logger for user output
    userLogger = logging.getLogger('youps.user')  # type: logging.Logger
    # get the stream handler associated with the user output
    userLoggerStreamHandlers = filter(lambda h: isinstance(h, logging.StreamHandler), userLogger.handlers)
    userLoggerStream = userLoggerStreamHandlers[0].stream if userLoggerStreamHandlers else None
    assert userLoggerStream is not None

    # create a string buffer to store stdout
    user_std_out = StringIO()
    user_property_log = []

    try:
        # set the stdout to a string
        stdout_original = sys.stdout
        sys.stdout = user_std_out

        # set the user logger to
        userLoggerStream = user_std_out

        if mailbox.is_simulate:
            print ("Simulating: this only simulates your rule behavior and won't affect your messages")

        code = extra_info['code']
        message_schemas = MessageSchema.objects.filter(id=extra_info['msg-id'])
        logger.info(message_schemas)
        # define the variables accessible to the user
        user_environ = sandbox_helpers.get_default_user_environment(mailbox, print)

        # Applying diff msgs to a same source code
        # TODO this code is completely broken and fires events based on function names
        for message_schema in message_schemas:
            msg_log = {"log": "", "property_log": [], "error": False}
            logger.debug(message_schema.base_message.subject)

            # create a read-only message object to prevent changing the message
            new_message = Message(message_schema, mailbox._imap_client, is_simulate=mailbox.is_simulate)

            try:
                user_environ['new_message'] = new_message
                mailbox._imap_client.select_folder(message_schema.folder.name)

                # clear the property log at the last possible moment
                user_property_log = []
                mailbox._imap_client.user_property_log = user_property_log
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
                print(sandbox_helpers.get_error_as_string_for_user())
            finally:
                msg_log["log"] += user_std_out.getvalue()
                msg_log["property_log"].extend(user_property_log)
                logger.info(msg_log)
                # msg_log["log"] = "%s\n%s" % (user_std_out.getvalue(), msg_log["log"])
                res['appended_log'][message_schema.id] = msg_log

                if not mailbox.is_simulate:
                    msg_log2 = print_execution_log(new_message)
                    msg_log2.update( copy.deepcopy(msg_log) )
                    logger.debug(msg_log2)
                    msg_log2["trigger"] = extra_info["rule_name"] or "untitled" if "rule_name" in extra_info else "untitled"
                    logger.debug(msg_log2)
                    dump_execution_log(mailbox._imap_account, {msg_log2["timestamp"]: msg_log2}, msg_log["property_log"])

                # flush buffer
                user_std_out = StringIO()

                # set the stdout to a string
                sys.stdout = user_std_out

                # set the user logger to
                userLoggerStream = user_std_out
    except Exception:
        logger.exception("test")
    finally: 
        sys.stdout = stdout_original


    return res


def interpret(mailbox, mode):
    """This function executes users' code.  

        Args:
            mailbox (Mailbox): user's mailbox
            mode (MailbotMode or None): current mode. if mode is null, it will bypass executing user's code and just print logs

    """
    # type: (MailBox, MailbotMode, bool) -> t.Dict[t.AnyStr, t.Any]

    from schema.youps import EmailRule, MailbotMode

    # set up the default result
    res = {'status': True, 'imap_error': False, 'imap_log': "", 'property_log': []}

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
        user_environ = sandbox_helpers.get_default_user_environment(mailbox, print)

        # iterate through event queue
        for event_data in mailbox.event_data_list:
            # Iterate through email rule at the current mode
            # TODO maybe use this instead of mode.rules
            if mode is None:
                continue

            copy_msg = {}

            user_property_log = []
            mailbox._imap_client.user_property_log = user_property_log

            event_class_name = type(event_data).__name__

            '''
                Event handle: add to each handler if it should be executed
            '''  
            rule_type_to_search = ""
            handler = call_back= None
            email_rules = []
            try:
                if event_class_name == "ThreadArrivalData":
                    rule_type_to_search = call_back = "on_response"
                    handler = mailbox.new_message_handler
                    
                    email_rules = [e.email_rule for e in EventManager.objects.filter(thread=event_data.message._schema.base_message._thread, email_rule__type__startswith=rule_type_to_search)]
                elif event_class_name ==  "ContactArrivalData":
                    rule_type_to_search = call_back = "on_response"
                    handler = mailbox.new_message_handler
                    
                    email_rules = [e.email_rule for e in EventManager.objects.filter(contact=event_data.message._schema.base_message.from_m, email_rule__type__startswith=rule_type_to_search)]
                elif event_class_name == "MessageArrivalData":
                    rule_type_to_search = "new-message"
                    handler = mailbox.new_message_handler
                    call_back = "on_message"              
                    email_rules = EmailRule.objects.filter(mode=mode, type__startswith=rule_type_to_search)
                    logger.exception(mode.id)
                    logger.exception(email_rules.values())
                elif event_class_name == "NewFlagsData":
                    rule_type_to_search = "flag-change"
                    handler = mailbox.added_flag_handler
                    call_back = "on_flag_change"
                    email_rules = EmailRule.objects.filter(mode=mode, type__startswith=rule_type_to_search)
                elif event_class_name == "NewMessageDataDue":
                    rule_type_to_search= "deadline"
                    handler = mailbox.deadline_handler
                    call_back = "on_deadline"
                    email_rules = EmailRule.objects.filter(mode=mode, type__startswith=rule_type_to_search)
                elif event_class_name == "MessageMovedData":
                    continue

                logger.exception("here")
                if handler is None:
                    continue

                for rule in email_rules:
                    code = rule.code
                    if event_class_name in ["ThreadArrivalData", "ContactArrivalData"]:
                        code = codeobject_loads(json.loads(code))
                        code = type(codeobject_loads)(code, user_environ)

                        logger.exception(mailbox.new_message_handler.getHandlerCount())
                        handler.handle(code)

                        logger.exception(mailbox.new_message_handler.getHandlerCount())
                    else:
                        valid_folders = FolderSchema.objects.filter(imap_account=mailbox._imap_account, rules=rule)
                        logger.info(valid_folders)
                        for v in valid_folders:
                            logger.exception(v.name)
                        if not event_class_name == "MessageArrivalData" or event_data.message._schema.folder in valid_folders:
                            exec(code + "\nhandler.handle(%s)" % call_back, user_environ.update({'handler': handler}))
                            # handler.handle(code)

                
                event_data.fire_event(handler)
            except Exception as e:
                # Get error message for users if occurs
                # print out error messages for user
                # if len(inspect.trace()) < 2:
                #     logger.exception("System error during running user code")

                exc_type, exc_obj, exc_tb = sys.exc_info()
                logger.exception(sys.exc_info())
                logger.exception("failure running user %s code" % mailbox._imap_account.email)
                error_msg = str(e) + traceback.format_tb(exc_tb)[-1]
                try:
                    send_email("failure running user %s code" % mailbox._imap_account.email, "youps.help@youps.csail.mit.edu", "youps.help@gmail.com", error_msg.decode('utf-8'), error_msg.decode('utf-8'))
                except Exception:
                    logger.exception("Can't send error emails to admin :P")
                copy_msg["log"] = error_msg
                copy_msg["error"] = True     

            if handler and handler.getHandlerCount():
                copy_msg.update(print_execution_log(event_data.message))
                logger.debug("handling fired %s %s" % (rule.name, event_data.message.subject))
                copy_msg["trigger"] = rule.name or (rule.type.replace("_", " ") + " untitled")

                copy_msg["log"] = "%s\n%s" % (user_std_out.getvalue(), copy_msg["log"] if "log" in copy_msg else "")
                            
                dump_execution_log(mailbox._imap_account, {copy_msg["timestamp"]: copy_msg}, mailbox._imap_client.user_property_log)

            # flush buffer
            user_std_out = StringIO()

            # set the stdout to a string
            sys.stdout = user_std_out

            # set the user logger to
            userLoggerStream = user_std_out

            mailbox.new_message_handler.removeAllHandles()
            mailbox.added_flag_handler.removeAllHandles()
            mailbox.deadline_handler.removeAllHandles()

        '''
            Task manager: Dynamic event handler. Could be triggered by a definite time or events 
            my_message.on_response(f)
            my_message.on_time(time, f)
            # TODO create event data list for this too 
        '''
        now = timezone.now()
        for task in EventManager.objects.filter(date__lte=now).order_by('date'): #(imap_account=mailbox._imap_account): # TODO filter by timestamp has passed and either thread, message or contact belongs to this imap account
            # check membership first
            logger.info("task detected")
            skip = True
            if (task.base_message and task.base_message.imap_account == mailbox._imap_account) or \
                (task.thread and task.thread.imap_account == mailbox._imap_account) or \
                (task.contact and task.contact.imap_account == mailbox._imap_account):
                skip = False
            logger.info("task detected")
            if skip:
                continue
            logger.info("task detected")
            # TODO user logger
            user_std_out = StringIO()

             # set the stdout to a string
            sys.stdout = user_std_out

            # set the user logger to
            userLoggerStream = user_std_out

            user_property_log = []
            mailbox._imap_client.user_property_log = user_property_log

            now = timezone.now().replace(microsecond=0)
            is_fired = False
            logger.critical("task manager %s now: %s" % (prettyPrintTimezone(task.date), prettyPrintTimezone(now)))
            new_msg = {}

            new_msg["timestamp"] = str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f"))
            new_msg["type"] = "see-later"

            copy_msg = copy.deepcopy(new_msg)
            copy_msg["timestamp"] = str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f"))
            copy_msg["log"] = ""
            msg=None
            try:
                if task.email_rule.type == "see-later":
                    msg_schema = MessageSchema.objects.filter(base_message=task.base_message)
                    if msg_schema.exists(): 
                        for m in msg_schema:
                            msg=Message(m, mailbox._imap_client)
                            user_environ.update({"my_message": msg})
                            exec(json.loads(task.email_rule.code), user_environ)
                        is_fired = True
                    
                elif new_msg["type"] == "remind":
                    user_environ = json.loads(task.email_rule.code) if len(task.email_rule.code) else {}
                    
                    for msg_schema in task.base_message.messages.all():
                        mailbox._imap_client.select_folder(user_environ["hide_in"])
                        msg=Message(msg_schema, mailbox._imap_client)
                        msg.forward(user_environ["note"])
                        break
                else: # on times
                    code = task.email_rule.code
                    code = codeobject_loads(json.loads(code))
                    code = type(codeobject_loads)(code, user_environ)

                    if task.base_message:
                        message_schemas = MessageSchema.objects.filter(base_message=task.base_message)
                        if message_schemas.exists(): 
                            msg = Message(message_schemas[0], mailbox._imap_client)
                            code(msg)
                    else:
                        contact_schemas = task.contact
                    
                        contact = Contact(contact_schemas, mailbox._imap_client)
                        code(contact)
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
                    if msg:
                        copy_msg.update(print_execution_log(msg))
                    copy_msg["trigger"] = task.email_rule.name
                    task.delete()
                    

                    copy_msg["log"] = "%s\n%s" % (user_std_out.getvalue(), copy_msg["log"] )
                    dump_execution_log(mailbox._imap_account, {copy_msg["timestamp"]: copy_msg}, mailbox._imap_client.user_property_log)
                        
                    

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
            # TODO get the right value
            res['property_log'] = []

        user_std_out.close()
        return res
