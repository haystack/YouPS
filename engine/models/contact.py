from __future__ import unicode_literals, print_function, division
import typing as t  # noqa: F401 ignore unused we use it for typing
from imapclient import IMAPClient  # noqa: F401 ignore unused we use it for typing
from schema.youps import ContactSchema, MessageSchema  # noqa: F401 ignore unused we use it for typing
from django.db.models import Q
import logging

logger = logging.getLogger('youps')  # type: logging.Logger

class Contact(object):

    def __init__(self, contact_schema, imap_client):
        # type: (ContactSchema, IMAPClient) -> Contact

        self._schema = contact_schema  # type: ContactSchema

        # the connection to the server
        self._imap_client = imap_client  # type: IMAPClient

    def __str__(self):
        return self.name

    def __repr__(self):
        return repr("Contact object %s" % str(self.name or self.email))

    def __eq__(self, other): 
        if isinstance(other, basestring):
            return (other == self.name) or (other == self.email) 

        if isinstance(other, Contact):
            return (other.name == self.name) and (other.email == self.email)

    @property
    def email(self):
        # type: () -> t.AnyStr
        """Get the email address associated with this contact

        Returns:
            str: The email address associated with this contact
        """
        return self._schema.email

    @property
    def name(self):
        # type: () -> t.AnyStr
        """Get the name associated with this contact

        Returns:
            str: The name associated with this contact
        """
        return self._schema.name or self.email

    @property
    def organization(self):
        # type: () -> t.AnyStr
        """Get the organization of this contact

        Returns:
            str: The organization associated with this contact
        """
        return self._schema.organization

    @property
    def geolocation(self):
        # type: () -> t.AnyStr
        """Get the location of this contact

        Returns:
            str: The location associated with this contact
        """
        return self._schema.geolocation

    @property
    def messages_to(self):
        # type: () -> t.List[Message]
        """Get the Messages which are to this contact

        Returns:
            t.List[Message]: The messages where this contact is listed in the to field
        """
        from engine.models.message import Message
        return [Message(message_schema, self._imap_client) for message_schema in self._schema.to_messages.all()]

    @property
    def messages_from(self):
        # type: () -> t.List[Message]
        """Get the Messages which are from this contact

        Returns:
            t.List[Message]: The messages where this contact is listed in the from field
        """
        from engine.models.message import Message
        return [Message(message_schema, self._imap_client) for message_schema in self._schema.from_messages.all()]

    @property
    def messages_bcc(self):
        # type: () -> t.List[Message]
        """Get the Messages which are bcc this contact

        Returns:
            t.List[Message]: The messages where this contact is listed in the bcc field
        """
        from engine.models.message import Message
        return [Message(message_schema, self._imap_client) for message_schema in self._schema.bcc_messages.all()]

    @property
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
        from browser.models.message import Message

        message_schemas = MessageSchema.objects.filter(Q(from_m=self._schema) | Q(to=self._schema) | Q(cc=self._schema) | Q(bcc=self._schema)).order_by("-date")[:N]
        logger.debug(message_schemas.values('id'))
        # TODO fetch from imap 
        # self._imap_client.search('OR FROM "%s" (OR TO "%s" (OR CC "%s" BCC "%s"))' % (self.email, self.email, self.email, self.email))
        return [Message(message_schema, self._imap_client) for message_schema in message_schemas]

