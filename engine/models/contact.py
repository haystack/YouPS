from __future__ import unicode_literals, print_function, division
import typing as t  # noqa: F401 ignore unused we use it for typing
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing
from schema.youps import ContactSchema, MessageSchema  # noqa: F401 ignore unused we use it for typing
from django.db.models import Q
import logging
from engine.models.helpers import CustomProperty

logger = logging.getLogger('youps')  # type: logging.Logger

class Contact(object):

    def __init__(self, contact_schema, imap_client):
        # type: (ContactSchema, IMAPClient) -> Contact

        self._schema = contact_schema  # type: ContactSchema

        # the connection to the server
        self._imap_client = imap_client  # type: IMAPClient

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
        return [Message(message_schema, self._imap_client) for message_schema in self._schema.to_messages.all()]

    @CustomProperty
    def messages_from(self):
        # type: () -> t.List[Message]
        """Get the Messages which are from this contact

        Returns:
            t.List[Message]: The messages where this contact is listed in the from field
        """
        from engine.models.message import Message
        return [Message(message_schema, self._imap_client) for message_schema in self._schema.from_messages.all()]

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
