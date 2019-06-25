import os.path as path
import sys
import traceback
import logging
from django.core.management.base import BaseCommand, CommandError
from logging.handlers import RotatingFileHandler
import ConfigParser
import email
from time import sleep
from datetime import datetime, time
import imapclient 

from schema.youps import ImapAccount
from browser.imap import GoogleOauth2, authenticate

class Command(BaseCommand):
    args = ''
    help = 'Process email'

    # Auto-send messages to the given email address
    def handle(self, *args, **options):
		host = 'imap.gmail.com'
		ssl = 'True'
		username='kixlab.rally@gmail.com'
		folder = 'INBOX'

		# Setup the log handlers to stdout and file.
		log = logging.getLogger('imap_monitor')
		log.setLevel(logging.DEBUG)
		formatter = logging.Formatter(
			'%(asctime)s | %(name)s | %(levelname)s | %(message)s'
			)
		handler_stdout = logging.StreamHandler(sys.stdout)
		handler_stdout.setLevel(logging.DEBUG)
		handler_stdout.setFormatter(formatter)
		log.addHandler(handler_stdout)
		handler_file = RotatingFileHandler(
			'imap_monitor.log',
			mode='a',
			maxBytes=1048576,
			backupCount=9,
			encoding='UTF-8',
			delay=True
			)
		handler_file.setLevel(logging.DEBUG)
		handler_file.setFormatter(formatter)
		log.addHandler(handler_file)

		while True:
			# <--- Start of IMAP server connection loop
			
			# Attempt connection to IMAP server
			log.info('connecting to IMAP server - {0}'.format(host))
			try:
				imap_account = ImapAccount.objects.get(email=username)
				res = authenticate(imap_account)
				if not res['status']:
					return
					
				imap = res['imap']
			except Exception:
				# If connection attempt to IMAP server fails, retry
				etype, evalue = sys.exc_info()[:2]
				estr = traceback.format_exception_only(etype, evalue)
				logstr = 'failed to connect to IMAP server - '
				for each in estr:
					logstr += '{0}; '.format(each.strip('\n'))
				log.error(logstr)
				sleep(10)
				continue
			log.info('server connection established')

			# Select IMAP folder to monitor
			log.info('selecting IMAP folder - {0}'.format(folder))
			try:
				result = imap.select_folder(folder)
				log.info('folder selected')
			except Exception:
				# Halt script when folder selection fails
				etype, evalue = sys.exc_info()[:2]
				estr = traceback.format_exception_only(etype, evalue)
				logstr = 'failed to select IMAP folder - '
				for each in estr:
					logstr += '{0}; '.format(each.strip('\n'))
				log.critical(logstr)
				break
			
			# latest_seen_UID = None
			# # Retrieve and process all unread messages. Should errors occur due
			# # to loss of connection, attempt restablishing connection 
			# try:
			# 	result = imap.search('UNSEEN')
			# 	latest_seen_UID = max(result)
			# except Exception:
			# 	continue
			# log.info('{0} unread messages seen - {1}'.format(
			# 	len(result), result
			# 	))
			
			# for each in result:
				# try:
				# 	# result = imap.fetch(each, ['RFC822'])
				# except Exception:
				# 	log.error('failed to fetch email - {0}'.format(each))
				# 	continue
				# mail = email.message_from_string(result[each]['RFC822'])
				# try:
				# 	# process_email(mail, download, log)
				# 	log.info('processing email {0} - {1}'.format(
				# 		each, mail['subject']
				# 		))
				# except Exception:
				# 	log.error('failed to process email {0}'.format(each))
				# 	raise
				# 	continue
					
			while True:
				# <--- Start of mail monitoring loop
				
				# After all unread emails are cleared on initial login, start
				# monitoring the folder for new email arrivals and process 
				# accordingly. Use the IDLE check combined with occassional NOOP
				# to refresh. Should errors occur in this loop (due to loss of
				# connection), return control to IMAP server connection loop to
				# attempt restablishing connection instead of halting script.
				imap.idle()
				result = imap.idle_check(1)
				print (result)

				# check if there is any request from users
				# if diff folder:
				#	break
				

				# either mark as unread/read or new message
				if result:
					# EXISTS command mean: if the size of the mailbox changes (e.g., new messages)
					print (result)
					imap.idle_done()
					result = imap.search('UID %d' % result[0][2][1])
					log.info('{0} new unread messages - {1}'.format(
						len(result),result
						))
					for each in result:
						_header_descriptor = 'BODY.PEEK[HEADER.FIELDS (SUBJECT)]'
						fetch = imap.fetch(each, [_header_descriptor])
						# mail = email.message_from_string(
						# 	fetch[each][_header_descriptor]
						# 	)
						try:
							# process_email(mail, download, log)
							log.info('processing email {0} - {1}'.format(
								each, fetch[each]
								))
						except Exception:
							log.error(
								'failed to process email {0}'.format(each))
							raise
							continue
				else:
					imap.idle_done()
					imap.noop()
					log.info('no new messages seen')
				# End of mail monitoring loop --->
				continue
				
			# End of IMAP server connection loop --->
			break