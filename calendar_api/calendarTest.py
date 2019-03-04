import youpsCalendar

# link = 'https://calendar.google.com/calendar/ical/uh0pjuueg6973g214phtapbq3c%40group.calendar.google.com/public/basic.ics'
# link = "https://calendar.google.com/calendar/ical/g97ka7smdj0v5mpahjhus7su8o%40group.calendar.google.com/public/basic.ics"
link = "https://calendar.google.com/calendar/ical/3ffpub8evedp0rkgvnubs5s3qk%40group.calendar.google.com/private-2bbe88297a1a1b5b38af796c4a094ba6/basic.ics"
classCalendar = youpsCalendar.YoupsCalendar('6.UAT', link)

print(classCalendar)
