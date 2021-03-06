import pytest
import requests
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from open_city_profile.exceptions import ProfileMustHaveOnePrimaryEmail
from services.enums import ServiceType
from services.exceptions import MissingGDPRUrlException
from services.models import ServiceConnection
from services.tests.factories import ServiceConnectionFactory

from ..models import Email, Profile
from ..schema import validate_primary_email
from .factories import (
    EmailFactory,
    ProfileWithPrimaryEmailFactory,
    SensitiveDataFactory,
)

User = get_user_model()

GDPR_URL = "https://example.com/"


def test_new_profile_with_default_name(user):
    profile = Profile.objects.create(user=user)
    assert profile.first_name == user.first_name
    assert profile.last_name == user.last_name


def test_new_profile_without_default_name():
    user = User.objects.create(email="test@user.com", username="user")
    profile = Profile.objects.create(user=user)
    assert profile.first_name == ""
    assert profile.last_name == ""


def test_new_profile_with_existing_name_and_default_name(user):
    profile = Profile.objects.create(
        first_name="Existingfirstname", last_name="Existinglastname", user=user
    )
    assert profile.first_name == "Existingfirstname"
    assert profile.last_name == "Existinglastname"


def test_new_profile_with_non_existing_name_and_default_name(user):
    profile = Profile.objects.create(first_name="", last_name="", user=user)
    assert profile.first_name
    assert profile.last_name


def test_serialize_profile(profile):
    email_2 = EmailFactory(profile=profile)
    email_1 = EmailFactory(profile=profile)
    sensitive_data = SensitiveDataFactory(profile=profile)
    serialized_profile = profile.serialize()
    expected_firstname = {"key": "FIRST_NAME", "value": profile.first_name}
    expected_email = {
        "key": "EMAILS",
        "children": [
            {
                "key": "EMAIL",
                "children": [
                    {"key": "PRIMARY", "value": email_1.primary},
                    {"key": "EMAIL_TYPE", "value": email_1.email_type.name},
                    {"key": "EMAIL", "value": email_1.email},
                ],
            },
            {
                "key": "EMAIL",
                "children": [
                    {"key": "PRIMARY", "value": email_2.primary},
                    {"key": "EMAIL_TYPE", "value": email_2.email_type.name},
                    {"key": "EMAIL", "value": email_2.email},
                ],
            },
        ],
    }
    expected_sensitive_data = {
        "key": "SENSITIVEDATA",
        "children": [{"key": "SSN", "value": sensitive_data.ssn}],
    }
    assert "key" in serialized_profile
    assert "children" in serialized_profile
    assert serialized_profile.get("key") == "PROFILE"
    assert expected_firstname in serialized_profile.get("children")
    assert expected_email in serialized_profile.get("children")
    assert expected_sensitive_data in serialized_profile.get("children")


def test_get_service_gdpr_data(monkeypatch, service_factory, profile):
    def mock_download_gdpr_data(self):
        if self.service.service_type == ServiceType.BERTH:
            return {"key": "BERTH", "children": [{"key": "CUSTOMERID", "value": "123"}]}
        elif self.service.service_type == ServiceType.YOUTH_MEMBERSHIP:
            return {
                "key": "YOUTHPROFILE",
                "children": [{"key": "BIRTH_DATE", "value": "2004-12-08"}],
            }
        else:
            return {}

    # Setup the data
    service_berth = service_factory(service_type=ServiceType.BERTH)
    service_youth = service_factory(service_type=ServiceType.YOUTH_MEMBERSHIP)
    service_kukkuu = service_factory(service_type=ServiceType.GODCHILDREN_OF_CULTURE)
    ServiceConnectionFactory(profile=profile, service=service_berth)
    ServiceConnectionFactory(profile=profile, service=service_youth)
    ServiceConnectionFactory(profile=profile, service=service_kukkuu)

    # Let's monkeypatch the method in ServiceConnection to mock the http requests
    monkeypatch.setattr(
        ServiceConnection, "download_gdpr_data", mock_download_gdpr_data
    )

    response = profile.get_service_gdpr_data()
    assert response == [
        {"key": "BERTH", "children": [{"key": "CUSTOMERID", "value": "123"}]},
        {
            "key": "YOUTHPROFILE",
            "children": [{"key": "BIRTH_DATE", "value": "2004-12-08"}],
        },
    ]


def test_remove_service_gdpr_data_no_url(profile, service):
    service_connection = ServiceConnectionFactory(profile=profile, service=service)

    with pytest.raises(MissingGDPRUrlException):
        service_connection.delete_gdpr_data(dry_run=True)
    with pytest.raises(MissingGDPRUrlException):
        service_connection.delete_gdpr_data()


@pytest.mark.parametrize("service__gdpr_url", [GDPR_URL])
def test_remove_service_gdpr_data_successful(profile, service, requests_mock):
    requests_mock.delete(f"{GDPR_URL}{profile.pk}", json={}, status_code=204)

    service_connection = ServiceConnectionFactory(profile=profile, service=service)

    dry_run_ok = service_connection.delete_gdpr_data(dry_run=True)
    real_ok = service_connection.delete_gdpr_data()

    assert dry_run_ok
    assert real_ok


@pytest.mark.parametrize("service__gdpr_url", [GDPR_URL])
def test_remove_service_gdpr_data_fail(profile, service, requests_mock):
    requests_mock.delete(f"{GDPR_URL}{profile.pk}", json={}, status_code=405)

    service_connection = ServiceConnectionFactory(profile=profile, service=service)

    with pytest.raises(requests.RequestException):
        service_connection.delete_gdpr_data(dry_run=True)
    with pytest.raises(requests.RequestException):
        service_connection.delete_gdpr_data()


def test_import_customer_data_with_valid_data_set(service_factory):
    service_factory()
    data = [
        {
            "customer_id": "321456",
            "first_name": "Jukka",
            "last_name": "Virtanen",
            "ssn": "010190-001A",
            "email": "jukka.virtanen@example.com",
            "address": {
                "address": "Mannerheimintie 1 A 11",
                "postal_code": "00100",
                "city": "Helsinki",
            },
            "phones": ["0412345678", "358 503334411", "755 1122 K"],
        },
        {
            "customer_id": "321457",
            "first_name": "",
            "last_name": "",
            "ssn": "101086-1234",
            "email": "mirja.korhonen@example.com",
            "address": None,
            "phones": [],
        },
    ]
    assert Profile.objects.count() == 0
    result = Profile.import_customer_data(data)
    assert len(result.keys()) == 2
    profiles = Profile.objects.all()
    assert len(profiles) == 2
    for profile in profiles:
        assert (
            profile.service_connections.first().service.service_type
            == ServiceType.BERTH
        )


def test_import_customer_data_with_missing_customer_id():
    data = [
        {
            "first_name": "Jukka",
            "last_name": "Virtanen",
            "ssn": "010190-001A",
            "email": "jukka.virtanen@example.com",
            "address": {
                "address": "Mannerheimintie 1 A 11",
                "postal_code": "00100",
                "city": "Helsinki",
            },
            "phones": ["0412345678", "358 503334411", "755 1122 K"],
        },
        {
            "customer_id": "321457",
            "first_name": "",
            "last_name": "",
            "ssn": "101086-1234",
            "email": "mirja.korhonen@example.com",
            "address": None,
            "phones": [],
        },
    ]
    assert Profile.objects.count() == 0
    with pytest.raises(Exception) as e:
        Profile.import_customer_data(data)
    assert str(e.value) == "Could not import unknown customer, index: 0"
    assert Profile.objects.count() == 0


def test_import_customer_data_with_missing_email():
    data = [
        {
            "customer_id": "321457",
            "first_name": "Jukka",
            "last_name": "Virtanen",
            "ssn": "010190-001A",
            "address": {
                "address": "Mannerheimintie 1 A 11",
                "postal_code": "00100",
                "city": "Helsinki",
            },
            "phones": ["0412345678", "358 503334411", "755 1122 K"],
        }
    ]
    assert Profile.objects.count() == 0
    with pytest.raises(ProfileMustHaveOnePrimaryEmail) as e:
        Profile.import_customer_data(data)
    assert str(e.value) == "Profile must have exactly one primary email, index: 0"
    assert Profile.objects.count() == 0


def test_validation_should_pass_with_one_primary_email():
    profile = ProfileWithPrimaryEmailFactory()
    validate_primary_email(profile)


def test_validation_should_fail_with_no_primary_email(profile):
    with pytest.raises(ProfileMustHaveOnePrimaryEmail):
        validate_primary_email(profile)


def test_validation_should_fail_with_multiple_primary_emails(profile):
    EmailFactory(profile=profile, primary=True)
    EmailFactory(profile=profile, primary=True)
    with pytest.raises(ProfileMustHaveOnePrimaryEmail):
        validate_primary_email(profile)


def test_validation_should_fail_with_invalid_email():
    e = Email("!dsdsd{}{}{}{}{}{")
    with pytest.raises(ValidationError):
        e.save()
