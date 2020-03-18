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
        """Get the organization of this contact (mutable)

        Returns:
            str: The organization associated with this contact
        """
        return self._schema.organization

    @organization.setter
    def organization(self, value):
        # type: () -> t.AnyStr
        self._schema.organization = value
        self._schema.save()

    @CustomProperty
    def geolocation(self):
        # type: () -> t.AnyStr
        """Get the location of this contact (mutable)

        Returns:
            str: The location associated with this contact
        """
        return self._schema.geolocation

    @geolocation.setter
    def geolocation(self, value):
        # type: () -> t.AnyStr
        self._schema.geolocation = value
        self._schema.save()

    def messages_to(self, N=3):
        # type: () -> t.List[Message]
        """Get the Messages which are to this contact

        Args:
            N (int): a number of recent messages you want (max:50)

        Returns:
            t.List[Message]: The messages where this contact is listed in the to field
        """
        if N>50:
            raise Exception("N should be less or equal to 50")

        from engine.models.message import Message
        m = []
        cnt =0
        for base_message in self._schema.to_messages.all():
            for message_schema in base_message.messages.all():
                cnt = cnt +1
                m.append(Message(message_schema, self._imap_client))
                break
            if cnt >= N:
                break

        return m

    def messages_from(self, N=3):
        # type: () -> t.List[Message]
        """Get the Messages which are from this contact

        Args:
            N (int): a number of recent messages you want (max:50)

        Returns:
            t.List[Message]: The messages where this contact is listed in the from field
        """
        if N>50:
            raise Exception("N should be less or equal to 50")

        from engine.models.message import Message

        m = []
        cnt = 0
        for base_message in self._schema.from_messages.all():
            for message_schema in base_message.messages.all():
                cnt = cnt +1
                m.append(Message(message_schema, self._imap_client))
                break
            if cnt >= N:
                break

        return m


    def _messages_from_date(self, from_date=None, to_date=None):
        """Get the Messages which are from this contact

        Args:
            from_date (datetime): Searching messages from this date
            to_date (datetime): to this date

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

    def messages_bcc(self,  N=3):
        # type: () -> t.List[Message]
        """Get the Messages which are bcc this contact

        Args:
            N (int): a number of recent messages you want (max:50)

        Returns:
            t.List[Message]: The messages where this contact is listed in the bcc field
        """
        if N>50:
            raise Exception("N should be less or equal to 50")
            
        from engine.models.message import Message
        m = []
        cnt = 0
        for base_message in self._schema.bcc_messages.all():
            for message_schema in base_message.messages.all():
                cnt = cnt +1
                m.append(Message(message_schema, self._imap_client))
                break
            if cnt >= N:
                break

        return m

    def messages_cc(self, N=3):
        # type: () -> t.List[Message]
        """Get the Messages which are cc this contact

        Args:
            N (int): a number of recent messages you want (max:50)

        Returns:
            t.List[Message]: The messages where this contact is listed in the cc field
        """
        if N>50:
            raise Exception("N should be less or equal to 50")

        from engine.models.message import Message
        m = []
        cnt = 0
        for base_message in self._schema.cc_messages.all():
            for message_schema in base_message.messages.all():
                cnt = cnt +1
                m.append(Message(message_schema, self._imap_client))
                break
            if cnt >= N:
                break

        return m

    @ActionLogging
    def _on_message(self, email_rule_id):
        """helper function for on_message() for logging and undo
        """
        pass

    def on_message(self, handler):
        """add an event handler that is triggered everytime when there is a new message arrived from this contact

        Args:
            handler (function): A function to execute each time when there are messaged arrvied to this thread. The function provides the newly arrived message as an argument
        """
        if not handler or type(handler).__name__ != "function":
            raise Exception('on_message(): requires callback function but it is %s ' % type(handler).__name__)

        if handler.func_code.co_argcount != 1:
            raise Exception('on_message(): your callback function should have only 1 argument, but there are %d argument(s)' % handler.func_code.co_argcount)

        try:
            a = codeobject_dumps(handler.func_code)
        except:
            raise Exception("on_message(): your callback function maybe include inner functions? Remove the inner functions and try again")
        if self._is_simulate:
            a=codeobject_loads(a)
            # s=exec(a)
            # logger.info(s)
            code_object=a

            from browser.sandbox_helpers import get_default_user_environment
            from engine.models.mailbox import MailBox  # noqa: F401 ignore unused we use it for typing
            a = get_default_user_environment(MailBox(self._schema.imap_account, self._imap_client, is_simulate=True), print)
            b = globals()
            g = type(codeobject_loads)(code_object, dict(a, **b))
            print("on_message(): Simulating callback function..:")
            messages_from_this_contact = self.messages_from(1)
            if len(messages_from_this_contact):
                try:
                    g(messages_from_this_contact[0])
                except SystemError:
                    raise Exception("on_message(): your callback function tries to use an unknown object that is not defined inside the function")
            else:
                print("on_message(): no message from this contact to simulate on")
        else: 
            # add EventManager attached to it
            er = EmailRule(imap_account=self._schema.imap_account, name='on message', type='on_message', code=json.dumps(a))
            er.save()

            self._on_message(er.id)

            e = EventManager(contact=self._schema, email_rule=er)
            e.save()

        print("on_message(): The handler will be executed when a new message arrives from this contact")

    @ActionLogging
    def _on_time(self, email_rule_id):
        """helper function for on_time() for logging and undo
        """
        pass

    def on_time(self, handler, later_at=60):
        """The number of minutes to wait before executing the handler. 

        Args:
            handler (function): A function that will be executed. The function provides the contact object as an argument \n
            later_at (int or datetime): when to execute the handler (in minutes). You can also send datetime to set an absolute time
        """
        if not handler or type(handler).__name__ != "function":
            raise Exception('on_time(): requires callback function but it is %s ' % type(handler).__name__)

        if handler.func_code.co_argcount != 1:
            raise Exception('on_time(): your callback function should have only 1 argument, but there are %d argument(s)' % handler.func_code.co_argcount)

        later_at = get_datetime_from_now(later_at)

        try:
            a = codeobject_dumps(handler.func_code)
        except:
            raise Exception("on_time(): your callback function maybe include inner functions? Remove the inner functions and try again")
        if self._is_simulate:
            a=codeobject_loads(a)
            code_object=a

            from browser.sandbox_helpers import get_default_user_environment
            from engine.models.mailbox import MailBox  # noqa: F401 ignore unused we use it for typing
            mailbox = MailBox(self._schema.imap_account, self._imap_client, is_simulate=True)
            g = type(codeobject_loads)(code_object, get_default_user_environment(mailbox, print))
            print("on_time(): Simulating callback function..:")
            
            try:
                g(self)
            except SystemError:
                raise Exception("on_time(): your callback function tries to use an unknown object that is not defined inside the function")
        else:
            # add EventManager attached to it
            er = EmailRule(imap_account=self._schema.imap_account, name='on time', type='on_time', code=json.dumps(a))
            er.save()

            self._on_time(er.id)

            e = EventManager(contact=self._schema, date=later_at, email_rule=er)
            e.save()

        print("on_time(): The handler will be executed at %s " % prettyPrintTimezone(later_at))


    def messages(self, N=3):
        # type: (t.integer) -> t.List[Message]
        """Get the N Messages which are exchanged with this contact
        Examples:
            >>> my_message.sender.messages()
            >>> [Message object "Hello!", Message object "other message", Message object "another messages.."]

        Args:
            N (int): a number of recent messages you want (max:50)

        Returns:
            t.List[Message]: The messages where this contact is listed in the from/to/cc/bcc field
        """
        if N>50:
            raise Exception("N should be less or equal to 50")
        from engine.models.message import Message

        message_schemas = MessageSchema.objects.filter(imap_account=self._schema.imap_account).filter(Q(base_message__from_m=self._schema) | Q(base_message__to=self._schema) | Q(base_message__cc=self._schema) | Q(base_message__bcc=self._schema)).order_by("-base_message__date")[:N]
        logger.debug(message_schemas.values('id'))
        # TODO fetch from imap 
        # self._imap_client.search('OR FROM "%s" (OR TO "%s" (OR CC "%s" BCC "%s"))' % (self.email, self.email, self.email, self.email))
        return [Message(message_schema, self._imap_client) for message_schema in message_schemas]

