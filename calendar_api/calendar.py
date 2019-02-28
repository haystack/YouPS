import ics

class YoupsCalendar:

    def YoupsCalendar(name, link):
        self.name = name
        self.source = link


    def is_available(startTime, endTime):
        pass


    ## TODO: Decide how to clean up new events (cronjob to delete, remove after attaching)
    def createEvent(name, startTime, endTime = None, description = "", location = ""):
        pass
