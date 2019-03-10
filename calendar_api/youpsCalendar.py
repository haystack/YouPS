from ics import Calendar, Event
import requests
import datetime
import arrow


class YoupsCalendar:
    """Calendar Module for Youps."""

    def __init__(self, name, link):
        """Create a new YoupsCalendar instance.

        Parameters:
        name (String) -- the name of the character
        link (String) -- public ics link to the calendar

        """
        self.name = name
        self.source = link

        clean = self.get_and_clean_cal(link)
        # print(clean)
        self.calendar = Calendar(clean)

        self.timeline = self.calendar.timeline

    def get_and_clean_cal(self, link):
        """Request and clean calendar data.

        Parameters:
        link (String) -- public ics link to the calendar

        Returns:
        String: ics representation of calendar

        """
        source = requests.get(link).text
        print(source)
        # Remove VALARMS from the calendar
        while 'VALARM' in source:
            begin = source.find('BEGIN:VALARM')
            end = source.find('END:VALARM') + len('END:VALARM') + 2
            source = source[:begin] + source[end:]

        return source

    def is_available(self, startTime, endTime):
        """Check the calendar to see if the specified time is available.

        Parameters:
        startTime (String) -- start of the time interval
        endTime (String) -- end of the time interval

        Returns:
        boolean: True if there are no conflicts within the time interval, False otherwise

        """
        # TODO: Find solution for reccuring events
        conflicts = [conflict for conflict in self.timeline.overlapping(arrow.get(startTime), arrow.get(endTime)) if not conflict.all_day]
        return len(conflicts) == 0

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


if __name__ == "__main__":

    # 6.031 Public Calendar
    # link = 'https://calendar.google.com/calendar/ical/uh0pjuueg6973g214phtapbq3c%40group.calendar.google.com/public/basic.ics'
    # YOUPS Test Cal
    link = 'https://calendar.google.com/calendar/ical/pj6gli5rhicds2hqp5jgl1k9ik%40group.calendar.google.com/public/basic.ics'

    classCalendar = YoupsCalendar('YouPS Test', link)

    # Test availablity
    assert classCalendar.is_available("2019-03-04T08:00:00-05:00", "2019-03-04T09:00:00-05:00")
    print("is_available True - PASS")
    assert (not classCalendar.is_available("2019-03-04T11:00:00-05:00", "2019-03-04T13:00:00-05:00"))
    print("is_available False - PASS")
    # Test event
    name = classCalendar.create_event("Available", "2019-03-04T14:00:00 -05:00", "2019-03-04T15:00:00 -05:00")
    print("Event Created - " + name)

    name = classCalendar.create_event("Unavailable", "2019-03-04T12:00:00 -05:00", "2019-03-04T13:00:00 -05:00")
    print("Event Created - " + name)
