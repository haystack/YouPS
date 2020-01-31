from nylas import APIClient
from private import *

nylas = APIClient(
    NYLAS_ID,
    NYLAS_SECRET,
    "5QYlryIVYRhp0jVsYc0xpdxgvWn7kh"
)

t=nylas.threads.where(limit=3,from_='arvindsatya@mit.edu',subject='Sign up to meet David Murray-Post, University of Edinburgh, January 28, 2020')
print(t)

for thread in t:
    print(thread)
    print()


# t = nylas.messages.where(limit=1,received_after=1579959448,received_before=1580319448,from_='arvindsatya@mit.edu',subject='Re: Sign up to meet David Murray-Post, University of Edinburgh, January 28, 2020')[0]

# for m in nylas.messages.where(thread_id=t.id,view='expanded'):
#     print(m)
#     print()


draft = nylas.drafts.create()
draft.subject = "With Love, From Nylas"
draft.to = [{'email': 'soya@mit.edu', 'name': 'My Nylas Friend'}, {'email': 'help@youps.csail.mit.edu', 'name': 'My Nylas Friend'}]
# You can also assign draft.cc, draft.bcc, and draft.from_ in the same manner
draft.body = "This email was sent using the Nylas email API. Visit https://nylas.com for details."
draft.reply_to = [{'email': 'you@example.com', 'name': 'Your Name'}]
# Note: changing from_ to a different email address may cause deliverability issues
draft.from_ = [{'email': 'soya@mit.edu', 'name': 'Soya Park'}]

draft.send()


# contact = nylas.contacts.create()
# contact.given_name = 'My'
# contact.middle_name = 'Nylas'
# contact.surname = 'Friend'
# contact.suffix = 'API'
# contact.nickname = 'Nylas'
# contact.office_location = 'San Francisco'
# contact.company_name = 'Nylas'
# contact.notes = 'Check out the Nylas Email, Calendar, and Contacts APIs'
# contact.manager_name = 'Communications'
# contact.job_title = 'Communications Platform'
# # contact.birthday = '2014-06-01'

# # emails must be one of type personal, or work
# contact.emails['personal'] = ['test@nylas.com']

# contact.save()

# for m in nylas.contacts.where(email='test@nylas.com'):
#     print(m)

# for m in nylas.messages.where(message_id="CAGrnvj4QCzT8iK-OpULwtZ+sz0Koga3_i3zf9B4wKPfwQBwnz3w@mail.gmail.com"):
#     print (m)
# for m in nylas.messages.where(limit=1,id="a0hiacdk6fsq0rpu671hhhjb2"):
#     print (m)

# for message in nylas.threads.where(limit=1,subject='Hi there cutie',from_='soya@mit.edu'):
#     print(message.id)
    
#     m = nylas.messages.where(limit=1,id=message.id)
#     print(m)
#     for x in m:
#         print(m.headers)