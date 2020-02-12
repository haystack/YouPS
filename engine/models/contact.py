from __future__ import unicode_literals, print_function, division
import typing as t  # noqa: F401 ignore unused we use it for typing
import json
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing
from schema.youps import ContactSchema, EmailRule, EventManager, MessageSchema  # noqa: F401 ignore unused we use it for typing
from django.db.models import Q
from smtp_handler.utils import codeobject_dumps, codeobject_loads
import logging
from engine.models.helpers import CustomProperty, ActionLogging
from engine.utils import get_datetime_from_now, prettyPrintTimezone

logger = logging.getLogger('youps')  # type: logging.Logger

class Contact(object):

    def __init__(self, contact_schema, imap_client, is_simulate=False):
        # type: (ContactSchema, IMAPClient) -> Contact

        self._schema = contact_schema  # type: ContactSchema

        # the connection to the server
        self._imap_client = imap_client  # type: IMAPClient
        self._is_simulate = is_simulate

    def __str__(self):
        return "%s, %s" % (self.name, self.email)

    def __repr__(self):
        return "Contact object: %s" % self.email

    def __eq__(self, other): 
        if isinstance(other, basestring):
            return other in self.aliases or other == self.email

        if isinstance(other, Contact):
            return other._schema == self._schema 

        return False

    @CustomProperty
    def email(self):
        # type: () -> t.AnyStr
        """Get the email address associated with this contact

        Returns:
            str: The email address associated with this contact
        """
        return self._schema.email

    @CustomProperty
    def aliases(self):
        # type: () -> t.List[t.AnyStr]
        """Get all the names associated with this contact

        Returns:
            list: The names associated with this contact
        """
        return self._schema.aliases.all().values_list('name', flat=True)

    @CustomProperty
    def name(self):
        # type: () -> t.AnyStr
        """Get the name associated with this contact

        Returns:
            str: The name associated with this contact
        """
        # simply returns the most common alias
        try:
            return self._schema.aliases.order_by('-count').first().name
        except Exception as e:
            # logger.exception(e)
            return ""

    @CustomProperty
    def organization(self):
        # type: () -> t.AnyStr
        """Get the organization of this contact

        Returns:
            str: The organization associated with this contact
        """
        return self._schema.organization

    @CustomProperty
    def geolocation(self):
        # type: () -> t.AnyStr
        """Get the location of this contact

        Returns:
            str: The location associated with this contact
        """
        return self._schema.geolocation

    @CustomProperty
    def messages_to(self):
        # type: () -> t.List[Message]
        """Get the Messages which are to this contact

        Returns:
            t.List[Message]: The messages where this contact is listed in the to field
        """
        from engine.models.message import Message
        return [Message(message_schema, self._imap_client) for message_schema in MessageSchema.objects.filter(imap_account=self._schema.imap_account, base_message__to=self._schema)]

    @CustomProperty
    def messages_from(self):
        # type: () -> t.List[Message]
        """Get the Messages which are from this contact

        Returns:
            t.List[Message]: The messages where this contact is listed in the from field
        """
        from engine.models.message import Message
        return [Message(message_schema, self._imap_client) for message_schema in MessageSchema.objects.filter(imap_account=self._schema.imap_account, base_message__from_m=self._schema)]

    def messages_from_date(self, from_date=None, to_date=None):
        """Get the Messages which are from this contact

        Returns:
            t.List[Message]: The messages where this contact is listed in the from field
        """
        from engine.models.message import Message

        message_schemas = []
        if from_date is None and to_date is None:
            return self.messages_from
    
        elif from_date is None:
            message_schemas = MessageSchema.objects.filter(imap_account=self._schema.imap_account, base_message__from_m=self._schema) \
                .filter(base_message__date__lte=to_date)

        elif to_date is None:
            message_schemas = MessageSchema.objects.filter(imap_account=self._schema.imap_account, base_message__from_m=self._schema) \
                .filter(base_message__date__gte=from_date)
        
        else:   # return all 
            message_schemas = MessageSchema.objects.filter(imap_account=self._schema.imap_account, base_message__from_m=self._schema) \
                .filter(base_message__date__range=[from_date, to_date])
            
        logger.debug(message_schemas.values('id'))
        return [Message(message_schema, self._imap_client) for message_schema in message_schemas]

    @CustomProperty
    def messages_bcc(self):
        # type: () -> t.List[Message]
        """Get the Messages which are bcc this contact

        Returns:
            t.List[Message]: The messages where this contact is listed in the bcc field
        """
        from engine.models.message import Message
        return [Message(message_schema, self._imap_client) for message_schema in self._schema.bcc_messages.all()]

    @CustomProperty
    def messages_cc(self):
        # type: () -> t.List[Message]
        """Get the Messages which are cc this contact

        Returns:
            t.List[Message]: The messages where this contact is listed in the cc field
        """
        from engine.models.message import Message
        return [Message(message_schema, self._imap_client) for message_schema in self._schema.cc_messages.all()]

    @ActionLogging
    def _on_response(self, email_rule_id):
        """helper function for on_response() for logging and undo
        """
        pass

    def on_response(self, handler):
        """add an event handler that is triggered everytime when there is a new message arrived from this contact

        Args:
            handler (function): A function to execute each time when there are messaged arrvied to this thread. The function provides the newly arrived message as an argument
        """
        if not handler or type(handler).__name__ != "function":
            raise Exception('on_response(): requires callback function but it is %s ' % type(handler).__name__)

        if handler.func_code.co_argcount != 1:
            raise Exception('on_response(): your callback function should have only 1 argument, but there are %d argument(s)' % handler.func_code.co_argcount)

        a = codeobject_dumps(handler.func_code)
        if self._is_simulate:
            a=codeobject_loads(a)
            # s=exec(a)
            # logger.info(s)
            code_object=a

            from browser.sandbox_helpers import get_default_user_environment
            from engine.models.mailbox import MailBox  # noqa: F401 ignore unused we use it for typing
            g = type(codeobject_loads)(code_object, get_default_user_environment(MailBox(self._schema.imap_account, self._imap_client, is_simulate=True), print))
            print("on_response(): Simulating callback function..:")
            g(self.messages_from[0])
        else: 
            # add EventManager attached to it
            er = EmailRule(imap_account=self._schema.imap_account, name='on response', type='on_response', code=json.dumps(a))
            er.save()

            self._on_response(er.id)

            e = EventManager(contact=self._schema, email_rule=er)
            e.save()

        print("on_response(): The handler will be executed when a new message arrives from this contact")

    @ActionLogging
    def _on_time(self, email_rule_id):
        """helper function for on_time() for logging and undo
        """
        pass

    def on_time(self, handler, later_at=60):
        """The number of minutes to wait before executing the handler. 

        Args:
            handler (function): A function that will be executed. The function provides the contact object as an argument
            later_at (int): when to move this message back to inbox (in minutes)
        """
        if not handler or type(handler).__name__ != "function":
            raise Exception('on_time(): requires callback function but it is %s ' % type(handler).__name__)

        if handler.func_code.co_argcount != 1:
            raise Exception('on_time(): your callback function should have only 1 argument, but there are %d argument(s)' % handler.func_code.co_argcount)

        later_at = get_datetime_from_now(later_at)

        a = codeobject_dumps(handler.func_code)
        if self._is_simulate:
            a=codeobject_loads(a)
            code_object=a

            from browser.sandbox_helpers import get_default_user_environment
            from engine.models.mailbox import MailBox  # noqa: F401 ignore unused we use it for typing
            g = type(codeobject_loads)(code_object, get_default_user_environment(MailBox(self._schema.imap_account, self._imap_client, is_simulate=True), print))
            print("on_time(): Simulating callback function..:")
            
            g(self)
        else:
            # add EventManager attached to it
            er = EmailRule(imap_account=self._schema.imap_account, name='on time', type='on_time', code=json.dumps(a))
            er.save()

            self._on_time(er.id)

            e = EventManager(contact=self._schema, date=later_at, email_rule=er)
            e.save()

        print("on_time(): The handler will be executed at %s " % prettyPrintTimezone(later_at))


    def recent_messages(self, N=3):
        # type: (t.integer) -> t.List[Message]
        """Get the N Messages which are exchanged with this contact

        Returns:
            t.List[Message]: The messages where this contact is listed in the from/to/cc/bcc field
        """
        from engine.models.message import Message

        message_schemas = MessageSchema.objects.filter(imap_account=self._schema.imap_account).filter(Q(base_message__from_m=self._schema) | Q(base_message__to=self._schema) | Q(base_message__cc=self._schema) | Q(base_message__bcc=self._schema)).order_by("-base_message__date")[:N]
        logger.debug(message_schemas.values('id'))
        # TODO fetch from imap 
        # self._imap_client.search('OR FROM "%s" (OR TO "%s" (OR CC "%s" BCC "%s"))' % (self.email, self.email, self.email, self.email))
        return [Message(message_schema, self._imap_client) for message_schema in message_schemas]

