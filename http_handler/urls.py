from django.conf.urls import patterns, include, url
from django.contrib.auth import views as auth_views
from django.views.generic.base import TemplateView
from browser.views import murmur_acct
from http_handler.settings import WEBSITE
from registration.backends.default.views import ActivationView
from registration.forms import MurmurPasswordResetForm
# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

website_context = {'website': WEBSITE}
urlpatterns = patterns('')
shared_patterns = [
    url(r'^$', 'browser.views.index'),
    url(r'^lamson_status', 'browser.views.lamson_status'),
    url(r'^settings', 'browser.views.settings'),
    url(r'^404', 'browser.views.error'),

    url(r'^login_imap_callback', 'browser.views.login_imap_callback'),

    # override the registration default urls - bug with django 1.6
    url(r'^accounts/password/change/$',
        murmur_acct,
        {'acct_func': auth_views.password_change,
         'template_name': 'registration/password_change_form.html'},
        name='password_change',
        ),
    url(r'^accounts/password/change/done/$',
        murmur_acct,
        {'acct_func': auth_views.password_change_done,
         'template_name': 'registration/password_change_done.html'},
        name='password_change_done',
        ),
    url(r'^accounts/password/reset/$',
        auth_views.password_reset,
        {'password_reset_form': MurmurPasswordResetForm,
         'extra_context': website_context},
        name='password_reset'),
    url(r'^accounts/password/reset/done/$',
        auth_views.password_reset_done,
        {'extra_context': website_context},
        name='password_reset_done'),
    url(r'^accounts/password/reset/complete/$',
        auth_views.password_reset_complete,
        {'extra_context': website_context},
        name='password_reset_complete'),
    url(r'^accounts/password/reset/confirm/(?P<uidb64>[0-9A-Za-z]+)-(?P<token>.+)/$',
        auth_views.password_reset_confirm,
        {'extra_context': website_context},
        name='password_reset_confirm'),

    url(r'^accounts/activate/complete/$',
        TemplateView.as_view(
            template_name='registration/activation_complete.html'),
        website_context,
        name='registration_activation_complete',
        ),

    url(r'^accounts/activate/(?P<activation_key>\w+)/$',
        ActivationView.as_view(),
        name='registration_activate',
        ),

    url(r'^accounts/register/complete/$',
        TemplateView.as_view(
            template_name='registration/registration_complete.html'),
        website_context,
        name='registration_complete',
        ),

    url(r'^accounts/',
        include('registration.backends.default.urls')),

    # mailbot
    url(r'^editor', 'browser.views.login_imap_view'),
    url(r'^docs', 'browser.views.docs_view'),
    url(r'^about', 'browser.views.about_view'),
    url(r'^calendar', 'browser.views.calendar_view'),
    url(r'^button', 'browser.views.email_button_view'),
    url(r'^privacy', 'browser.views.privacy_view'),
    url(r'^login_imap', 'browser.views.login_imap'),
    url(r'^load_new_editor', 'browser.views.load_new_editor'),
    url(r'^remove_rule', 'browser.views.remove_rule'),
    url(r'^run_mailbot', 'browser.views.run_mailbot'),
    url(r'^run_simulate_on_messages', 'browser.views.run_simulate_on_messages'),
    url(r'^save_shortcut', 'browser.views.save_shortcut'),

    url(r'^email_rule_meta', 'browser.views.get_email_rule_meta'),
    
                    
    url(r'^apply_button_rule', 'browser.views.apply_button_rule'),                
    url(r'^create_mailbot_mode', 'browser.views.create_mailbot_mode'),
    url(r'^delete_mailbot_mode', 'browser.views.delete_mailbot_mode'),
    url(r'^fetch_execution_log', 'browser.views.fetch_execution_log'),
    url(r'^fetch_watch_message', 'browser.views.fetch_watch_message'),
    url(r'^folder_recent_messages', 'browser.views.folder_recent_messages'),
    url(r'^load_components', 'browser.views.load_components'),
    url(r'^watch_current_message', 'browser.views.handle_imap_idle'),
]

urlpatterns.extend(shared_patterns)
