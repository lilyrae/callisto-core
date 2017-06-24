from django.conf import settings
from django.contrib.sites.models import Site
from django.http import HttpResponse

from callisto_core.delivery.api import CallistoCoreMatchingApi
from callisto_core.delivery.wizard import EncryptedFormBaseWizard
from callisto_core.notification.api import CallistoCoreNotificationApi


class EncryptedFormWizard(EncryptedFormBaseWizard):

    def wizard_complete(self, report, **kwargs):
        return HttpResponse(report.id)


class SiteAwareNotificationApi(CallistoCoreNotificationApi):

    @classmethod
    def get_user_site(self, user):
        site = Site.objects.get(id=1)
        site.domain = 'testserver'
        site.save()
        return site


class CustomNotificationApi(SiteAwareNotificationApi):

    from_email = '"Custom" <custom@{0}>'.format(settings.APP_URL)
    report_filename = "custom_{0}.pdf.gpg"

    @classmethod
    def get_report_title(self):
        return 'Custom'


class ExtendedCustomNotificationApi(CustomNotificationApi):

    @classmethod
    def send_report_to_authority(arg1, arg2, arg3):
        pass


class CustomMatchingApi(CallistoCoreMatchingApi):

    @classmethod
    def process_new_matches(cls, matches, identifier):
        pass
