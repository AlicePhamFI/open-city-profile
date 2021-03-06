from datetime import timedelta
from string import Template

import pytest
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from graphene import relay
from graphql_relay.node.node import to_global_id
from guardian.shortcuts import assign_perm

from open_city_profile.consts import (
    API_NOT_IMPLEMENTED_ERROR,
    INVALID_EMAIL_FORMAT_ERROR,
    OBJECT_DOES_NOT_EXIST_ERROR,
    PROFILE_MUST_HAVE_ONE_PRIMARY_EMAIL,
    TOKEN_EXPIRED_ERROR,
)
from open_city_profile.tests.factories import GroupFactory
from profiles.enums import AddressType, EmailType, PhoneType
from profiles.models import Profile
from services.enums import ServiceType
from services.tests.factories import ServiceConnectionFactory
from subscriptions.models import Subscription
from subscriptions.tests.factories import (
    SubscriptionTypeCategoryFactory,
    SubscriptionTypeFactory,
)
from youths.tests.factories import YouthProfileFactory

from ..schema import ProfileNode
from .factories import (
    AddressFactory,
    ClaimTokenFactory,
    EmailFactory,
    PhoneFactory,
    ProfileFactory,
    ProfileWithPrimaryEmailFactory,
    SensitiveDataFactory,
)


def test_normal_user_can_create_profile(rf, user_gql_client, email_data, profile_data):
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                createMyProfile(
                    input: {
                        profile: {
                            nickname: \"${nickname}\",
                            addEmails:[
                                {emailType: ${email_type}, email:\"${email}\", primary: ${primary}}
                            ]
                        }
                    }
                ) {
                profile{
                    nickname,
                    emails{
                        edges{
                        node{
                            email,
                            emailType,
                            primary,
                            verified
                        }
                        }
                    }
                }
            }
            }
        """
    )

    expected_data = {
        "createMyProfile": {
            "profile": {
                "nickname": profile_data["nickname"],
                "emails": {
                    "edges": [
                        {
                            "node": {
                                "email": email_data["email"],
                                "emailType": email_data["email_type"],
                                "primary": email_data["primary"],
                                "verified": False,
                            }
                        }
                    ]
                },
            }
        }
    }

    mutation = t.substitute(
        nickname=profile_data["nickname"],
        email=email_data["email"],
        email_type=email_data["email_type"],
        primary=str(email_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_cannot_create_profile_with_no_primary_email(
    rf, user_gql_client, email_data
):
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                createMyProfile(
                    input: {
                        profile: {
                            addEmails:[
                                {emailType: ${email_type}, email:\"${email}\", primary: ${primary}}
                            ]
                        }
                    }
                ) {
                profile{
                    id
                }
            }
            }
        """
    )

    mutation = t.substitute(
        email=email_data["email"],
        email_type=email_data["email_type"],
        primary=str(not email_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert "code" in executed["errors"][0]["extensions"]
    assert (
        executed["errors"][0]["extensions"]["code"]
        == PROFILE_MUST_HAVE_ONE_PRIMARY_EMAIL
    )


def test_normal_user_can_update_profile(rf, user_gql_client, email_data, profile_data):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    email = profile.emails.first()
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                            nickname: \"${nickname}\",
                            updateEmails:[
                                {
                                    id: \"${email_id}\",
                                    emailType: ${email_type},
                                    email:\"${email}\",
                                    primary: ${primary}
                                }
                            ]
                        }
                    }
                ) {
                    profile{
                        nickname,
                        emails{
                            edges{
                            node{
                                id
                                email
                                emailType
                                primary
                                verified
                            }
                            }
                        }
                    }
                }
            }
        """
    )

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "nickname": profile_data["nickname"],
                "emails": {
                    "edges": [
                        {
                            "node": {
                                "id": to_global_id(type="EmailNode", id=email.id),
                                "email": email_data["email"],
                                "emailType": email_data["email_type"],
                                "primary": email_data["primary"],
                                "verified": False,
                            }
                        }
                    ]
                },
            }
        }
    }

    mutation = t.substitute(
        nickname=profile_data["nickname"],
        email_id=to_global_id(type="EmailNode", id=email.id),
        email=email_data["email"],
        email_type=email_data["email_type"],
        primary=str(email_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_add_email(rf, user_gql_client, email_data):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    email = profile.emails.first()
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                            addEmails:[
                                {emailType: ${email_type}, email:\"${email}\", primary: ${primary}}
                            ]
                        }
                    }
            ) {
                profile{
                    emails{
                        edges{
                        node{
                            email
                            emailType
                            primary
                            verified
                        }
                        }
                    }
                }
            }
            }
        """
    )

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "emails": {
                    "edges": [
                        {
                            "node": {
                                "email": email.email,
                                "emailType": email.email_type.name,
                                "primary": email.primary,
                                "verified": False,
                            }
                        },
                        {
                            "node": {
                                "email": email_data["email"],
                                "emailType": email_data["email_type"],
                                "primary": not email_data["primary"],
                                "verified": False,
                            }
                        },
                    ]
                }
            }
        }
    }

    mutation = t.substitute(
        email=email_data["email"],
        email_type=email_data["email_type"],
        primary=str(not email_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_cannot_add_invalid_email(rf, user_gql_client, email_data):
    ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                            addEmails:[
                                {emailType: ${email_type}, email:\"${email}\", primary: ${primary}}
                            ]
                        }
                    }
            ) {
                profile{
                    emails{
                        edges{
                        node{
                            id
                        }
                        }
                    }
                }
            }
            }
        """
    )

    mutation = t.substitute(
        email="!dsdsd{}{}{}{}{}{",
        email_type=email_data["email_type"],
        primary=str(not email_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert "code" in executed["errors"][0]["extensions"]
    assert executed["errors"][0]["extensions"]["code"] == INVALID_EMAIL_FORMAT_ERROR


def test_normal_user_cannot_update_email_to_invalid_format(
    rf, user_gql_client, email_data
):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    email = profile.emails.first()
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                        updateEmails:[
                            {
                                id: \"${email_id}\",
                                emailType: ${email_type},
                                email:\"${email}\",
                                primary: ${primary}
                            }
                        ]
                    }
                }
            ) {
                profile{
                    emails{
                        edges{
                        node{
                            id
                        }
                        }
                    }
                }
            }
            }
        """
    )

    mutation = t.substitute(
        email_id=to_global_id(type="EmailNode", id=email.id),
        email="!dsdsd{}{}{}{}{}{",
        email_type=email_data["email_type"],
        primary=str(email_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert "code" in executed["errors"][0]["extensions"]
    assert executed["errors"][0]["extensions"]["code"] == INVALID_EMAIL_FORMAT_ERROR


def test_normal_user_can_add_phone(rf, user_gql_client, phone_data):
    ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                        addPhones:[
                            {phoneType: ${phone_type}, phone:\"${phone}\", primary: ${primary}}
                        ]
                    }
                }
            ) {
                profile{
                    phones{
                        edges{
                        node{
                            phone
                            phoneType
                            primary
                        }
                        }
                    }
                }
            }
            }
        """
    )

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "phones": {
                    "edges": [
                        {
                            "node": {
                                "phone": phone_data["phone"],
                                "phoneType": phone_data["phone_type"],
                                "primary": phone_data["primary"],
                            }
                        }
                    ]
                }
            }
        }
    }

    mutation = t.substitute(
        phone=phone_data["phone"],
        phone_type=phone_data["phone_type"],
        primary=str(phone_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_add_address(rf, user_gql_client, address_data):
    ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                            addAddresses: [
                                {
                                    addressType: ${address_type},
                                    address:\"${address}\",
                                    postalCode: \"${postal_code}\",
                                    city: \"${city}\",
                                    countryCode: \"${country_code}\",
                                    primary: ${primary}
                                }
                            ]
                        }
                    }
                ) {
                profile {
                    addresses {
                        edges {
                            node {
                                address
                                postalCode
                                city
                                countryCode
                                addressType
                                primary
                            }
                        }
                    }
                }
            }
            }
        """
    )

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "addresses": {
                    "edges": [
                        {
                            "node": {
                                "address": address_data["address"],
                                "postalCode": address_data["postal_code"],
                                "city": address_data["city"],
                                "countryCode": address_data["country_code"],
                                "addressType": address_data["address_type"],
                                "primary": address_data["primary"],
                            }
                        }
                    ]
                }
            }
        }
    }

    mutation = t.substitute(
        address=address_data["address"],
        postal_code=address_data["postal_code"],
        city=address_data["city"],
        country_code=address_data["country_code"],
        address_type=address_data["address_type"],
        primary=str(address_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_update_address(rf, user_gql_client, address_data):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    address = AddressFactory(profile=profile)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                        updateAddresses:[
                            {
                                id: \"${address_id}\",
                                addressType: ${address_type},
                                address:\"${address}\",
                                postalCode:\"${postal_code}\",
                                city:\"${city}\",
                                primary: ${primary}
                            }
                        ]
                    }
                }
            ) {
                profile{
                    addresses{
                        edges{
                        node{
                            id
                            address
                            postalCode
                            city
                            addressType
                            primary
                        }
                        }
                    }
                }
            }
            }
        """
    )

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "addresses": {
                    "edges": [
                        {
                            "node": {
                                "id": to_global_id(type="AddressNode", id=address.id),
                                "address": address_data["address"],
                                "postalCode": address_data["postal_code"],
                                "city": address_data["city"],
                                "addressType": address_data["address_type"],
                                "primary": address_data["primary"],
                            }
                        }
                    ]
                }
            }
        }
    }

    mutation = t.substitute(
        address_id=to_global_id(type="AddressNode", id=address.id),
        address=address_data["address"],
        postal_code=address_data["postal_code"],
        city=address_data["city"],
        address_type=address_data["address_type"],
        primary=str(address_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_update_email(rf, user_gql_client, email_data):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    email = profile.emails.first()
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                        updateEmails:[
                            {
                                id: \"${email_id}\",
                                emailType: ${email_type},
                                email:\"${email}\",
                                primary: ${primary}
                            }
                        ]
                    }
                }
            ) {
                profile{
                    emails{
                        edges{
                        node{
                            id
                            email
                            emailType
                            primary
                        }
                        }
                    }
                }
            }
            }
        """
    )

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "emails": {
                    "edges": [
                        {
                            "node": {
                                "id": to_global_id(type="EmailNode", id=email.id),
                                "email": email_data["email"],
                                "emailType": email_data["email_type"],
                                "primary": email_data["primary"],
                            }
                        }
                    ]
                }
            }
        }
    }

    mutation = t.substitute(
        email_id=to_global_id(type="EmailNode", id=email.id),
        email=email_data["email"],
        email_type=email_data["email_type"],
        primary=str(email_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_update_phone(rf, user_gql_client, phone_data):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    phone = PhoneFactory(profile=profile)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                        updatePhones:[
                            {
                                id: \"${phone_id}\",
                                phoneType: ${phone_type},
                                phone:\"${phone}\",
                                primary: ${primary}
                            }
                        ]
                    }
                }
            ) {
                profile{
                    phones{
                        edges{
                        node{
                            id
                            phone
                            phoneType
                            primary
                        }
                        }
                    }
                }
            }
            }
        """
    )

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "phones": {
                    "edges": [
                        {
                            "node": {
                                "id": to_global_id(type="PhoneNode", id=phone.id),
                                "phone": phone_data["phone"],
                                "phoneType": phone_data["phone_type"],
                                "primary": phone_data["primary"],
                            }
                        }
                    ]
                }
            }
        }
    }

    mutation = t.substitute(
        phone_id=to_global_id(type="PhoneNode", id=phone.id),
        phone=phone_data["phone"],
        phone_type=phone_data["phone_type"],
        primary=str(phone_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_remove_email(rf, user_gql_client, email_data):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user, emails=2)
    primary_email = profile.emails.filter(primary=True).first()
    email = profile.emails.filter(primary=False).first()
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                        removeEmails:[
                            \"${email_id}\"
                        ]
                    }
                }
            ) {
                profile{
                    emails{
                        edges{
                        node{
                            id
                            email
                            emailType
                            primary
                        }
                        }
                    }
                }
            }
            }
        """
    )

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "emails": {
                    "edges": [
                        {
                            "node": {
                                "id": to_global_id(
                                    type="EmailNode", id=primary_email.id
                                ),
                                "email": primary_email.email,
                                "emailType": primary_email.email_type.name,
                                "primary": primary_email.primary,
                            }
                        }
                    ]
                }
            }
        }
    }

    mutation = t.substitute(
        email_id=to_global_id(type="EmailNode", id=email.id),
        email=email_data["email"],
        email_type=email_data["email_type"],
        primary=str(email_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_remove_phone(rf, user_gql_client, phone_data):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    phone = PhoneFactory(profile=profile)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                        removePhones:[
                            \"${phone_id}\"
                        ]
                    }
                }
            ) {
                profile{
                    phones{
                        edges{
                        node{
                            id
                            phone
                            phoneType
                            primary
                        }
                        }
                    }
                }
            }
            }
        """
    )

    expected_data = {"updateMyProfile": {"profile": {"phones": {"edges": []}}}}

    mutation = t.substitute(
        phone_id=to_global_id(type="PhoneNode", id=phone.id),
        phone=phone_data["phone"],
        phone_type=phone_data["phone_type"],
        primary=str(phone_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_remove_address(rf, user_gql_client, address_data):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    address = AddressFactory(profile=profile)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                        removeAddresses:[
                            \"${address_id}\"
                        ]
                    }
                }
            ) {
                profile{
                    addresses{
                        edges{
                        node{
                            id
                            address
                            addressType
                            primary
                        }
                        }
                    }
                }
            }
            }
        """
    )

    expected_data = {"updateMyProfile": {"profile": {"addresses": {"edges": []}}}}

    mutation = t.substitute(
        address_id=to_global_id(type="AddressNode", id=address.id),
        address=address_data["address"],
        address_type=address_data["address_type"],
        primary=str(address_data["primary"]).lower(),
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_query_emails(rf, user_gql_client):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    email = profile.emails.first()
    request = rf.post("/graphql")
    request.user = user_gql_client.user
    query = """
        {
            myProfile {
                emails{
                    edges{
                        node{
                            email
                            emailType
                            primary
                        }
                    }
                }
            }
        }
    """
    expected_data = {
        "myProfile": {
            "emails": {
                "edges": [
                    {
                        "node": {
                            "email": email.email,
                            "emailType": email.email_type.name,
                            "primary": email.primary,
                        }
                    }
                ]
            }
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_query_phones(rf, user_gql_client):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    phone = PhoneFactory(profile=profile)
    request = rf.post("/graphql")
    request.user = user_gql_client.user
    query = """
        {
            myProfile {
                phones{
                    edges{
                        node{
                            phone
                            phoneType
                            primary
                        }
                    }
                }
            }
        }
    """
    expected_data = {
        "myProfile": {
            "phones": {
                "edges": [
                    {
                        "node": {
                            "phone": phone.phone,
                            "phoneType": phone.phone_type.name,
                            "primary": phone.primary,
                        }
                    }
                ]
            }
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_query_addresses(rf, user_gql_client):
    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    address = AddressFactory(profile=profile)
    request = rf.post("/graphql")
    request.user = user_gql_client.user
    query = """
        {
            myProfile {
                addresses{
                    edges{
                        node{
                            address
                            addressType
                            primary
                        }
                    }
                }
            }
        }
    """
    expected_data = {
        "myProfile": {
            "addresses": {
                "edges": [
                    {
                        "node": {
                            "address": address.address,
                            "addressType": address.address_type.name,
                            "primary": address.primary,
                        }
                    }
                ]
            }
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_query_primary_contact_details(rf, user_gql_client):
    profile = ProfileFactory(user=user_gql_client.user)
    phone = PhoneFactory(profile=profile, primary=True)
    email = EmailFactory(profile=profile, primary=True)
    address = AddressFactory(profile=profile, primary=True)
    PhoneFactory(profile=profile, primary=False)
    EmailFactory(profile=profile, primary=False)
    AddressFactory(profile=profile, primary=False)
    request = rf.post("/graphql")
    request.user = user_gql_client.user
    query = """
        {
            myProfile {
                primaryPhone{
                    phone,
                    phoneType,
                    primary
                },
                primaryEmail{
                    email,
                    emailType,
                    primary
                },
                primaryAddress{
                    address,
                    addressType,
                    primary
                }
            }
        }
    """
    expected_data = {
        "myProfile": {
            "primaryPhone": {
                "phone": phone.phone,
                "phoneType": phone.phone_type.name,
                "primary": phone.primary,
            },
            "primaryEmail": {
                "email": email.email,
                "emailType": email.email_type.name,
                "primary": email.primary,
            },
            "primaryAddress": {
                "address": address.address,
                "addressType": address.address_type.name,
                "primary": address.primary,
            },
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_change_primary_contact_details(
    rf, user_gql_client, email_data, phone_data, address_data
):
    profile = ProfileFactory(user=user_gql_client.user)
    PhoneFactory(profile=profile, primary=True)
    EmailFactory(profile=profile, primary=True)
    AddressFactory(profile=profile, primary=True)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                            addEmails:[
                                {emailType: ${email_type}, email:\"${email}\", primary: ${primary}}
                            ],
                            addPhones:[
                                {phoneType: ${phone_type}, phone:\"${phone}\", primary: ${primary}}
                            ],
                            addAddresses:[
                                {
                                    addressType: ${address_type},
                                    address:\"${address}\",
                                    postalCode:\"${postal_code}\",
                                    city:\"${city}\",
                                    primary: ${primary}
                                }
                            ]
                        }
                    }
                ) {
                profile{
                    primaryEmail{
                        email,
                        emailType,
                        primary
                    },
                    primaryPhone{
                        phone,
                        phoneType,
                        primary
                    },
                    primaryAddress{
                        address,
                        postalCode,
                        city,
                        addressType,
                        primary
                    },
                }
            }
            }
        """
    )

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "primaryEmail": {
                    "email": email_data["email"],
                    "emailType": email_data["email_type"],
                    "primary": True,
                },
                "primaryPhone": {
                    "phone": phone_data["phone"],
                    "phoneType": phone_data["phone_type"],
                    "primary": True,
                },
                "primaryAddress": {
                    "address": address_data["address"],
                    "postalCode": address_data["postal_code"],
                    "city": address_data["city"],
                    "addressType": address_data["address_type"],
                    "primary": True,
                },
            }
        }
    }

    mutation = t.substitute(
        email=email_data["email"],
        email_type=email_data["email_type"],
        phone=phone_data["phone"],
        phone_type=phone_data["phone_type"],
        address=address_data["address"],
        postal_code=address_data["postal_code"],
        city=address_data["city"],
        address_type=address_data["address_type"],
        primary="true",
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_update_primary_contact_details(
    rf, user_gql_client, email_data
):
    profile = ProfileFactory(user=user_gql_client.user)
    email = EmailFactory(profile=profile)
    email_2 = EmailFactory(profile=profile, primary=True)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                        updateEmails:[
                            {
                                id: \"${email_id}\",
                                emailType: ${email_type},
                                email:\"${email}\",
                                primary: ${primary}
                            }
                        ]
                    }
                }
            ) {
                profile{
                    emails{
                        edges{
                        node{
                            id
                            email
                            emailType
                            primary
                        }
                        }
                    }
                }
            }
            }
        """
    )

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "emails": {
                    "edges": [
                        {
                            "node": {
                                "id": to_global_id(type="EmailNode", id=email.id),
                                "email": email_data["email"],
                                "emailType": email_data["email_type"],
                                "primary": True,
                            }
                        },
                        {
                            "node": {
                                "id": to_global_id(type="EmailNode", id=email_2.id),
                                "email": email_2.email,
                                "emailType": email_2.email_type.name,
                                "primary": False,
                            }
                        },
                    ]
                }
            }
        }
    }

    mutation = t.substitute(
        email_id=to_global_id(type="EmailNode", id=email.id),
        email=email_data["email"],
        email_type=email_data["email_type"],
        primary="true",
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_update_sensitive_data(rf, user_gql_client):
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    profile = ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    SensitiveDataFactory(profile=profile, ssn="010199-1234")

    t = Template(
        """
            mutation {
                updateMyProfile(
                    input: {
                        profile: {
                            nickname: "${nickname}"
                            sensitivedata: {
                                ssn: "${ssn}"
                            }
                        }
                    }
                ) {
                    profile {
                        nickname
                        sensitivedata {
                            ssn
                        }
                    }
                }
            }
        """
    )

    data = {"nickname": "Larry", "ssn": "010199-4321"}

    query = t.substitute(**data)

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "nickname": data["nickname"],
                "sensitivedata": {"ssn": data["ssn"]},
            }
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_update_subscriptions_via_profile(rf, user_gql_client):
    ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    category = SubscriptionTypeCategoryFactory()
    type_1 = SubscriptionTypeFactory(subscription_type_category=category, code="TEST-1")
    type_2 = SubscriptionTypeFactory(subscription_type_category=category, code="TEST-2")
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        mutation {
            updateMyProfile(
                input: {
                    profile: {
                        subscriptions: [
                            {
                                subscriptionTypeId: \"${type_1_id}\",
                                enabled: ${type_1_enabled}
                            },
                            {
                                subscriptionTypeId: \"${type_2_id}\",
                                enabled: ${type_2_enabled}
                            }
                        ]
                    }
                }
            ) {
                profile {
                    subscriptions {
                        edges {
                            node {
                                enabled
                                subscriptionType {
                                    code
                                    subscriptionTypeCategory {
                                        code
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """
    )

    expected_data = {
        "updateMyProfile": {
            "profile": {
                "subscriptions": {
                    "edges": [
                        {
                            "node": {
                                "enabled": True,
                                "subscriptionType": {
                                    "code": type_1.code,
                                    "subscriptionTypeCategory": {"code": category.code},
                                },
                            }
                        },
                        {
                            "node": {
                                "enabled": False,
                                "subscriptionType": {
                                    "code": type_2.code,
                                    "subscriptionTypeCategory": {"code": category.code},
                                },
                            }
                        },
                    ]
                }
            }
        }
    }

    mutation = t.substitute(
        type_1_id=to_global_id(type="SubscriptionTypeNode", id=type_1.id),
        type_1_enabled="true",
        type_2_id=to_global_id(type="SubscriptionTypeNode", id=type_2.id),
        type_2_enabled="false",
    )
    executed = user_gql_client.execute(mutation, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_not_query_berth_profiles(rf, user_gql_client, service_factory):
    service_factory()
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            profiles(serviceType: ${service_type}) {
                edges {
                    node {
                        firstName
                        lastName
                    }
                }
            }
        }
    """
    )
    query = t.substitute(service_type=ServiceType.BERTH.name)
    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed
    assert executed["errors"][0]["message"] == _(
        "You do not have permission to perform this action."
    )


def test_admin_user_can_query_berth_profiles(
    rf, superuser_gql_client, profile, service
):
    ServiceConnectionFactory(profile=profile, service=service)
    request = rf.post("/graphql")
    request.user = superuser_gql_client.user

    t = Template(
        """
        {
            profiles(serviceType: ${service_type}) {
                edges {
                    node {
                        firstName
                        lastName
                        nickname
                    }
                }
            }
        }
    """
    )
    query = t.substitute(service_type=ServiceType.BERTH.name)
    expected_data = {
        "profiles": {
            "edges": [
                {
                    "node": {
                        "firstName": profile.first_name,
                        "lastName": profile.last_name,
                        "nickname": profile.nickname,
                    }
                }
            ]
        }
    }
    executed = superuser_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_staff_user_with_group_access_can_query_berth_profiles(
    rf, user_gql_client, profile, group, service
):
    ServiceConnectionFactory(profile=profile, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user

    t = Template(
        """
        {
            profiles(serviceType: ${service_type}) {
                edges {
                    node {
                        firstName
                    }
                }
            }
        }
    """
    )
    query = t.substitute(service_type=ServiceType.BERTH.name)
    expected_data = {
        "profiles": {"edges": [{"node": {"firstName": profile.first_name}}]}
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_staff_user_can_filter_berth_profiles(rf, user_gql_client, group, service):
    profile_1, profile_2 = ProfileFactory.create_batch(2)
    ServiceConnectionFactory(profile=profile_1, service=service)
    ServiceConnectionFactory(profile=profile_2, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $firstName: String){
            profiles(serviceType: $serviceType, firstName: $firstName) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 1, "totalCount": 2}}

    executed = user_gql_client.execute(
        query,
        variables={
            "serviceType": ServiceType.BERTH.name,
            "firstName": profile_2.first_name,
        },
        context=request,
    )
    assert "errors" not in executed
    assert dict(executed["data"]) == expected_data


def test_staff_user_can_sort_berth_profiles(rf, user_gql_client, group, service):
    profile_1, profile_2 = (
        ProfileFactory(first_name="Adam", last_name="Tester"),
        ProfileFactory(first_name="Bryan", last_name="Tester"),
    )
    ServiceConnectionFactory(profile=profile_1, service=service)
    ServiceConnectionFactory(profile=profile_2, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user

    t = Template(
        """
        query getBerthProfiles {
            profiles(serviceType: ${service_type}, orderBy: "-firstName") {
                edges {
                    node {
                        firstName
                    }
                }
            }
        }
    """
    )
    query = t.substitute(service_type=ServiceType.BERTH.name)
    expected_data = {
        "profiles": {
            "edges": [{"node": {"firstName": "Bryan"}}, {"node": {"firstName": "Adam"}}]
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


@pytest.mark.parametrize(
    "order_by",
    [
        "primaryAddress",
        "primaryCity",
        "primaryPostalCode",
        "primaryCountryCode",
        "primaryEmail",
    ],
)
def test_staff_user_can_sort_berth_profiles_by_custom_fields(
    rf, user_gql_client, group, service, order_by
):
    profile_1, profile_2 = (
        ProfileFactory(first_name="Adam", last_name="Tester"),
        ProfileFactory(first_name="Bryan", last_name="Tester"),
    )
    AddressFactory(
        profile=profile_1,
        city="Akaa",
        address="Autotie 1",
        postal_code="00100",
        country_code="FI",
        primary=True,
    ),
    AddressFactory(
        profile=profile_2,
        city="Ypäjä",
        address="Yrjönkatu 99",
        postal_code="99999",
        country_code="SE",
        primary=True,
    ),
    EmailFactory(profile=profile_1, email="adam.tester@example.com", primary=True,),
    EmailFactory(profile=profile_2, email="bryan.tester@example.com", primary=True,),
    ServiceConnectionFactory(profile=profile_1, service=service)
    ServiceConnectionFactory(profile=profile_2, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user

    t = Template(
        """
        query getBerthProfiles {
            profiles(serviceType: ${service_type}, orderBy: \"${order_by}\") {
                edges {
                    node {
                        firstName
                    }
                }
            }
        }
    """
    )
    query = t.substitute(service_type=ServiceType.BERTH.name, order_by=order_by)
    expected_data = {
        "profiles": {
            "edges": [{"node": {"firstName": "Adam"}}, {"node": {"firstName": "Bryan"}}]
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data

    query = t.substitute(service_type=ServiceType.BERTH.name, order_by=f"-{order_by}")
    expected_data = {
        "profiles": {
            "edges": [{"node": {"firstName": "Bryan"}}, {"node": {"firstName": "Adam"}}]
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_staff_user_can_filter_berth_profiles_by_emails(
    rf, user_gql_client, group, service
):
    profile_1, profile_2, profile_3 = ProfileFactory.create_batch(3)
    EmailFactory(
        profile=profile_1, primary=True, email_type=EmailType.PERSONAL, verified=True
    )
    email = EmailFactory(profile=profile_2, primary=False, email_type=EmailType.WORK)
    EmailFactory(profile=profile_3, primary=False, email_type=EmailType.OTHER)
    ServiceConnectionFactory(profile=profile_1, service=service)
    ServiceConnectionFactory(profile=profile_2, service=service)
    ServiceConnectionFactory(profile=profile_3, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user

    # filter by email

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $email: String){
            profiles(serviceType: $serviceType, emails_Email: $email) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 1, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={"serviceType": ServiceType.BERTH.name, "email": email.email},
        context=request,
    )
    assert dict(executed["data"]) == expected_data

    # filter by email_type

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $emailType: String){
            profiles(serviceType: $serviceType, emails_EmailType: $emailType) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 1, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={
            "serviceType": ServiceType.BERTH.name,
            "emailType": email.email_type.value,
        },
        context=request,
    )
    assert dict(executed["data"]) == expected_data

    # filter by primary

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $primary: Boolean){
            profiles(serviceType: $serviceType, emails_Primary: $primary) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 2, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={"serviceType": ServiceType.BERTH.name, "primary": False},
        context=request,
    )
    assert dict(executed["data"]) == expected_data

    # filter by verified

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $verified: Boolean){
            profiles(serviceType: $serviceType, emails_Verified: $verified) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 1, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={"serviceType": ServiceType.BERTH.name, "verified": True},
        context=request,
    )
    assert dict(executed["data"]) == expected_data


def test_staff_user_can_filter_berth_profiles_by_phones(
    rf, user_gql_client, group, service
):
    profile_1, profile_2, profile_3 = ProfileFactory.create_batch(3)
    PhoneFactory(profile=profile_1, primary=True, phone_type=PhoneType.HOME)
    phone = PhoneFactory(profile=profile_2, primary=False, phone_type=PhoneType.WORK)
    PhoneFactory(profile=profile_3, primary=False, phone_type=PhoneType.MOBILE)
    ServiceConnectionFactory(profile=profile_1, service=service)
    ServiceConnectionFactory(profile=profile_2, service=service)
    ServiceConnectionFactory(profile=profile_3, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user

    # filter by phone

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $phone: String){
            profiles(serviceType: $serviceType, phones_Phone: $phone) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 1, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={"serviceType": ServiceType.BERTH.name, "phone": phone.phone},
        context=request,
    )
    assert dict(executed["data"]) == expected_data

    # filter by phone_type

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $phoneType: String){
            profiles(serviceType: $serviceType, phones_PhoneType: $phoneType) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 1, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={
            "serviceType": ServiceType.BERTH.name,
            "phoneType": phone.phone_type.value,
        },
        context=request,
    )
    assert dict(executed["data"]) == expected_data

    # filter by primary

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $primary: Boolean){
            profiles(serviceType: $serviceType, phones_Primary: $primary) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 2, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={"serviceType": ServiceType.BERTH.name, "primary": False},
        context=request,
    )
    assert dict(executed["data"]) == expected_data


def test_staff_user_can_filter_berth_profiles_by_addresses(
    rf, user_gql_client, group, service
):
    profile_1, profile_2, profile_3 = ProfileFactory.create_batch(3)
    AddressFactory(
        profile=profile_1,
        postal_code="00100",
        city="Helsinki",
        country_code="FI",
        primary=True,
        address_type=AddressType.HOME,
    )
    address = AddressFactory(
        profile=profile_2,
        postal_code="00100",
        city="Espoo",
        country_code="FI",
        primary=False,
        address_type=AddressType.WORK,
    )
    AddressFactory(
        profile=profile_3,
        postal_code="00200",
        city="Stockholm",
        country_code="SE",
        primary=False,
        address_type=AddressType.OTHER,
    )
    ServiceConnectionFactory(profile=profile_1, service=service)
    ServiceConnectionFactory(profile=profile_2, service=service)
    ServiceConnectionFactory(profile=profile_3, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user

    # filter by address

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $address: String){
            profiles(serviceType: $serviceType, addresses_Address: $address) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 1, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={"serviceType": ServiceType.BERTH.name, "address": address.address},
        context=request,
    )
    assert dict(executed["data"]) == expected_data

    # filter by postal_code

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $postalCode: String){
            profiles(serviceType: $serviceType, addresses_PostalCode: $postalCode) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 2, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={
            "serviceType": ServiceType.BERTH.name,
            "postalCode": address.postal_code,
        },
        context=request,
    )
    assert dict(executed["data"]) == expected_data

    # filter by city

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $city: String){
            profiles(serviceType: $serviceType, addresses_City: $city) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 1, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={"serviceType": ServiceType.BERTH.name, "city": address.city},
        context=request,
    )
    assert dict(executed["data"]) == expected_data

    # filter by country code

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $countryCode: String){
            profiles(serviceType: $serviceType, addresses_CountryCode: $countryCode) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 2, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={
            "serviceType": ServiceType.BERTH.name,
            "countryCode": address.country_code,
        },
        context=request,
    )
    assert dict(executed["data"]) == expected_data

    # filter by address_type

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $addressType: String){
            profiles(serviceType: $serviceType, addresses_AddressType: $addressType) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 1, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={
            "serviceType": ServiceType.BERTH.name,
            "addressType": address.address_type.value,
        },
        context=request,
    )
    assert dict(executed["data"]) == expected_data

    # filter by primary

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $primary: Boolean){
            profiles(serviceType: $serviceType, addresses_Primary: $primary) {
                count
                totalCount
            }
        }
    """

    expected_data = {"profiles": {"count": 2, "totalCount": 3}}

    executed = user_gql_client.execute(
        query,
        variables={"serviceType": ServiceType.BERTH.name, "primary": False},
        context=request,
    )
    assert dict(executed["data"]) == expected_data


def test_staff_user_can_filter_berth_profiles_by_subscriptions_and_postal_code(
    rf, user_gql_client, group, service
):
    def generate_expected_data(profiles):
        return {
            "profiles": {
                "edges": [
                    {
                        "node": {
                            "emails": {
                                "edges": [
                                    {"node": {"email": profile.emails.first().email}}
                                ]
                            },
                            "phones": {
                                "edges": [
                                    {"node": {"phone": profile.phones.first().phone}}
                                ]
                            },
                        }
                    }
                    for profile in profiles
                ]
            }
        }

    profile_1, profile_2, profile_3, profile_4 = ProfileFactory.create_batch(4)
    PhoneFactory(profile=profile_1, phone="0401234561", primary=True)
    PhoneFactory(profile=profile_2, phone="0401234562", primary=True)
    PhoneFactory(profile=profile_3, phone="0401234563", primary=True)
    PhoneFactory(profile=profile_4, phone="0401234564", primary=True)

    EmailFactory(profile=profile_1, email="first@example.com", primary=True)
    EmailFactory(profile=profile_2, email="second@example.com", primary=True)
    EmailFactory(profile=profile_3, email="third@example.com", primary=True)
    EmailFactory(profile=profile_4, email="fourth@example.com", primary=True)

    AddressFactory(profile=profile_1, primary=True, postal_code="00100")
    AddressFactory(profile=profile_2, postal_code="00100")
    AddressFactory(profile=profile_3, postal_code="00100")
    AddressFactory(profile=profile_4, postal_code="00200")

    cat = SubscriptionTypeCategoryFactory(code="TEST-CATEGORY-1")
    type_1 = SubscriptionTypeFactory(subscription_type_category=cat, code="TEST-1")
    type_2 = SubscriptionTypeFactory(subscription_type_category=cat, code="TEST-2")

    Subscription.objects.create(
        profile=profile_1, subscription_type=type_1, enabled=True
    )
    Subscription.objects.create(
        profile=profile_1, subscription_type=type_2, enabled=True
    )

    Subscription.objects.create(
        profile=profile_2, subscription_type=type_1, enabled=True
    )
    Subscription.objects.create(
        profile=profile_2, subscription_type=type_2, enabled=False
    )

    Subscription.objects.create(
        profile=profile_3, subscription_type=type_1, enabled=True
    )

    Subscription.objects.create(
        profile=profile_4, subscription_type=type_2, enabled=True
    )

    ServiceConnectionFactory(profile=profile_1, service=service)
    ServiceConnectionFactory(profile=profile_2, service=service)
    ServiceConnectionFactory(profile=profile_3, service=service)
    ServiceConnectionFactory(profile=profile_4, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user

    query = """
        query getBerthProfiles($serviceType: ServiceType!, $subscriptionType: String, $postalCode: String){
            profiles(
                serviceType: $serviceType,
                enabledSubscriptions: $subscriptionType,
                addresses_PostalCode: $postalCode
            ) {
                edges {
                    node {
                        emails {
                            edges {
                                node {
                                    email
                                }
                            }
                        }
                        phones {
                            edges {
                                node {
                                    phone
                                }
                            }
                        }
                    }
                }
            }
        }
    """

    # test for type 1 + postal code 00100

    executed = user_gql_client.execute(
        query,
        variables={
            "serviceType": ServiceType.BERTH.name,
            "subscriptionType": type_1.code,
            "postalCode": "00100",
        },
        context=request,
    )
    assert dict(executed["data"]) == generate_expected_data(
        [profile_1, profile_2, profile_3]
    )

    # test for type 2 + postal code 00100

    executed = user_gql_client.execute(
        query,
        variables={
            "serviceType": ServiceType.BERTH.name,
            "subscriptionType": type_2.code,
            "postalCode": "00100",
        },
        context=request,
    )
    assert dict(executed["data"]) == generate_expected_data([profile_1])


def test_staff_user_can_paginate_berth_profiles(rf, user_gql_client, group, service):
    profile_1, profile_2 = (
        ProfileFactory(first_name="Adam", last_name="Tester"),
        ProfileFactory(first_name="Bryan", last_name="Tester"),
    )
    ServiceConnectionFactory(profile=profile_1, service=service)
    ServiceConnectionFactory(profile=profile_2, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user

    query = """
        query getBerthProfiles {
            profiles(serviceType: BERTH, orderBy: "firstName", first: 1) {
                pageInfo {
                    endCursor
                }
                edges {
                    node {
                        firstName
                    }
                }
            }
        }
    """

    expected_data = {"edges": [{"node": {"firstName": "Adam"}}]}
    executed = user_gql_client.execute(query, context=request)
    assert "data" in executed
    assert executed["data"]["profiles"]["edges"] == expected_data["edges"]
    assert "pageInfo" in executed["data"]["profiles"]
    assert "endCursor" in executed["data"]["profiles"]["pageInfo"]

    end_cursor = executed["data"]["profiles"]["pageInfo"]["endCursor"]

    query = """
        query getBerthProfiles($endCursor: String){
            profiles(serviceType: BERTH, first: 1, after: $endCursor) {
                edges {
                    node {
                        firstName
                    }
                }
            }
        }
    """
    expected_data = {"edges": [{"node": {"firstName": "Bryan"}}]}
    executed = user_gql_client.execute(
        query, variables={"endCursor": end_cursor}, context=request
    )
    assert "data" in executed
    assert executed["data"]["profiles"] == expected_data


def test_staff_user_with_group_access_can_query_only_profiles_he_has_access_to(
    rf, user_gql_client, group, service_factory
):
    profile_berth = ProfileFactory()
    profile_youth = ProfileFactory()
    service_berth = service_factory(service_type=ServiceType.BERTH)
    service_youth = service_factory(service_type=ServiceType.YOUTH_MEMBERSHIP)
    ServiceConnectionFactory(profile=profile_berth, service=service_berth)
    ServiceConnectionFactory(profile=profile_youth, service=service_youth)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service_berth)
    request = rf.post("/graphql")
    request.user = user

    t = Template(
        """
        {
            profiles(serviceType: ${service_type}) {
                edges {
                    node {
                        firstName
                    }
                }
            }
        }
    """
    )
    query = t.substitute(service_type=ServiceType.BERTH.name)
    expected_data = {
        "profiles": {"edges": [{"node": {"firstName": profile_berth.first_name}}]}
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data

    t = Template(
        """
        {
            profiles(serviceType: ${service_type}) {
                edges {
                    node {
                        firstName
                    }
                }
            }
        }
    """
    )
    query = t.substitute(service_type=ServiceType.YOUTH_MEMBERSHIP.name)
    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed
    assert executed["errors"][0]["message"] == _(
        "You do not have permission to perform this action."
    )


def test_staff_user_can_create_a_profile(
    rf, user_gql_client, email_data, phone_data, address_data, group, service
):
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_manage_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user

    t = Template(
        """
        mutation {
            createProfile(
                input: {
                    serviceType: ${service_type},
                    profile: {
                        firstName: \"${first_name}\",
                        lastName: \"${last_name}\",
                        addEmails: [{
                            emailType: ${email_type},
                            email: \"${email}\",
                            primary: true,
                        }],
                        addPhones: [{
                            phoneType: ${phone_type},
                            phone: \"${phone}\",
                            primary: true
                        }]
                    }
                }
            ) {
                profile {
                    firstName
                    lastName
                    phones {
                        edges {
                            node {
                                phoneType
                                phone
                                primary
                            }
                        }
                    }
                    emails {
                        edges {
                            node {
                                emailType
                                email
                                primary
                            }
                        }
                    }
                    serviceConnections {
                        edges {
                            node {
                                service {
                                    type
                                }
                            }
                        }
                    }
                }
            }
        }
    """
    )
    query = t.substitute(
        service_type=ServiceType.BERTH.name,
        first_name="John",
        last_name="Doe",
        phone_type=phone_data["phone_type"],
        phone=phone_data["phone"],
        email_type=email_data["email_type"],
        email=email_data["email"],
    )
    expected_data = {
        "createProfile": {
            "profile": {
                "firstName": "John",
                "lastName": "Doe",
                "phones": {
                    "edges": [
                        {
                            "node": {
                                "phoneType": phone_data["phone_type"],
                                "phone": phone_data["phone"],
                                "primary": True,
                            }
                        }
                    ]
                },
                "emails": {
                    "edges": [
                        {
                            "node": {
                                "emailType": email_data["email_type"],
                                "email": email_data["email"],
                                "primary": True,
                            }
                        }
                    ]
                },
                "serviceConnections": {
                    "edges": [{"node": {"service": {"type": ServiceType.BERTH.name}}}]
                },
            }
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert executed["data"] == expected_data


def test_normal_user_cannot_create_a_profile_using_create_profile_mutation(
    rf, user_gql_client, service_factory
):
    service_factory()
    user = user_gql_client.user
    request = rf.post("/graphql")
    request.user = user

    t = Template(
        """
        mutation {
            createProfile(
                input: {
                    serviceType: ${service_type},
                    profile: {
                        firstName: \"${first_name}\",
                    }
                }
            ) {
                profile {
                    firstName
                }
            }
        }
    """
    )
    query = t.substitute(service_type=ServiceType.BERTH.name, first_name="John")
    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed
    assert executed["errors"][0]["message"] == _(
        "You do not have permission to perform this action."
    )


def test_staff_user_cannot_create_a_profile_without_service_access(
    rf, user_gql_client, service_factory
):
    service_factory(service_type=ServiceType.BERTH)
    service = service_factory(service_type=ServiceType.YOUTH_MEMBERSHIP)
    group = GroupFactory(name="youth_membership")
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_manage_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user

    t = Template(
        """
        mutation {
            createProfile(
                input: {
                    serviceType: ${service_type},
                    profile: {
                        firstName: \"${first_name}\",
                    }
                }
            ) {
                profile {
                    firstName
                }
            }
        }
    """
    )
    query = t.substitute(service_type=ServiceType.BERTH.name, first_name="John")
    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed
    assert executed["errors"][0]["message"] == _(
        "You do not have permission to perform this action."
    )


def test_staff_user_with_sensitive_data_service_accesss_can_create_a_profile_with_sensitive_data(
    rf, user_gql_client, email_data, group, service
):
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_manage_profiles", group, service)
    assign_perm("can_manage_sensitivedata", group, service)
    assign_perm("can_view_sensitivedata", group, service)
    request = rf.post("/graphql")
    request.user = user

    t = Template(
        """
        mutation {
            createProfile(
                input: {
                    serviceType: ${service_type},
                    profile: {
                        firstName: \"${first_name}\",
                        addEmails: [{
                            email: \"${email}\",
                            emailType: ${email_type},
                            primary: true
                        }],
                        sensitivedata: {
                            ssn: \"${ssn}\"
                        }
                    }
                }
            ) {
                profile {
                    firstName
                    sensitivedata {
                        ssn
                    }
                }
            }
        }
    """
    )
    query = t.substitute(
        service_type=ServiceType.BERTH.name,
        first_name="John",
        ssn="121282-123E",
        email=email_data["email"],
        email_type=email_data["email_type"],
    )

    expected_data = {
        "createProfile": {
            "profile": {"firstName": "John", "sensitivedata": {"ssn": "121282-123E"}}
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert executed["data"] == expected_data


def test_staff_user_cannot_create_a_profile_with_sensitive_data_without_sensitive_data_service_access(
    rf, user_gql_client, service_factory
):
    service_berth = service_factory(service_type=ServiceType.BERTH)
    service_youth = service_factory(service_type=ServiceType.YOUTH_MEMBERSHIP)
    group_berth = GroupFactory(name=ServiceType.BERTH.value)
    group_youth = GroupFactory(name="youth_membership")
    user = user_gql_client.user
    user.groups.add(group_berth)
    user.groups.add(group_youth)
    assign_perm("can_manage_profiles", group_berth, service_berth)
    assign_perm("can_manage_sensitivedata", group_youth, service_youth)
    assign_perm("can_view_sensitivedata", group_youth, service_youth)
    request = rf.post("/graphql")
    request.user = user

    t = Template(
        """
        mutation {
            createProfile(
                input: {
                    serviceType: ${service_type},
                    profile: {
                        firstName: \"${first_name}\",
                        sensitivedata: {
                            ssn: \"${ssn}\"
                        }
                    }
                }
            ) {
                profile {
                    firstName
                    sensitivedata {
                        ssn
                    }
                }
            }
        }
    """
    )
    query = t.substitute(
        service_type=ServiceType.BERTH.name, first_name="John", ssn="121282-123E"
    )

    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed
    assert executed["errors"][0]["message"] == _(
        "You do not have permission to perform this action."
    )


@pytest.mark.parametrize("service__service_type", [ServiceType.YOUTH_MEMBERSHIP])
def test_staff_user_can_update_a_profile(rf, user_gql_client, group, service):
    profile = ProfileWithPrimaryEmailFactory(first_name="Joe")
    phone = PhoneFactory(profile=profile)
    address = AddressFactory(profile=profile)
    YouthProfileFactory(profile=profile)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_manage_profiles", group, service)
    assign_perm("can_view_sensitivedata", group, service)
    assign_perm("can_manage_sensitivedata", group, service)
    request = rf.post("/graphql")
    request.user = user

    data = {
        "first_name": "John",
        "email": {
            "email": "another@example.com",
            "email_type": EmailType.WORK.name,
            "primary": False,
        },
        "phone": "0407654321",
        "school_class": "5F",
        "ssn": "010199-1234",
    }

    t = Template(
        """
        mutation {
            updateProfile(
                input: {
                    serviceType: ${service_type},
                    profile: {
                        id: \"${id}\",
                        firstName: \"${first_name}\",
                        addEmails: [{
                            email: \"${email}\"
                            emailType: ${email_type}
                            primary: ${primary}
                        }],
                        updatePhones: [{
                            id: \"${phone_id}\",
                            phone: \"${phone}\",
                        }],
                        removeAddresses: [\"${address_id}\"],
                        youthProfile: {
                            schoolClass: \"${school_class}\"
                        },
                        sensitivedata: {
                            ssn: \"${ssn}\"
                        }
                    }
                }
            ) {
                profile {
                    firstName
                    emails {
                        edges {
                            node {
                                email
                            }
                        }
                    }
                    phones {
                        edges {
                            node {
                                phone
                            }
                        }
                    }
                    addresses {
                        edges {
                            node {
                                address
                            }
                        }
                    }
                    youthProfile {
                        schoolClass
                    }
                    sensitivedata {
                        ssn
                    }
                }
            }
        }
    """
    )
    query = t.substitute(
        service_type=ServiceType.YOUTH_MEMBERSHIP.name,
        id=to_global_id("ProfileNode", profile.pk),
        first_name=data["first_name"],
        phone_id=to_global_id("PhoneNode", phone.pk),
        email=data["email"]["email"],
        email_type=data["email"]["email_type"],
        primary=str(data["email"]["primary"]).lower(),
        phone=data["phone"],
        address_id=to_global_id(type="AddressNode", id=address.pk),
        school_class=data["school_class"],
        ssn=data["ssn"],
    )
    expected_data = {
        "updateProfile": {
            "profile": {
                "firstName": data["first_name"],
                "emails": {
                    "edges": [
                        {"node": {"email": profile.emails.first().email}},
                        {"node": {"email": data["email"]["email"]}},
                    ]
                },
                "phones": {"edges": [{"node": {"phone": data["phone"]}}]},
                "addresses": {"edges": []},
                "youthProfile": {"schoolClass": data["school_class"]},
                "sensitivedata": {"ssn": data["ssn"]},
            }
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert executed["data"] == expected_data


@pytest.mark.parametrize("service__service_type", [ServiceType.YOUTH_MEMBERSHIP])
def test_staff_user_cannot_update_profile_sensitive_data_without_correct_permission(
    rf, user_gql_client, group, service
):
    """A staff user without can_manage_sensitivedata permission cannot update sensitive data."""
    profile = ProfileWithPrimaryEmailFactory()
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_manage_profiles", group, service)
    assign_perm("can_view_sensitivedata", group, service)

    request = rf.post("/graphql")
    request.user = user

    t = Template(
        """
        mutation {
            updateProfile(
                input: {
                    serviceType: ${service_type},
                    profile: {
                        id: \"${id}\",
                        sensitivedata: {
                            ssn: \"${ssn}\"
                        }
                    }
                }
            ) {
                profile {
                    sensitivedata {
                        ssn
                    }
                }
            }
        }
    """
    )
    query = t.substitute(
        service_type=ServiceType.YOUTH_MEMBERSHIP.name,
        id=to_global_id("ProfileNode", profile.pk),
        ssn="010199-1234",
    )
    executed = user_gql_client.execute(query, context=request)

    assert "errors" in executed
    assert executed["errors"][0]["message"] == _(
        "You do not have permission to perform this action."
    )


def test_normal_user_cannot_update_a_profile_using_update_profile_mutation(
    rf, user_gql_client, service_factory
):
    profile = ProfileWithPrimaryEmailFactory(first_name="Joe")
    service_factory(service_type=ServiceType.YOUTH_MEMBERSHIP)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        mutation {
            updateProfile(
                input: {
                    serviceType: ${service_type},
                    profile: {
                        id: \"${id}\",
                        firstName: \"${first_name}\",
                    }
                }
            ) {
                profile {
                    firstName
                }
            }
        }
    """
    )
    query = t.substitute(
        service_type=ServiceType.YOUTH_MEMBERSHIP.name,
        id=to_global_id("ProfileNode", profile.pk),
        first_name="John",
    )
    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed
    assert executed["errors"][0]["message"] == _(
        "You do not have permission to perform this action."
    )
    assert Profile.objects.get(pk=profile.pk).first_name == profile.first_name


def test_normal_user_can_query_his_own_profile(rf, user_gql_client):
    profile = ProfileFactory(user=user_gql_client.user)
    request = rf.post("/graphql")
    request.user = user_gql_client.user
    query = """
        {
            myProfile {
                firstName
                lastName
            }
        }
    """
    expected_data = {
        "myProfile": {"firstName": profile.first_name, "lastName": profile.last_name}
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_query_his_own_profiles_sensitivedata(rf, user_gql_client):
    profile = ProfileFactory(user=user_gql_client.user)
    sensitive_data = SensitiveDataFactory(profile=profile)
    request = rf.post("/graphql")
    request.user = user_gql_client.user
    query = """
        {
            myProfile {
                firstName
                sensitivedata {
                    ssn
                }
            }
        }
    """
    expected_data = {
        "myProfile": {
            "firstName": profile.first_name,
            "sensitivedata": {"ssn": sensitive_data.ssn},
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_can_query_his_own_profile_with_subscriptions(rf, user_gql_client):
    profile = ProfileFactory(user=user_gql_client.user)
    cat = SubscriptionTypeCategoryFactory(
        code="TEST-CATEGORY-1", label="Test Category 1"
    )
    type_1 = SubscriptionTypeFactory(
        subscription_type_category=cat, code="TEST-1", label="Test 1"
    )
    type_2 = SubscriptionTypeFactory(
        subscription_type_category=cat, code="TEST-2", label="Test 2"
    )
    Subscription.objects.create(profile=profile, subscription_type=type_1, enabled=True)
    Subscription.objects.create(
        profile=profile, subscription_type=type_2, enabled=False
    )
    request = rf.post("/graphql")
    request.user = user_gql_client.user
    query = """
        {
            myProfile {
                firstName
                lastName
                subscriptions {
                    edges {
                        node {
                            enabled
                            subscriptionType {
                                order
                                code
                                label
                                subscriptionTypeCategory {
                                    code
                                    label
                                }
                            }
                        }
                    }
                }
            }
        }
    """
    expected_data = {
        "myProfile": {
            "firstName": profile.first_name,
            "lastName": profile.last_name,
            "subscriptions": {
                "edges": [
                    {
                        "node": {
                            "enabled": True,
                            "subscriptionType": {
                                "order": 1,
                                "code": "TEST-1",
                                "label": "Test 1",
                                "subscriptionTypeCategory": {
                                    "code": "TEST-CATEGORY-1",
                                    "label": "Test Category 1",
                                },
                            },
                        }
                    },
                    {
                        "node": {
                            "enabled": False,
                            "subscriptionType": {
                                "order": 2,
                                "code": "TEST-2",
                                "label": "Test 2",
                                "subscriptionTypeCategory": {
                                    "code": "TEST-CATEGORY-1",
                                    "label": "Test Category 1",
                                },
                            },
                        }
                    },
                ]
            },
        }
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_normal_user_cannot_query_a_profile(rf, user_gql_client, profile, service):
    ServiceConnectionFactory(profile=profile, service=service)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            profile(id: "${id}", serviceType: ${service_type}) {
                firstName
                lastName
            }
        }
    """
    )

    query = t.substitute(
        id=relay.Node.to_global_id(ProfileNode._meta.name, profile.id),
        service_type=ServiceType.BERTH.name,
    )
    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed
    assert executed["errors"][0]["message"] == _(
        "You do not have permission to perform this action."
    )


def test_staff_user_can_query_a_profile_connected_to_service_he_is_admin_of(
    rf, user_gql_client, profile, group, service
):
    ServiceConnectionFactory(profile=profile, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            profile(id: "${id}", serviceType: ${service_type}) {
                firstName
                lastName
            }
        }
    """
    )

    query = t.substitute(
        id=relay.Node.to_global_id(ProfileNode._meta.name, profile.id),
        service_type=ServiceType.BERTH.name,
    )
    expected_data = {
        "profile": {"firstName": profile.first_name, "lastName": profile.last_name}
    }
    executed = user_gql_client.execute(query, context=request)
    assert dict(executed["data"]) == expected_data


def test_staff_user_cannot_query_a_profile_without_id(
    rf, user_gql_client, profile, group, service
):
    ServiceConnectionFactory(profile=profile, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            profile(serviceType: ${service_type}) {
                firstName
                lastName
            }
        }
    """
    )

    query = t.substitute(service_type=ServiceType.BERTH.name)
    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed


def test_staff_user_cannot_query_a_profile_without_service_type(
    rf, user_gql_client, profile, group, service
):
    ServiceConnectionFactory(profile=profile, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            profile(id: ${id}) {
                firstName
                lastName
            }
        }
    """
    )

    query = t.substitute(id=relay.Node.to_global_id(ProfileNode._meta.name, profile.id))
    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed


def test_staff_user_cannot_query_a_profile_with_service_type_that_is_not_connected(
    rf, user_gql_client, profile, group, service_factory
):
    service_berth = service_factory()
    service_youth = service_factory(service_type=ServiceType.YOUTH_MEMBERSHIP)
    ServiceConnectionFactory(profile=profile, service=service_berth)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service_youth)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            profile(id: "${id}", serviceType: ${service_type}) {
                firstName
                lastName
            }
        }
    """
    )

    query = t.substitute(
        id=relay.Node.to_global_id(ProfileNode._meta.name, profile.id),
        service_type=ServiceType.YOUTH_MEMBERSHIP.name,
    )
    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed
    assert "code" in executed["errors"][0]["extensions"]
    assert executed["errors"][0]["extensions"]["code"] == OBJECT_DOES_NOT_EXIST_ERROR


def test_staff_user_cannot_query_a_profile_with_service_type_that_he_is_not_admin_of(
    rf, user_gql_client, profile, group, service_factory
):
    service_berth = service_factory()
    service_youth = service_factory(service_type=ServiceType.YOUTH_MEMBERSHIP)
    ServiceConnectionFactory(profile=profile, service=service_berth)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service_youth)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            profile(id: "${id}", serviceType: ${service_type}) {
                firstName
                lastName
            }
        }
    """
    )

    query = t.substitute(
        id=relay.Node.to_global_id(ProfileNode._meta.name, profile.id),
        service_type=ServiceType.BERTH.name,
    )
    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed
    assert executed["errors"][0]["message"] == _(
        "You do not have permission to perform this action."
    )


def test_staff_user_cannot_query_sensitive_data_with_only_profile_permissions(
    rf, user_gql_client, profile, group, service
):
    SensitiveDataFactory(profile=profile)
    ServiceConnectionFactory(profile=profile, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            profile(id: "${id}", serviceType: ${service_type}) {
                sensitivedata {
                    ssn
                }
            }
        }
    """
    )

    query = t.substitute(
        id=relay.Node.to_global_id(ProfileNode._meta.name, profile.id),
        service_type=ServiceType.BERTH.name,
    )
    expected_data = {"profile": {"sensitivedata": None}}
    executed = user_gql_client.execute(query, context=request)
    assert "errors" not in executed
    assert dict(executed["data"]) == expected_data


def test_staff_user_can_query_sensitive_data_with_given_permissions(
    rf, user_gql_client, profile, group, service
):
    sensitive_data = SensitiveDataFactory(profile=profile)
    ServiceConnectionFactory(profile=profile, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    assign_perm("can_view_sensitivedata", group, service)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            profile(id: "${id}", serviceType: ${service_type}) {
                sensitivedata {
                    ssn
                }
            }
        }
    """
    )

    query = t.substitute(
        id=relay.Node.to_global_id(ProfileNode._meta.name, profile.id),
        service_type=ServiceType.BERTH.name,
    )
    expected_data = {"profile": {"sensitivedata": {"ssn": sensitive_data.ssn}}}
    executed = user_gql_client.execute(query, context=request)
    assert "errors" not in executed
    assert dict(executed["data"]) == expected_data


def test_staff_receives_null_sensitive_data_if_it_does_not_exist(
    rf, user_gql_client, profile, group, service
):
    ServiceConnectionFactory(profile=profile, service=service)
    user = user_gql_client.user
    user.groups.add(group)
    assign_perm("can_view_profiles", group, service)
    assign_perm("can_view_sensitivedata", group, service)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            profile(id: "${id}", serviceType: ${service_type}) {
                sensitivedata {
                    ssn
                }
            }
        }
    """
    )

    query = t.substitute(
        id=relay.Node.to_global_id(ProfileNode._meta.name, profile.id),
        service_type=ServiceType.BERTH.name,
    )
    expected_data = {"profile": {"sensitivedata": None}}
    executed = user_gql_client.execute(query, context=request)
    assert "errors" in executed
    assert dict(executed["data"]) == expected_data


def test_profile_node_exposes_key_for_federation_gateway(rf, anon_user_gql_client):
    request = rf.post("/graphql")

    query = """
        query {
            _service {
                sdl
            }
        }
    """

    executed = anon_user_gql_client.execute(query, context=request)
    assert (
        'type ProfileNode implements Node  @key(fields: "id")'
        in executed["data"]["_service"]["sdl"]
    )


def test_profile_connection_schema_matches_federated_schema(rf, anon_user_gql_client):
    request = rf.post("/graphql")

    query = """
        query {
            _service {
                sdl
            }
        }
    """

    executed = anon_user_gql_client.execute(query, context=request)
    assert (
        "type ProfileNodeConnection {   pageInfo: PageInfo!   "
        "edges: [ProfileNodeEdge]!   count: Int!   totalCount: Int! }"
        in executed["data"]["_service"]["sdl"]
    )


def test_can_query_claimable_profile_with_token(rf, user_gql_client):
    profile = ProfileFactory(user=None, first_name="John", last_name="Doe")
    claim_token = ClaimTokenFactory(profile=profile)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            claimableProfile(token: "${claimToken}") {
                id
                firstName
                lastName
            }
        }
        """
    )
    query = t.substitute(claimToken=claim_token.token)
    expected_data = {
        "claimableProfile": {
            "id": to_global_id(type="ProfileNode", id=profile.id),
            "firstName": profile.first_name,
            "lastName": profile.last_name,
        }
    }
    executed = user_gql_client.execute(query, context=request)

    assert "errors" not in executed
    assert dict(executed["data"]) == expected_data


def test_cannot_query_claimable_profile_with_user_already_attached(
    rf, user_gql_client, profile
):
    claim_token = ClaimTokenFactory(profile=profile)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            claimableProfile(token: "${claimToken}") {
                id
            }
        }
        """
    )
    query = t.substitute(claimToken=claim_token.token)
    executed = user_gql_client.execute(query, context=request)

    assert "errors" in executed


def test_cannot_query_claimable_profile_with_expired_token(rf, user_gql_client):
    profile = ProfileFactory(user=None)
    claim_token = ClaimTokenFactory(
        profile=profile, expires_at=timezone.now() - timedelta(days=1)
    )
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        {
            claimableProfile(token: "${claimToken}") {
                id
            }
        }
        """
    )
    query = t.substitute(claimToken=claim_token.token)
    executed = user_gql_client.execute(query, context=request)

    assert "errors" in executed
    assert executed["errors"][0]["extensions"]["code"] == TOKEN_EXPIRED_ERROR


def test_user_can_claim_claimable_profile_without_existing_profile(rf, user_gql_client):
    profile = ProfileWithPrimaryEmailFactory(
        user=None, first_name="John", last_name="Doe"
    )
    claim_token = ClaimTokenFactory(profile=profile)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        mutation {
            claimProfile(
                input: {
                    token: "${claimToken}",
                    profile: {
                        firstName: "Joe",
                        nickname: "Joey"
                    }
                }
            ) {
                profile {
                    id
                    firstName
                    lastName
                    nickname
                }
            }
        }
        """
    )
    query = t.substitute(claimToken=claim_token.token)
    expected_data = {
        "claimProfile": {
            "profile": {
                "id": to_global_id(type="ProfileNode", id=profile.id),
                "firstName": "Joe",
                "nickname": "Joey",
                "lastName": profile.last_name,
            }
        }
    }
    executed = user_gql_client.execute(query, context=request)

    assert "errors" not in executed
    assert dict(executed["data"]) == expected_data
    profile.refresh_from_db()
    assert profile.user == user_gql_client.user
    assert profile.claim_tokens.count() == 0


def test_user_cannot_claim_claimable_profile_if_token_expired(rf, user_gql_client):
    profile = ProfileWithPrimaryEmailFactory(
        user=None, first_name="John", last_name="Doe"
    )
    expired_claim_token = ClaimTokenFactory(
        profile=profile, expires_at=timezone.now() - timedelta(days=1)
    )
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        mutation {
            claimProfile(
                input: {
                    token: "${claimToken}",
                    profile: {
                        firstName: "Joe",
                        nickname: "Joey"
                    }
                }
            ) {
                profile {
                    id
                    firstName
                    lastName
                    nickname
                }
            }
        }
        """
    )
    query = t.substitute(claimToken=expired_claim_token.token)
    executed = user_gql_client.execute(query, context=request)

    assert "errors" in executed
    assert executed["errors"][0]["extensions"]["code"] == TOKEN_EXPIRED_ERROR


def test_user_cannot_claim_claimable_profile_with_existing_profile(rf, user_gql_client):
    ProfileWithPrimaryEmailFactory(user=user_gql_client.user)
    profile_to_claim = ProfileFactory(user=None, first_name="John", last_name="Doe")
    expired_claim_token = ClaimTokenFactory(profile=profile_to_claim)
    request = rf.post("/graphql")
    request.user = user_gql_client.user

    t = Template(
        """
        mutation {
            claimProfile(
                input: {
                    token: "${claimToken}",
                    profile: {
                        firstName: "Joe",
                        nickname: "Joey"
                    }
                }
            ) {
                profile {
                    id
                    firstName
                    lastName
                    nickname
                }
            }
        }
        """
    )
    query = t.substitute(claimToken=expired_claim_token.token)
    executed = user_gql_client.execute(query, context=request)

    assert "errors" in executed
    assert executed["errors"][0]["extensions"]["code"] == API_NOT_IMPLEMENTED_ERROR
