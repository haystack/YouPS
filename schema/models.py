from django.contrib.auth.models import BaseUserManager, AbstractBaseUser, User
from django.core.mail import send_mail
from django.db import models
from django.utils.http import urlquote
from jsonfield import JSONField
from oauth2client.django_orm import FlowField, CredentialsField

from http_handler import settings
from http_handler.settings import AUTH_USER_MODEL

from schema.youps import ImapAccount

class MyUserManager(BaseUserManager):
	def create_user(self, email, password=None):
		"""
        Creates and saves a User with the given email and password.
        """
		if not email:
			raise ValueError('Users must have an email address')

		user = self.model(email=self.normalize_email(email))

		user.set_password(password)
		user.save(using=self._db)
		return user

	def create_superuser(self, email, password):
		"""
        Creates and saves a superuser with the given email and password.
        """
		user = self.create_user(email,
            password=password
        )
		user.is_admin = True
		user.save(using=self._db)
		return user


class UserProfile(AbstractBaseUser):
	email = models.EmailField(
        verbose_name='email address',
        max_length=191,
        unique=True,
    )
	first_name = models.CharField('first name', max_length=30, blank=True)
	last_name = models.CharField('last name', max_length=30, blank=True)
	is_active = models.BooleanField(default=True)
	is_admin = models.BooleanField(default=False)
	date_joined = models.DateTimeField(auto_now=True)
	hash = models.CharField(max_length=40, default="")

	imap_account = models.ForeignKey('ImapAccount', null=True, blank=True)


	objects = MyUserManager()

	USERNAME_FIELD = 'email'

	def get_full_name(self):
		"""
        Returns the first_name plus the last_name, with a space in between.
        """
		full_name = '%s %s' % (self.first_name, self.last_name)
		return full_name.strip()

	def get_short_name(self):
		"Returns the short name for the user."
		return self.first_name

	def email_user(self, subject, message, from_email=None):
		"""
        Sends an email to this User.
        """	
		from smtp_handler.utils import relay_mailer
		relay_mailer.send(self.email, from_email, subject, message)

	def has_perm(self, perm, obj=None):
		"Does the user have a specific permission?"
		return True

	def has_module_perms(self, app_label):
		"Does the user have permissions to view the app `app_label`?"
		return True

	@property
	def is_staff(self):
		"Is the user a member of staff?"
		return self.is_admin

class Attachment(models.Model):
	id = models.AutoField(primary_key=True)
	msg_id = models.CharField(max_length=120)
	hash_filename = models.TextField(max_length=40)
	true_filename = models.TextField()
	content_id = models.CharField(max_length=120, null=True)
	timestamp = models.DateTimeField(auto_now=True)

	class Meta:
		db_table = "murmur_attachments"
		ordering = ["timestamp"]

class FlowModel(models.Model):
    id = models.ForeignKey(AUTH_USER_MODEL, primary_key=True)
    flow = FlowField()

class CredentialsModel(models.Model):
    id = models.ForeignKey(AUTH_USER_MODEL, primary_key=True)
    credential = CredentialsField()