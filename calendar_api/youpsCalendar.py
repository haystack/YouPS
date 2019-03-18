from ics import Calendar, Event
from icalevents.icalevents import events
from icalevents.icalparser import normalize
import datetime


class YoupsCalendar:
    """Calendar Module for Youps."""

    def __init__(self, name, link):
        """Create a new YoupsCalendar instance.

        Parameters:
        name (String) -- the name of the character
        link (String) -- public ics link to the calendar

        """
        self.name = name
        self.link = link

    def get_conflicts(self, startTime, endTime=None, defaultInterval=datetime.timedelta(hours=1)):
        """Check the calendar to see if the specified time is available.

        Parameters:
        startTime (datetime) -- start of the time interval
        endTime (datetime) -- end of the time interval

        Returns:
        boolean: True if there are no conflicts within the time interval, False otherwise

        """
        if endTime is None:
            endTime = startTime + defaultInterval
        conflicts = events(self.link, start=startTime, end=endTime)
        return conflicts

    # TODO: Decide how to clean up new events (cronjob to delete)

    def create_event(self, name, startTime, endTime=None, description="", location="", path=""):
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
        newEvent.begin = normalize(startTime)

        if endTime is not None:
            newEvent.end = normalize(endTime)

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


if __name__ == "__main__":

    # 6.031 Public Calendar
    # link = 'https://calendar.google.com/calendar/ical/uh0pjuueg6973g214phtapbq3c%40group.calendar.google.com/public/basic.ics'
    # YOUPS Test Cal
    link = "https://calendar.google.com/calendar/ical/3ffpub8evedp0rkgvnubs5s3qk%40group.calendar.google.com/private-4250a5c9223e2fdeb9b64397e3944922/basic.ics",

    classCalendar = YoupsCalendar('Classe Test', link)

    # Test availablity
    noConflicts = classCalendar.get_conflicts(datetime.datetime(2019, 3, 18, 6, 30, 0), datetime.datetime(2019, 3, 18, 7, 30, 0))
    assert len(noConflicts) == 0
    print("is_available True - PASS")
    conflict = classCalendar.get_conflicts(datetime.datetime(2019, 3, 18, 10, 30, 0), datetime.datetime(2019, 3, 18, 11, 30, 0))
    assert len(conflict) == 2
    print("is_available False - PASS")
    # Test event
    # name = classCalendar.create_event("Available", "2019-03-04T14:00:00 -05:00", "2019-03-04T15:00:00 -05:00")
    # print("Event Created - " + name)
    #
    # name = classCalendar.create_event("Unavailable", "2019-03-04T12:00:00 -05:00", "2019-03-04T13:00:00 -05:00")
    # print("Event Created - " + name)
