import heapq
import email

class Pile:
    def __init__(self, imap, search_criteria):
        """create a new pile

        Args:
            imap (imapclient.IMAPClient): connection to an imap server
            search_criteria (Union[str, List[str]]): string or list of strings
                of search criteria to search the imap server
        """

        self.imap = imap
        self.search_criteria = search_criteria
        self.is_valid = True
        # TODO not sure that we need this list of email only used on 451
        self.EMAIL = []
        self.EMAIL_IDS = []
        self.EMAIL_IDS, self.EMAIL = self.init_email()

    def init_email(self):
        """Get all emails passing the search criteria and return them

        Returns:
            Tuple[List[int], List[message]]: List of message ids and email messages that pass the search criteria
        """

        # get unread emails that pass search criteria
        unread_message_ids = self.get_unread_message_ids()

        # get message ids that pass search criteria (includes read emails)
        initial_message_ids = self.get_IDs()

        # these are the message ids which have data associated with them
        final_message_ids = []
        messages = []

        try:
            # fetch RFC822 data about the messages (this marks emails as read)
            response = self.imap.fetch(initial_message_ids, ['RFC822'])
            for msg_id, data in response.iteritems():
                if b'RFC822' not in data:
                    continue
                messages.append(email.message_from_string(data[b'RFC822']))
                final_message_ids.append(msg_id)
        finally:
            # finally even if we crash try to mark messages as unread
            if unread_message_ids:
                self.imap.remove_flags(unread_message_ids, '\\Seen')

        return final_message_ids, messages

    def check_email(self):
        return self.is_valid

    #################################
    ### Getter functions
    def get_content(self):
        contents = self.get_contents()
        if len(contents) > 0:
            return contents[0]
        else:
            return ""

    def get_date(self):
        dates = self.get_dates()
        if len(dates) > 0:
            return dates[0]
        else:
            return ""

    def get_notes(self):
        # TODO this might be confusing since it returns all the flags on all messages
        flags = []
        for _, data in self.imap.get_flags(self.EMAIL_IDS).items():
            for f in data:
                if "YouPS" == f:
                    continue
                flags.append(f)

        return flags

    def get_gmail_labels(self):
        # TODO this might be confusing since it returns all the flags on all messages
        flags = []
        for _, data in self.imap.get_gmail_labels(self.EMAIL_IDS).items():
            for f in data:
                if "YouPS" == f:
                    continue
                flags.append(f)

        return flags

    def get_sender(self):
        senders = self.get_senders()
        if len(senders) > 0:
            return senders[0]
        else:
            return ""

    def get_subject(self):
        subjects = self.get_subjects()
        if len(subjects) > 0:
            return subjects[0]
        else:
            return ""

    def get_recipient(self):
        recipients = self.get_recipients()
        if len(recipients) > 0:
            return recipients[0]
        else:
            return ""


    ### Getter functions
    #################################



    def add_gmail_labels(self, flags):
        self.imap.add_gmail_labels(self.EMAIL_IDS, flags)

    def add_notes(self, flags):
        self.imap.add_flags(self.EMAIL_IDS, flags)

    def copy(self, dst_folder):
        # TODO source folder should be able to be specified
        src_folder = "INBOX"
        self.create_folder(dst_folder)
        self.imap.select_folder(src_folder)
        self.imap.copy(self.EMAIL_IDS, dst_folder)

    def delete(self):
        self.imap.add_flags(self.EMAIL_IDS, ['\\Deleted'])

    def has_label(self, label):
        for data in self.get_notes():
            if data == label:
                return True

        return False

    def mark_read(self, is_seen=True):
        # if true, add SEEN flags
        if is_seen:
            self.imap.set_flags(self.EMAIL_IDS, '\\Seen')
        else:
            self.imap.remove_flags(self.EMAIL_IDS, '\\Seen')

    def move(self, dst_folder):
        src_folder = "INBOX"
        self.imap.select_folder(src_folder)
        self.imap.move(self.EMAIL_IDS, dst_folder)

    def remove_notes(self, flags):
        self.imap.remove_flags(self.EMAIL_IDS, flags)

    def remove_gmail_labels(self, flags):
        self.imap.remove_gmail_labels(self.EMAIL_IDS, flags)

    #################################
    ### Folder functions

    def create_folder(self, folder):
        if not self.folder_exists(folder):
            self.imap.create_folder(folder)

    def folder_exists(self, folder):
        return self.imap.folder_exists(folder)

    def delete_folder(self, folder):
        self.imap.delete_folder(folder)

    def list_folders(self, directory=u'', pattern=u'*'):
        return self.imap.list_folders(directory, pattern)

    def rename_folder(self, old_name, new_name):
        self.imap.rename_folder(old_name, new_name)

    ### Folder functions
    #################################

    def get_IDs(self):
        return self.imap.search(self.search_criteria)

    def get_count(self):
        print ("info", "Mmail getCount(): " + self.search_criteria + str(len(self.EMAIL_IDS)))
        return len(self.EMAIL_IDS)

    def get_N_latest_emails(self, N):
        return heapq.nlargest(N, self.EMAIL_IDS)

    def get_subjects(self):
        return [message.get('Subject') for message in self.EMAIL]

    def get_senders(self):
        return [message.get('From') for message in self.EMAIL]

    def get_dates(self):
        return [message.get('Date') for message in self.EMAIL]

    def get_recipients(self):
        return [message.get('To') for message in self.EMAIL]

    def get_contents(self):
        bodys = []
        for email_message in self.EMAIL:
            text = ""
            html = ""
            for part in email_message.walk():
                if part.is_multipart():
                    continue
                else:
                    decoded = part.get_payload(decode=True)
                    charset = part.get_content_charset()
                    if charset is not None:
                        decoded = unicode(part.get_payload(decode=True), str(charset), "ignore").encode('utf8',
                                                                                                        'replace')

                    content_type = part.get_content_type()
                    if content_type == 'text/plain':
                        text += decoded
                    elif content_type == 'text/html':
                        html += decoded
                    else:
                        # TODO should be a log but idk where logs go... LSM
                        print 'unknown content type', content_type

            bodys.append(text if text != "" else html)

        return bodys

    def get_unread_message_ids(self):
        """Return uids of messages which pass the search critera and are not flagged as seen.

        Returns:
            List[int]: unique ids of messages which pass the search critera and are not flagged as seen.
        """

        flags = self.get_notes()

        if flags is None:
            return []

        unread_emails = []

        for msgid, data in self.imap.get_flags(self.get_IDs()).items():
            if b'\\Seen' not in data:
                unread_emails.append(msgid)

        return unread_emails
