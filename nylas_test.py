from nylas import APIClient
from private import *

nylas = APIClient(
    NYLAS_ID,
    NYLAS_SECRET,
    "nmCG2Kq9pLK53burtYzFXbACV5BmbZ"
)

t=nylas.threads.where(limit=3,from_='arvindsatya@mit.edu',subject='Sign up to meet David Murray-Post, University of Edinburgh, January 28, 2020')
print(t)

for thread in t:
    print(thread)
    print()


# t = nylas.messages.where(limit=1,received_after=1579959448,received_before=1580319448,from_='arvindsatya@mit.edu',subject='Re: Sign up to meet David Murray-Post, University of Edinburgh, January 28, 2020')[0]

for m in nylas.messages.where(thread_id=t.id,view='expanded'):
    print(m)
    print()

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