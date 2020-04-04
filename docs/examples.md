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

#### Set a reminder for urgent messages

When a message arrives, if the message is urgent (a message with an urgent flag), move it to the Inbox folder, and send me a reminder of it every 6 house. Otherwise, move the message to my otherEmails folder.

Tags: []

```python
# fired when a message arrives
def on_message(my_message):
    import datetime
    if my_message.has_label('urgent'):
        my_message.move("inbox")
        my_message.deadline = datetime.datetime.now() + datetime.timedelta(hours=6)
    else:
        my_message.move("anotherFolder")

# fired when a message.deadline is up
def on_deadline(my_message):
    import datetime
    if my_message.has_label('urgent'):
        # if still urgent, update deadline to 6 hours later
        my_message.deadline = datetime.datetime.now() + datetime.timedelta(hours=6)        
    else:
        my_message.move("anotherFolder")								
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
    def checkImportance(msg):
        if msg.has_label('low priority'):
            msg.delete()
            
    import datetime
    later = datetime.datetime.now() + datetime.timedelta(days=3)
    my_message.on_time(checkImportance, later)
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

#### Aggregate Messages

Aggregate all messages with event dates into a one message with the date and subject of each message.

Tags: []

```python
# fired when a message arrives
def on_message(my_message):
    msg_subject = 'my current schedule'
    msgs = []
    if my_message.extract_time_entity():
       	msgs = ME.messages_from()
        print(msgs)
        
    	old_msg = None
    	msgs.reverse()
    	for m in msgs:
     		if m.subject == msg_subject:
           		old_msg = m
           		break
        # append a new schedule
    	new_content = "%s: %s \n" %(my_message.subject,my_message.extract_time_entity()[0]['start']) 	
        if old_msg:
            new_content += old_msg.content['text']
    	send(to=ME, subject=msg_subject, body=new_content)
							
```
----------

#### Make your email as chatbot

Tags: [auto response, draft]


```python
# fired when a message arrives
def on_message(my_message):
    from chatterbot import ChatBot
    from chatterbot.trainers import ListTrainer

    chatterbot = ChatBot("My chatbot")
    chatterbot.set_trainer(ListTrainer)
    
    chatterbot.train([
        "Are you busy now?",
        "I'm busy",
    	"How are you?",
    	"I am good.",
    	"That is good to hear.",
    	"Thank you",
    	"You are welcome.",
    ])
    
    r = chatterbot.get_response(my_message.extract_response())
    print(str(r))
    create_draft('Re: '+ my_message.subject, content=str(r))
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
