from icalevents.icalevents import events
import datetime

es = events(
    "https://calendar.google.com/calendar/ical/3ffpub8evedp0rkgvnubs5s3qk%40group.calendar.google.com/private-4250a5c9223e2fdeb9b64397e3944922/basic.ics",
    start=datetime.datetime.now() + datetime.timedelta(hours=-10),
    end=datetime.datetime.now() + datetime.timedelta(hours=2)
)

for event in es:
    print(event.summary)
