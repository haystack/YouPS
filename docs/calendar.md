# Incorporating your schedule into email automation
<p align="right"><b>Dillon Zhang</b></p>

From [our need-finding study on email automation](https://dl.acm.org/citation.cfm?id=3300604), we found that email users would like their email to interface with their schedule. For instance, users stated they wanted to `highlight emails related to my current schedule`, `put "attending" emails in their calendar`, `make a career calendar out of emails containing applications`, and `calendars to ask for approval of the events before filling it in on the calendar.`

Calendars already have been tightly integrated into email. Calendar apps, such as [Google Calendar](https://www.google.com/calendar) and [Outlook](https://outlook.live.com), allow users to schedule events and forward events using email. [Calendly](https://calendly.com/) allows others to interact with a user’s calendar to coordinate scheduling easier. While these applications help users to access to their calendar easy from email, YouPS envisions smart inboxes where users can automate based on their schedule. 

With YouPS Calendar module, users can connect their calendar and work with additional context. This new module will allow users to connect to their calendars and use additional data, such as their availability and upcoming event, in their email automation process.

## Design Scenarios

#### Delaying emails to specific times

User Joon is a student who is frequently receiving emails during his class and is distracted by these emails. He does not want to turn off all notifications since he would miss emails when he was outside of class. Using YouPS with the Calendar Module, he is able to write the following.

```python
link = 'LINK TO CAL'
classCalendar = Calendar('My Classes', link)

# fired when a message arrives
def on_message(my_message):
    if classCalender.get_conflicts():
        my_message.add_flags("Check later")
        my_message.mark_read()  
```

#### Automating event recurring event invites

User Matt is part of the student group ESP. The event coordinator sends out a weekly email with all the events will occur that week with a following format:

```
Event: <Event Name> (<Start>, <End>):
Description

Event: <Event Name> (<Start>, <End>):
Description
```

Matt is an active member of the ESP community and would like to participate in as many events as he can. As a busy MIT student, he tends to have prior commitments. Currently, he checks each event against his calendar and adds it if there is no conflict. Using YouPS with the Calendar Module, he is able to write the following.

```python
link = 'LINK TO CAL'
classCalendar = Calendar('My Calendar', link)

# fired when a message arrives
def on_message(my_message):
    if my_message.subject == 'ESP This Week':
      events = {}
      lines = my_message.content["text"]
      for i in range(len(lines)):
        line = lines[i]
        if line[:6] == "Event:":
          name = line[7:line.find('(') - 1]
          start = line[line.find('(') + 1, line.find(',')]
          end = line[line.find(',') + 1, line.find(')')]
          description = lines[i+1]
          event = classCalendar.create_event(name, start, end, description)
          events[event] = len(classCalendar.get_conflicts(start, end)) == 0

      body = ""
      for event in events:
        body += "You are " + "not " * (!events[event]) + "available for " + event.name + "\n"

      send('ESP This Week Summary', "MATT's EMAIL ADDRESS", body)
```

## Design Goals
From our initial surveys and need finding, we discovered users would like the ability to connect their emails to third party contexts, such as their to-do lists and calendars. To address this need, we focused on connecting users to their calendars. We initially identified two main needs of users to accessing their calendars.

`Checking for availability` Users use their calendars to keep track of their availability. During our initial surveys, users wanted to be able to delay emails until they were available. Accessing the user’s calendar, we were able to check if there existed conflicting events during the time an email was received. Another use case for this capability was events emails. If the user received an invite to an event, they would be able to automatically check if they were already booked and by what event.

`Creating events` Upon receiving invites to events, users wanted to be able to add them to their calendar. By allowing users to create .ics files, we have given the user the ability to modify their calendar by adding the .ics file to their calendar. This makes the process easier for the user.

## Implementation
Calendars are important to users. This means that we need to gain the trust of users and ensure we would not damage their calendars. In order to do this, we access read only version of their calendars and provide .ics files for users to add to their calendars. This ensures that we cannot do any harm to their original calendars. We also ran into the issue of querying calendars too often and implemented a local cache for calendar data.

## Results
After user study, we found additional functionalities that users might need. 
`Finding availabilities` One of our tasks was to delay emails until they were available, users looked for an easy way to find their next availability. One user checked every minute to until he found a time he was available. The other two users just used the end time of the last conflict that was found. This did not account for events after that conflict. In order to address this need, we added additional functionality after the user study to return the next time their calendar said they were available.
