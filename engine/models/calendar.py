import logging
# from ics import Calendar, Event # Soya comment out
from icalevents.icalevents import events, download_calendar, find_conflicts
from dateutil.tz import tzlocal
from schema.youps import CalendarSchema
from django.utils import timezone
import datetime

logger = logging.getLogger('youps')  # type: logging.Logger

class MyCalendar(object):
    """Calendar Module for Youps."""

    def __init__(self, name, link, apple=False):
        """Create a new YoupsCalendar instance.
        Parameters:
        name (String) -- the name of the character
        link (String) -- public ics link to the calendar
        """
        self.name = name
        self.link = link
        self.apple = apple

    def get_conflicts(self, startTime=None, endTime=None,
                      defaultInterval=datetime.timedelta(hours=1)):
        """Check the calendar to see if the specified time is available.

        Parameters:
        startTime (datetime) -- start of the time interval
        endTime (datetime) -- end of the time interval
        Returns:
        list: events conflicting with the interval

        """
        if startTime is None:
            startTime = datetime.datetime.now()

        if endTime is None:
            endTime = startTime + defaultInterval

        conflicts = []

        try:
            calendars = CalendarSchema.objects.filter(link=self.link)
            content = ''
            # if there is no calendar or it is out dated, download calendar again
            if not calendars.exists():
                c = CalendarSchema(link= self.link)
                content = download_calendar(self.link, fix_apple=self.apple)

                c.content = content
                c.save()
                
            elif calendars[0].downloaded_at + datetime.timedelta(seconds=300) < timezone.now():
                content = download_calendar(self.link, fix_apple=self.apple)
                c = calendars[0]
                c.downloaded_at = timezone.now()
                c.content = content
                c.save()

            else:
                c = calendars[0]
                content = c.content

            conflicts = find_conflicts(content, start=startTime, end=endTime)


        except Exception as e:
            logger.critical(e)
            raise Exception('Provided link was invalid: {}'.format(self.link))

        conflictDictionaries = [
            {
                "name": e.summary,
                "start": e.start,
                "end": e.end,
                "description": e.description,
                "location": e.location
            } for e in conflicts
        ]

        return conflictDictionaries

    def create_event(self, name, startTime, endTime=None, description="",
                     location="", path=""):
        """Create an ics file containing a new event.
        Parameters:
        name (String) -- name of the event
        startTime (String) -- starting time of the event
        endTime (String) -- ending time of the event (default None
        description (String) -- description for the event (default '')
        location (String) -- location for the event (default '')
        Returns:
        String: path and name of the file the event is stored in
        """
        # NOTE(dzhang98): create a new calendar because using the current
        # calendar would have all the current events
        newCalendar = Calendar()
        newEvent = Event()

        newEvent.name = name
        newEvent.begin = startTime

        if endTime is not None:
            newEvent.end = endTime

        newEvent.description = description
        newEvent.location = location

        newCalendar.events.add(newEvent)

        # TODO: decide file path to store .ics files
        # TODO: decide name format that is human friendly and unique
        # Currently - event name + current time + '.ics'
        timestamp = datetime.datetime.now()
        filename = "%s%s-%s.ics" % (path, name, str(timestamp))
        # for event in newCalendar.events:
        #     print(event)
        with open(filename, 'w') as f:
            f.writelines(newCalendar)

        return filename
