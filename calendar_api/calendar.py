import ics
import requests
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
        self.source = link
        self.calendar = ics.Calendar(requests.get(link).text)
        self.timeline = self.calendar.timeline

    def is_available(self, startTime, endTime):
        """Check the calendar to see if the specified time is available.

        Parameters:
        startTime (String) -- start of the time interval
        endTime (String) -- end of the time interval

        Returns:
        boolean: True if there are no conflicts within the time interval, False otherwise

        """
        conflicts = self.timeline.overlapping(startTime, endTime)
        return len(conflicts) == 0

    # TODO: Decide how to clean up new events (cronjob to delete)

    def create_event(self, name, startTime, endTime=None, description="", location=""):
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
        newCalendar = ics.Calendar()
        newEvent = ics.Event()

        newEvent.name = name
        newEvent.startTime = startTime

        if endTime is not None:
            newEvent.endTime = endTime

        newEvent.description = description
        newEvent.location = location

        newCalendar.events.add(newEvent)

        # TODO: decide file path to store .ics files
        # TODO: decide name format that is human friendly and unique
        # Currently - event name + current time + '.ics'
        path = ""
        timestamp = datetime.datetime.now()
        filename = "%s%s-%s.ics" % (path, name, str(timestamp))
        with open(filename, 'w') as f:
            f.writelines(newCalendar)

        return filename
