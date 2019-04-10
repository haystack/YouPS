from __future__ import unicode_literals, division

import logging
import sys, traceback
import datetime
import copy
import typing as t  # noqa: F401 ignore unused we use it for typing
from StringIO import StringIO
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing
from schema.youps import MessageSchema  # noqa: F401 ignore unused we use it for typing

from engine.models.event_data import NewMessageData, NewMessageDataScheduled, NewFlagsData
from engine.models.mailbox import MailBox  # noqa: F401 ignore unused we use it for typing
from engine.models.message import Message

logger = logging.getLogger('youps')  # type: logging.Logger


def interpret(mailbox, mode, is_simulate=False, simulate_info={}):
    # type: (MailBox, MailbotMode, bool) -> t.Dict[t.AnyStr, t.Any]

    from schema.youps import EmailRule, MailbotMode

    # set up the default result
    res = {'status': True, 'imap_error': False, 'imap_log': ""}

    # if mode is None:
    #     logger.warn("No mode set for interpret")
    #     res['status'] = False
    #     return res

    # assert we actually got a mailbox
    assert isinstance(mailbox, MailBox)
    # assert the mode is the mailboat mode
    # assert isinstance(mode, MailbotMode)
    assert mailbox.new_message_handler is not None

    # define user methods

    # get the logger for user output
    userLogger = logging.getLogger('youps.user')  # type: logging.Logger
    # get the stream handler associated with the user output
    userLoggerStreamHandlers = filter(lambda h: isinstance(h, logging.StreamHandler), userLogger.handlers)
    userLoggerStream = userLoggerStreamHandlers[0].stream if userLoggerStreamHandlers else None
    assert userLoggerStream is not None

    mailbox.is_simulate = is_simulate

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
            'send': mailbox.send,
            'on_message_arrival': lambda f: mailbox.new_message_handler.handle(f),
            'on_flag_added': lambda f: mailbox.added_flag_handler.handle(f),
            'on_flag_removed': lambda f: mailbox.removed_flag_handler.handle(f),
        }

        # simulate request. normally from UI
        if is_simulate:
            code = simulate_info['code']
            message_schema = MessageSchema.objects.filter(id=simulate_info['msg-id'])
            for m_schema in message_schema:
                new_message = Message(m_schema, mailbox._imap_client, is_simulate=True)            

                # execute the user's code
                # exec cant register new function (e.g., on_message_arrival) when there is a user_env
                user_environ['new_message'] = new_message
                exec(code + "\non_message(new_message)", user_environ)    

        # regular loading from event queue
        else:
            # iterate through event queue
            for event_data in mailbox.event_data_list:
                new_msg = {}

                # event for new message arrival
                # TODO maybe caputre this info after execute log?
                if isinstance(event_data, NewMessageData) or isinstance(event_data, NewMessageDataScheduled) or isinstance(event_data, NewFlagsData):
                    from_field = {}
                    if event_data.message.from_._schema:
                        from_field = {
                            "name": event_data.message.from_.name,
                            "email": event_data.message.from_.email,
                            "organization": event_data.message.from_.organization,
                            "geolocation": event_data.message.from_.geolocation
                        }

                    to_field = [{
                        "name": contact.name,
                        "email": contact.email,
                        "organization": contact.organization,
                        "geolocation": contact.geolocation
                    } for contact in event_data.message.to]

                    cc_field = [{
                        "name": contact.name,
                        "email": contact.email,
                        "organization": contact.organization,
                        "geolocation": contact.geolocation
                    } for contact in event_data.message.cc]

                    # This is to log for users
                    new_msg = {
                        "timestamp": str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f")),
                        "type": "new_message", 
                        "folder": event_data.message.folder.name, 
                        "from_": from_field, 
                        "subject": event_data.message.subject, 
                        "to": to_field,
                        "cc": cc_field,
                        "flags": [f.encode('utf8', 'replace') for f in event_data.message.flags],
                        "date": str(event_data.message.date),
                        "deadline": event_data.message.deadline, 
                        "is_read": event_data.message.is_read, 
                        "is_deleted": event_data.message.is_deleted, 
                        "is_recent": event_data.message.is_recent,
                        "log": ""
                    }

                # if tho the engine is not turned on yet, still leave the log of message arrival 
                # TODO fix this. should be still able to show incoming message when there is mode exists and no rule triggers it 
                if mode is None:
                    new_log[new_msg["timestamp"]] = new_msg
                    continue

                # TODO maybe use this instead of mode.rules
                for rule in EmailRule.objects.filter(mode=mode):
                    is_fired = False 
                    copy_msg = copy.deepcopy(new_msg)
                    copy_msg["timestamp"] = str(datetime.datetime.now().strftime("%m/%d %H:%M:%S,%f"))

                    assert isinstance(rule, EmailRule)

                    valid_folders = rule.folders.all()
                    valid_folders = FolderSchema.objects.filter(imap_account=mailbox._imap_account, rules=rule)
                    code = rule.code
                    
                    logger.debug(code)

                    # add the user's functions to the event handlers
                    if rule.type.startswith("new-message"):
                        code = code + "\non_message_arrival(on_message)"
                    elif rule.type == "flag-change":
                        code = code + "\non_flag_added(on_flag_change)"
                    # else:
                    #     continue
                    #     # some_handler or something += repeat_every

                    
                    try:
                        # execute the user's code
                        # exec cant register new function (e.g., on_message_arrival) when there is a user_env
                        exec(code, user_environ)

                        # Check if the type of rule and event_data match
                        if (type(event_data).__name__ == "NewMessageData" and rule.type =="new-message") or \
                                (type(event_data).__name__ == "NewMessageDataScheduled" and rule.type.startswith("new-message-")):

                            # Conduct rules only on requested folders
                            if event_data.message._schema.folder_schema in valid_folders:
                                logger.info("fired %s %s" % (rule.name, event_data.message.subject))
                                # TODO maybe user log here that event has been fired
                                is_fired = True
                                event_data.fire_event(mailbox.new_message_handler)
                        if isinstance(event_data, NewFlagsData) and rule.type == "flag-change":
                            if event_data.message._schema.folder_schema in valid_folders:
                                logger.info("fired %s %s" % (rule.name, event_data.message.subject))
                                # TODO maybe user log here that event has been fired
                                is_fired = True
                                event_data.fire_event(mailbox.added_flag_handler)

                    except Exception as e:
                        # Get error message for users if occurs
                        # print out error messages for user 
                        
                        # if len(inspect.trace()) < 2: 
                        #     logger.exception("System error during running user code")
                        # else:
                        
                        exc_type, exc_obj, exc_tb = sys.exc_info()
                        logger.info(e)
                        logger.debug(exc_obj)
                        # logger.info(traceback.print_exception())

                        # TODO find keyword 'in on_message'
                        logger.info(traceback.format_tb(exc_tb))
                        logger.info(sys.exc_info())
                        
                        copy_msg["log"] = str(e) + traceback.format_tb(exc_tb)[-1]
                        copy_msg["error"] = True 
                    finally:         
                        if is_fired:
                            logger.debug("handling fired %s %s" % (rule.name, event_data.message.subject))
                            copy_msg["trigger"] = rule.name
                            
                            copy_msg["log"] = "%s\n%s" % (user_std_out.getvalue(), copy_msg["log"] )

                            new_log[copy_msg["timestamp"]] = copy_msg    

                        # flush buffer
                        user_std_out = StringIO()

                        # set the stdout to a string
                        sys.stdout = user_std_out

                        # set the user logger to
                        userLoggerStream = user_std_out

                    mailbox.new_message_handler.removeAllHandles()
                    mailbox.added_flag_handler.removeAllHandles()

    except Exception as e:
        res['status'] = False
        userLogger.exception("failure running user %s code" %
                             mailbox._imap_account.email)
    finally:
        # set the stdout back to what it was
        sys.stdout = sys.__stdout__
        userLoggerStream = sys.__stdout__

        # if it is simulate don't save to db
        if is_simulate:
            logger.info(user_std_out.getvalue())
        
        # save logs to db
        else:
            logger.info(new_log)
            res['imap_log'] = new_log

        user_std_out.close()
        return res
