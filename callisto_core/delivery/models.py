import json
import logging
import uuid

from nacl.exceptions import CryptoError

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string

from . import hashers, model_helpers, security, utils

logger = logging.getLogger(__name__)


class Report(models.Model):
    '''The full text of a reported incident.'''

    # standard fields
    submitted_to_school = models.DateTimeField(blank=True, null=True)
    contact_phone = models.CharField(blank=True, null=True, max_length=256)
    contact_voicemail = models.TextField(default=True)
    contact_email = models.EmailField(blank=True, null=True, max_length=256)
    contact_notes = models.TextField(default='No Preference')
    contact_name = models.TextField(blank=True, null=True)
    match_found = models.BooleanField(default=False)

    # autogenerated fields
    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    added = models.DateTimeField(auto_now_add=True)
    last_edited = models.DateTimeField(null=True)

    # encryption fields
    encrypted = models.BinaryField(blank=True)
    encrypted_eval = models.BinaryField(blank=True)
    # <algorithm>$<iterations>$<salt>$
    encode_prefix = models.TextField(null=True)
    salt = models.TextField(null=True)  # used for backwards compatibility

    # foreign keys
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True)

    def __str__(self):
        return 'Record(uuid={})'.format(self.uuid)

    @property
    def entered_into_matching(self):
        first_match_report = self.matchreport_set.first()
        if first_match_report:
            return first_match_report.added
        else:
            return None

    def encrypt_record(
        self,
        record_data: dict,
        passphrase: str,
    ) -> None:
        '''Encrypts and saves record data, in two formats'''
        self._store_for_user_decryption(record_data, passphrase)
        self._store_for_callisto_decryption(record_data)
        self.save()

    def decrypt_record(
        self,
        passphrase: str,  # aka secret key aka passphrase
    ) -> dict or str:
        '''decrypts record text from record.encrypted, with the passphrase'''
        if not (self.encode_prefix or self.salt):
            key = self.encryption_setup(passphrase)
        else:
            _, key = hashers.make_key(
                self.encode_prefix, passphrase, self.salt)

        record_data_string = security.decrypt_text(key, self.encrypted)

        try:
            decrypted_data = json.loads(record_data_string)
            return self._return_or_transform(decrypted_data, passphrase)
        except json.decoder.JSONDecodeError:
            logger.info('decrypting legacy report')
            return record_data_string

    def withdraw_from_matching(self):
        '''Deletes all associated MatchReports'''
        self.matchreport_set.all().delete()
        self.match_found = False
        self.save()

    def encryption_setup(self, passphrase):
        '''Generates and stores a random salt'''
        if self.salt:
            self.salt = None
        hasher = hashers.get_hasher()
        encoded = hasher.encode(passphrase, get_random_string())
        self.encode_prefix, key = hasher.split_encoded(encoded)
        self.save()
        return key

    def save(self, *args, **kwargs):
        ''' On save, update timestamps '''
        self.last_edited = timezone.now()
        return super().save(*args, **kwargs)

    def _return_or_transform(
        self,
        data: list or dict,
        key: str,  # aka secret key aka passphrase
    ) -> dict:
        '''
        given a set of data in old list or new dict format, return
        the data in the new dict format.

        and save the new data if it was in the old list format
        '''
        if isinstance(data, list):
            new_data = utils.RecordDataUtil.transform_if_old_format(data)
            self.encrypt_record(new_data, key)
            return new_data
        else:
            return data

    def _store_for_user_decryption(
        self,
        record_data: dict,
        passphrase: str,
    ):
        '''
        store user decryptable data and 500 the request on fails
        '''
        key = self.encryption_setup(passphrase)
        self.encrypted = security.encrypt_text(key, json.dumps(record_data))

    def _store_for_callisto_decryption(
        self,
        record_data: dict,
    ):
        '''
        store callisto decryptable data and ignore fails
        filters out skip_eval fields before storing
        '''
        try:
            filtered_data = model_helpers.filter_record_data(record_data)
            encrypted_answers = model_helpers.gpg_encrypt_data(
                data=filtered_data,
                key=settings.CALLISTO_EVAL_PUBLIC_KEY,
            )
            self.encrypted_eval = encrypted_answers
            RecordHistorical.objects.create(
                record=self, encrypted_eval=encrypted_answers)
        except BaseException as error:
            logger.exception(error)

    class Meta:
        ordering = ('-added',)


class RecordHistorical(models.Model):
    '''for saving the change in record eval data over time'''
    record = models.ForeignKey(Report, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    encrypted_eval = models.BinaryField(null=True)


class MatchReport(models.Model):
    '''
    A report that indicates the user wants to submit if a match is found.
    A single report can have multiple MatchReports--one per perpetrator.
    '''
    report = models.ForeignKey(Report, on_delete=models.CASCADE)
    added = models.DateTimeField(auto_now_add=True)
    encrypted = models.BinaryField(null=False)

    # <algorithm>$<iterations>$<salt>$
    encode_prefix = models.TextField(blank=True)
    salt = models.TextField(null=True)  # used for backwards compatibility

    def __str__(self):
        return "MatchReport for report(pk={0})".format(self.report.pk)

    @property
    def match_found(self):
        self.report.refresh_from_db()
        return self.report.match_found

    def encrypt_match_report(
        self,
        report_text: str,  # MatchReportContent as a string of json
        identifier: str,  # MatchReport is encrypted with the identifier
    ) -> None:
        '''
        Encrypts and attaches report text. Generates a random salt and
        stores it in an encode prefix on the MatchReport object.

        MatchReports are encrypted with the identifier, whereas Reports
        are encrypted with the secret key
        '''
        if self.salt:
            self.salt = None
        hasher = hashers.get_hasher()
        salt = get_random_string()

        encoded = hasher.encode(identifier, salt)
        self.encode_prefix, stretched_identifier = hasher.split_encoded(
            encoded)

        self.encrypted = security.pepper(
            security.encrypt_text(stretched_identifier, report_text),
        )
        self.save()

    def get_match(
        self,
        identifier: str,  # MatchReport is encrypted with the identifier
    ) -> str or None:
        '''
        Checks if the given identifier triggers a match on this report.
        Returns report text if so.
        '''
        decrypted_report = None

        prefix, stretched_identifier = hashers.make_key(
            self.encode_prefix,
            identifier,
            self.salt,
        )
        try:
            decrypted_report = security.decrypt_text(
                stretched_identifier,
                security.unpepper(self.encrypted),
            )
        except CryptoError:
            pass
        return decrypted_report


class SentFullReport(models.Model):
    '''Report of a single incident since to the monitoring organization'''
    report = models.ForeignKey(
        Report,
        blank=True,
        null=True,
        on_delete=models.SET_NULL)
    sent = models.DateTimeField(auto_now_add=True)
    to_address = models.TextField(blank=False, null=True)

    def get_report_id(self):
        return f'{self.id}-0'


class SentMatchReport(models.Model):
    '''Report of multiple incidents, sent to the monitoring organization'''
    reports = models.ManyToManyField(MatchReport)
    sent = models.DateTimeField(auto_now_add=True)
    to_address = models.TextField(blank=False, null=True)

    def get_report_id(self):
        return f'{self.id}-1'
