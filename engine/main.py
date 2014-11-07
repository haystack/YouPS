import sys, logging, base64, email, datetime
from schema.models import *
from msg_codes import *
from django.utils.timezone import utc
from django.db.models import Q
from browser.util import password_generator
from lamson.mail import MailResponse
from smtp_handler.utils import relay_mailer
from cgi import escape


'''
MailX Main Controller

@author: Anant Bhardwaj
@date: Oct 20, 2012
'''

def list_groups(user):
	res = {'status':False}
	try:
		groups = Group.objects.filter(members__in=[user], active=True)
		res['status'] = True
		res['groups'] = []
		for g in groups:
			admin = False
			mod = False
			if g.admins.filter(email=user.email).count() > 0:
				admin = True
			if g.moderators.filter(email=user.email).count() > 0:
				mod = True
			
			res['groups'].append({'name':g.name, 'member': True, 'admin': admin, 'mod': mod})
			
		pub_groups = Group.objects.filter(Q(public=True, active=True), ~Q(members__in=[user]))
		for g in pub_groups:
			res['groups'].append({'name':g.name,  'member': False, 'admin': False, 'mod': False})
			
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res
	


def create_group(group_name, public, requester):
	res = {'status':False}
	try:
		group = Group.objects.get(name=group_name)
		res['code'] = msg_code['DUPLICATE_ERROR']
	except Group.DoesNotExist:
		group = Group(name=group_name, active=True, public=public)
		group.save()
		
		group.admins.add(requester)
		group.moderators.add(requester)
		group.members.add(requester)
		group.save()
		
		res['status'] = True
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res




def activate_group(group_name, user):
	res = {'status':False}
	try:
		group = Group.objects.get(name=group_name)
		if group.admins.filter(email=user.email).count() > 0:
			group.active = True
			group.save()
			res['status'] = True
		else:
			res['code'] = msg_code['PRIVILEGE_ERROR']
	except Group.DoesNotExist:
		res['code'] = msg_code['GROUP_NOT_FOUND_ERROR']
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res





def deactivate_group(group_name, user):
	res = {'status':False}
	try:
		group = Group.objects.get(name=group_name)
		if group.admins.filter(email=user.email).count() > 0:
			group.active = False
			group.save()
			res['status'] = True
		else:
			res['code'] = msg_code['PRIVILEGE_ERROR']
	except Group.DoesNotExist:
		res['code'] = msg_code['GROUP_NOT_FOUND_ERROR']
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res




def add_members(group_name, emails, user):
	res = {'status':False}
	
	try:
		group = Group.objects.get(name=group_name)
		
		if group.admins.filter(email=user.email).count() > 0:
			res['status'] = True
			email_list = emails.strip().lower().split(',')
			for email in email_list:
				email = email.strip()
				
				mail = MailResponse(From = 'help@mailx.csail.mit.edu', 
									To = email, 
									Subject  = "You've been subscribed to %s Mailing List" % (group_name))
				
				email_user = UserProfile.objects.filter(email=email)
				if email_user.count() == 1:
					group.members.add(email_user[0])
					
					message = "You've been subscribed to %s Mailing List. <br />" % (group_name)
					message += "To see posts from this list, visit <a href='http://mailx.csail.mit.edu/posts?group_name=%s'>http://mailx.csail.mit.edu/posts?group_name=%s</a><br />" % (group_name, group_name)
					message += "To manage your mailing lists, subscribe, or unsubscribe from groups, visit <a href='http://mailx.csail.mit.edu/groups'>http://mailx.csail.mit.edu/groups</a><br />"
				else:
					pw = password_generator()
					new_user = UserProfile.objects.create_user(email, pw)
					group.members.add(new_user)
					
					message = "You've been subscribed to %s Mailing List. <br />" % (group_name)
					message += "An account has been created for you at <a href='http://mailx.csail.mit.edu'>http://mailx.csail.mit.edu</a><br />"
					message += "Your username is your email, which is %s and your auto-generated password is %s <br />" % (email, pw)
					message += "If you would like to change your password, please log in at the link above and then you can change it under your settings. <br />"
					message += "To see posts from this list, visit <a href='http://mailx.csail.mit.edu/posts?group_name=%s'>http://mailx.csail.mit.edu/posts?group_name=%s</a><br />" % (group_name, group_name)
					message += "To manage your mailing lists, subscribe, or unsubscribe from groups, visit <a href='http://mailx.csail.mit.edu/groups'>http://mailx.csail.mit.edu/groups</a><br />"

				mail.Html = message
				logging.debug('TO LIST: ' + str(email))
				
				relay_mailer.deliver(mail, To = [email])
					
		else:
			res['code'] = msg_code['PRIVILEGE_ERROR']
	except Group.DoesNotExist:
		res['code'] = msg_code['GROUP_NOT_FOUND_ERROR']
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res




def subscribe_group(group_name, user):
	res = {'status':False}

	try:
		group = Group.objects.get(name=group_name)
		if group.members.filter(email=user.email).count() > 0:
			user.active=True
			user.save()
			res['status'] = True
		else:
			group.members.add(user)
			res['status'] = True
	except Group.DoesNotExist:
		res['code'] = msg_code['GROUP_NOT_FOUND_ERROR']
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res




def unsubscribe_group(group_name, user):
	res = {'status':False}
	try:
		group = Group.objects.get(name=group_name)
		group.members.remove(user)
		res['status'] = True
	except Group.DoesNotExist:
		res['code'] = msg_code['GROUP_NOT_FOUND_ERROR']
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res




def group_info(group_name, user):
	res = {'status':False}
	try:
		group = Group.objects.get(name=group_name)
		
		members = group.members.all()
		res['status'] = True
		res['group_name'] = group_name
		res['active'] = group.active
		res['members'] = []
		for member in members:

			admin = False
			mod = False
			if group.admins.filter(email=member.email).count() > 0:
				admin = True
			if group.moderators.filter(email=member.email).count() > 0:
				mod = True
			
			if user.email == member.email:
				res['admin'] = admin
				res['moderator'] = mod
				res['subscribed'] = member.is_active
			
			member_info = {'email': member.email, 
						   'group_name': group_name, 
						   'admin': admin, 
						   'member': True, 
						   'moderator': mod, 
						   'active': member.is_active}
			
			res['members'].append(member_info)
	except Group.DoesNotExist:
		res['code'] = msg_code['GROUP_NOT_FOUND_ERROR']	
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res


def format_date_time(d):
	return datetime.datetime.strftime(d, '%Y/%m/%d %H:%M:%S')

def list_posts(group_name=None, timestamp_str = None):
	res = {'status':False}
	try:
		t = datetime.datetime.min
		if(timestamp_str):
			t = datetime.datetime.strptime(timestamp_str, '%Y/%m/%d %H:%M:%S')
		t = t.replace(tzinfo=utc, second = t.second + 1)
		
		if (group_name != None):
			g = Group.objects.filter(name=group_name)
			threads = Thread.objects.filter(timestamp__gt = t, group = g)
		else:
			threads = Thread.objects.filter(timestamp__gt = t)
		res['threads'] = []
		for t in threads:
			following = Following.objects.filter(thread = t)
			f_list = [f.user.email for f in following]
			posts = Post.objects.filter(thread = t)		
			replies = []
			post = None
			for p in posts:
				if(not p.reply_to_id):
					post = {'msg_id':p.msg_id, 'thread_id':p.thread_id, 'from':p.author.email, 'to':p.group.name, 'subject': escape(p.subject), 'text': escape(p.post), 'timestamp':format_date_time(p.timestamp)}
				else:
					replies.append({'msg_id':p.msg_id, 'thread_id':p.thread_id, 'from':p.author.email, 'to':p.group.name, 'subject': escape(p.subject), 'text': escape(p.post), 'timestamp':format_date_time(p.timestamp)})
			res['threads'].append({'thread_id':t.id, 'post':post, 'replies': replies, 'f_list':f_list, 'timestamp':format_date_time(t.timestamp)})
			res['status'] = True
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res
	

def load_post(group_name, thread_id, msg_id):
	res = {'status':False}
	try:
		t = Thread.objects.get(id=thread_id)
		p = Post.objects.get(msg_id=msg_id, thread= t)
		res['status'] = True
		res['msg_id'] = p.msg_id
		res['thread_id'] = p.thread_id
		res['from'] = p.email
		res['subject'] = escape(p.subject)
		res['text'] = escape(p.post)
		res['to'] = p.group.name
	except Thread.DoesNotExist:
		res['code'] = msg_code['THREAD_NOT_FOUND_ERROR']
	except Post.DoesNotExist:
		res['code'] = msg_code['POST_NOT_FOUND_ERROR']
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res


def insert_post(group_name, subject, message_text, user):
	res = {'status':False}
	thread = None
	try:
		
		group = Group.objects.get(name=group_name)
		group_members = group.members.all()
		
		recipients = [m.email for m in group_members]
		
		thread = Thread()
		thread.subject = subject
		thread.group = group
		thread.save()
		
		msg_id = base64.b64encode(user.email + str(datetime.datetime.now())).lower() + '@mailx.csail.mit.edu'
		
		p = Post(msg_id=msg_id, author=user, subject=subject, post=str(message_text), group=group, thread=thread)
		p.save()
		
		f = Following(user=user, thread=thread)
		f.save()
		
		res['status'] = True
		res['msg_id'] = msg_id
		res['thread_id'] = thread.id
		res['recipients'] = recipients

	except Group.DoesNotExist:
		res['code'] = msg_code['GROUP_NOT_FOUND_ERROR']
	except:
		if(thread):
			thread.delete()
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res
	


def insert_reply(group_name, subject, message_text, user, thread_id=None):
	res = {'status':False}
	try:
		group = Group.objects.get(name=group_name)
		
		orig_post_subj = subject[4:]
		
		post = Post.objects.filter(Q(subject=orig_post_subj) | Q(subject=subject)).order_by('-timestamp')[0]
		if not thread_id:
			thread = Thread.objects.filter(subject=orig_post_subj).order_by('-timestamp')[0]
		else:
			thread = Thread.objects.get(id=thread_id)
		msg_id = base64.b64encode(user.email + str(datetime.datetime.now())).lower() + '@mailx.csail.mit.edu'
		
		r = Post(msg_id=msg_id, author=user, subject=subject, post = str(message_text), reply_to=post, group=group, thread=thread)
		r.save()
		
		thread.timestamp = datetime.datetime.now().replace(tzinfo=utc)
		thread.save()
		
		following = Following.objects.filter(thread=thread)
		recipients = [f.user.email for f in following]
		res['status'] = True
		res['recipients'] = recipients
		res['thread_id'] = thread.id
		res['msg_id'] = msg_id
		
	except Group.DoesNotExist:
		res['code'] = msg_code['GROUP_NOT_FOUND_ERROR']
	except Post.DoesNotExist:
		res['code'] = msg_code['POST_NOT_FOUND_ERROR']
	except:
		print sys.exc_info()
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res




def follow_thread(thread_id, user):
	res = {'status':False}
	t = None
	try:
		t = Thread.objects.get(id=thread_id)
		f = Following.objects.get(thread=t, user=user)
		res['status'] = True
	except Following.DoesNotExist:
		f = Following(thread=t, user=user)
		f.save()
		res['status'] = True
	except Thread.DoesNotExist:
		res['code'] = msg_code['THREAD_NOT_FOUND_ERROR']
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res





def unfollow_thread(thread_id, user):
	res = {'status':False}
	try:
		t = Thread.objects.get(id=thread_id)
		f = Following.objects.get(thread=t, user=user)
		f.delete()
		res['status'] = True
	except Following.DoesNotExist:
		res['status'] = True
	except Thread.DoesNotExist:
		res['code'] = msg_code['THREAD_NOT_FOUND_ERROR']
	except:
		res['code'] = msg_code['UNKNOWN_ERROR']
	logging.debug(res)
	return res











