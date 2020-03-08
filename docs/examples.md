# Overview of the API

The object you will be interacting with most commonly is the `Message` object. Rules generally are run on one `Message` at a time, for example when a `Message` arrives in your inbox, or when a `Message`'s deadline is up. 

The `Message` object contains useful names for properties you would expect to find on an email, such as `to`, `from`, `bcc`, `cc`, `date`, `deadline` etc.... You can find documentation about these properties in the [api documentation](/docs). 

<!-- TODO we need to make it possible to set custom methods such as deadline using our API. -->

<!-- TODO might be useful to express flags as a custom list so people can use append pop etc... -->

<!-- TODO: what happened to the on flag changed -->

## Examples

#### Archive Unimportant Messages

When a  message arrives you can archive it immediately. You want to make sure that this rule is running on inbox and important at the very least.

Tags: [archive, inbox zero]

```python
# fired when a message arrives
def on_message(my_message):
    if my_message.sender == "someone_spammy@example.com":
        print('archiving', my_message)
        my_message.delete()
								
```

----------

#### Set a deadline for a certain message using YouPS shortcut

Set a deadline of a message within your email interface. Forward a message you want to add a deadline with a content. Then, YouPS parse the content with a NLP library. 

Tags: [YouPS command]


```python
# fired when you forward a message to YoUPS. 
def on_command(my_message, kargs):
    # you should set a datetime type argument
    my_message.deadline = kargs['deadline']
```

----------

#### Highlight Emails from Friends or Family

This example is useful for marking emails from a group of people, i.e. your coworkers, people working on a project, etc...

Tags: [gmail]

```python
# fired when a message arrives
def on_message(my_message):
    friends = ["soya@example.com", "karger@example.com", "Amy Zhang"]
    if my_message.sender in friends:
        my_message.add_labels('MIT Friends')
    family = ["brother@example.com", "father@example.com", "mother@example.com"]
    if my_message.sender in family:
        my_message.add_labels(['Family', 'Important'])
```

----------

<!-- TODO: why does return_only_text in message.content also return the HTML?? -->

#### Add a flag to an email based on it's message contents

Useful for processing emails, shows how to access message contents and can be extended to do things like natural language processing.

Tags: [gmail]


```python
# fired when a message arrives
def on_message(my_message):
    keywords = [ "NIH", "NSF", "OSP", "ISCB", "Proposal", "Review requests", "AAAS", "IEEE"]
    if any(my_message.contains(keyword) for keyword in keywords):
        my_message.add_labels(["urgent", "work"])
```

----------

#### Mark an email read if you have not read the last five emails from that sender and it is addressed to more than 10 people

This is useful for filtering out emails that come from mass mailing lists without missing out on the mailing lists you are actually interested in

Tags: []


```python
# fired when a message arrives
def on_message(my_message):
    prev_msgs = my_message.sender.messages_from(5)
    if len(my_message.recipients) > 10 and all(not p.is_read for p in prev_msgs):
        my_message.mark_read()
	my_message.add_labels("low priority") # if gmail
```

----------

#### Archive unread messages marked as low priority after three days

This example is useful for maintaining a clean inbox. On gmail using the delete flag will simply archive the email. This rule requires that you set the delay for the on_message rule to three days

Tags: [inbox zero, gmail]


```python
# fired when a message arrives
def on_message(my_message):
    if my_message.has_label('low priority') and not my_message.is_read:
        my_message.delete()
```

----------

#### If you've exchanged more than 10 emails with someone in one day mark any emails you get from them as urgent

This is helpful when you have a long email thread and want to make sure you are getting updates

Tags: [priority]


```python
# fired when a message arrives
def on_message(my_message):
    from datetime import datetime
    last_ten_messages = my_message.sender.messages(10)
    if all(my_message.date.date() == datetime.today().date() for m in last_ten_messages):
        my_message.priority = "urgent"
```

----------

#### Archive/Delete Gmail Message

This example is useful when you want to emulate Gmail's archive feature or send a gmail message to the trash. Gmail will retain any deleted messages for 30 days after the message is deleted. Gmail will retain archived messages forever but they are only accessible through search. **Note** In order for this to work properly the rule must be run on any folder the email will appear in. Usually you will want to run this on 'Inbox' and 'Important' but if you want to send emails to yourself for testing you will want to run this on 'Sent Mail' as well.

Tags: [gmail, trash, archive]

```python

# set delete_permanently to True to actually delete the message
# set delete_permanently to False to archive the message (this is the default)
def archive_gmail(msg, delete_permanently=False):
    msg.remove_flags(['\\Inbox', '\\Important'])
    if delete_permanently:
        msg.add_flags(['\\Trash'])

# fired when a message arrives
def on_message(my_message):
    # this archives any message which contains tonight in the subject
    if "[tonight]" in my_message.subject.lower():
        archive_gmail(my_message, True)		
```

----------


### Add Your Own Examples

You can add examples [here](https://github.com/soyapark/murmur/edit/master/docs/examples.md). If you don't have access rights to the repository fork the repository and create a pull request. Or submit an issue containing your example.

We suggest using the following template for your examples.


    #### Example Title
    
    Example Description
    
    Tags: []
    
    ```python
    # fired when a message arrives
    def on_message(msg):
    pass
    
    # fired when a deadline occurs on a message
    def on_deadline(msg):
    pass
    
    # fired when you use YouPS command or send an email to rule_name@youps.csail.mit.edu
    def on_command(msg):
    pass
    ```
    
    ----------
