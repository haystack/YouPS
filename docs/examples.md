# Overview of the API

The object you will be interacting with most commonly is the `Message` object. Rules generally are run on one `Message` at a time, for example when a `Message` arrives in your inbox, or when a `Message` has a flag change.

A key thing to keep in mind about email messages is that they are mostly immutable. The only part of an email message that is mutable for most email systems is the flags and the folder that it is stored in. 

The `Message` object contains useful names for properties you would expect to find on an email, such as `to`, `from`, `bcc`, `cc`, `date` etc.... You can find documentation about these properties in the [api documentation](TODO insert link). 

Because most of these properties are immutable they return data. So to get the list of people a `Message` is sent to you can use `people = message.to`.  To add flags or remove flags you can use `message.add_flags(['your', 'flags']` and `message.remove_flags(['your', 'flags'])`. Using these methods will keep you completely compatible with most existing email software.

<!-- TODO we need to make it possible to set custom methods such as deadline using our API. -->

<!-- TODO might be useful to express flags as a custom list so people can use append pop etc... -->

<!-- TODO: what happened to the on flag changed -->

## Examples

#### Highlight Emails from Friends or Family

This example is useful for marking emails from a group of people, i.e. your coworkers, people working on a project, etc...

Tags: []

```python

# fired when a message arrives
def on_message(msg):
    friends = ["soya@example.com", "karger@example.com", "Amy Zhang"]
    if msg.sender in friends:
        msg.add_flags('MIT Friends')
    family = ["brother@example.com", "father@example.com", "mother@example.com"]
    if msg.sender in family:
        msg.add_flags(['Family', 'Important'])
```

----------

<!-- TODO: why does return_only_text in message.content also return the HTML?? -->

#### Add a flag to an email based on it's message contents

Useful for processing emails, shows how to access message contents and can be extended to do things like natural language processing.

Tags: []


```python
# fired when a message arrives
def on_message(msg):
    keywords = [ "NIH", "NSF", "OSP", "ISCB", "Proposal", "Review requests", "AAAS", "IEEE"]
    content = msg.content["text"]
    if any(keyword in content for keyword in keywords):
        msg.add_flags(["urgent", "work"])
```

----------

#### Mark an email as low priority if you have not read the last five emails from that sender and it is addressed to more than 10 people

This is useful for filtering out emails that come from mass mailing lists without missing out on the mailing lists you are actually interested in

Tags: []


```python
# fired when a message arrives
def on_message(msg):
    sender = message.from_
    prev_msgs = sender.recent_messages(5)
    recipients = message.to + msg.cc + msg.bcc
    if len(recipients) > 10 and all(not prev_msg.is_read):
        msg.add_flags('low priority')
```

----------

#### Archive unread messages marked as low priority after three days

This example is useful for maintaining a clean inbox. On gmail using the delete flag will simply archive the email. This rule requires that you set the delay for the on_message rule to three days

Tags: []


```python
# fired when a message arrives
def on_message(msg):
    if msg.has_flag('low priority') and not msg.is_read:
        msg.delete()
```

----------

#### If you've exchanged more than 10 emails with someone in one day mark any emails you get from them as urgent

This is helpful when you have a long email thread and want to make sure you are getting updates

Tags: []


```python
# fired when a message arrives
def on_message(msg):
    sender = message.from_
    last_ten_messages = sender.recent_messages(10)
    if all(m.date().date() == datetime.today().date() for m in last_ten_messages):
        m.priority("urgent")
```

----------