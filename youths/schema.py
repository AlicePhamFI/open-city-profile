import uuid

import graphene
from django.db import transaction
from django.utils import timezone
from django.utils.translation import override
from django.utils.translation import ugettext_lazy as _
from django_ilmoitin.utils import send_notification
from graphene import relay
from graphene_django.types import DjangoObjectType
from graphql import GraphQLError
from graphql_jwt.decorators import login_required
from graphql_relay.node.node import from_global_id

from open_city_profile.exceptions import ProfileHasNoPrimaryEmailError
from profiles.models import Email, Profile

from .enums import NotificationType, YouthLanguage
from .models import YouthProfile

with override("en"):
    LanguageAtHome = graphene.Enum.from_enum(
        YouthLanguage, description=lambda e: e.label if e else ""
    )


class YouthProfileType(DjangoObjectType):
    membership_number = graphene.String(
        source="membership_number", description="Youth's membership number"
    )

    language_at_home = LanguageAtHome(
        source="language_at_home",
        description="The language which is spoken in the youth's home.",
    )

    class Meta:
        model = YouthProfile
        exclude = ("id", "approval_token", "language_at_home")


# Abstract base fields
class YouthProfileFields(graphene.InputObjectType):
    school_name = graphene.String(description="The youth's school name.")
    school_class = graphene.String(description="The youth's school class.")
    language_at_home = LanguageAtHome(
        description="The language which is spoken in the youth's home."
    )
    approver_first_name = graphene.String(
        description="The youth's (supposed) guardian's first name."
    )
    approver_last_name = graphene.String(
        description="The youth's (supposed) guardian's last name."
    )
    approver_phone = graphene.String(
        description="The youth's (supposed) guardian's phone number."
    )
    approver_email = graphene.String(
        description="The youth's (supposed) guardian's email address which will be used to send approval requests."
    )
    birth_date = graphene.Date(
        required=False,
        description="The youth's birth date. This is used for example to calculate if the youth is a minor or not.",
    )


# Subset of abstract fields are required for creation
class CreateMyYouthProfileInput(YouthProfileFields):
    approver_email = graphene.String(required=True, description="The approver's email address.")
    birth_date = graphene.Date(
        required=True,
        description="The youth's birth date. This is used for example to calculate if the youth is a minor or not.",
    )


class CreateMyYouthProfileMutation(relay.ClientIDMutation):
    class Input:
        youth_profile = CreateMyYouthProfileInput(required=True)

    youth_profile = graphene.Field(YouthProfileType)

    @classmethod
    @login_required
    @transaction.atomic
    def mutate_and_get_payload(cls, root, info, **input):
        input_data = input.get("youth_profile")

        profile = Profile.objects.get(user=info.context.user)

        youth_profile, created = YouthProfile.objects.get_or_create(
            profile=profile, defaults=input_data
        )

        youth_profile.approval_token = uuid.uuid4()
        send_notification(
            email=youth_profile.approver_email,
            notification_type=NotificationType.YOUTH_PROFILE_CONFIRMATION_NEEDED.value,
            context={"youth_profile": youth_profile},
        )
        youth_profile.approval_notification_timestamp = timezone.now()
        youth_profile.save()

        return CreateMyYouthProfileMutation(youth_profile=youth_profile)


class UpdateYouthProfileInput(YouthProfileFields):
    resend_request_notification = graphene.Boolean(
        description="If set to `true`, a new approval token is generated and a new email notification is sent to the"
                    "approver's email address."
    )


class UpdateMyYouthProfileMutation(relay.ClientIDMutation):
    class Input:
        youth_profile = UpdateYouthProfileInput(required=True)

    youth_profile = graphene.Field(YouthProfileType)

    @classmethod
    @login_required
    @transaction.atomic
    def mutate_and_get_payload(cls, root, info, **input):
        input_data = input.get("youth_profile")
        resend_request_notification = input_data.pop(
            "resend_request_notification", False
        )

        profile = Profile.objects.get(user=info.context.user)
        youth_profile, created = YouthProfile.objects.get_or_create(profile=profile)

        for field, value in input_data.items():
            setattr(youth_profile, field, value)
        youth_profile.save()

        if resend_request_notification:
            youth_profile.approval_token = uuid.uuid4()
            send_notification(
                email=youth_profile.approver_email,
                notification_type=NotificationType.YOUTH_PROFILE_CONFIRMATION_NEEDED.value,
                context={"youth_profile": youth_profile},
            )
            youth_profile.approval_notification_timestamp = timezone.now()
            youth_profile.save()

        return UpdateMyYouthProfileMutation(youth_profile=youth_profile)


class ApproveYouthProfileFields(YouthProfileFields):
    # TODO: Photo usage needs to be present also in Create/Modify, but it cannot be given, if the youth is under 15
    photo_usage_approved = graphene.Boolean(
        description="`true` if the youth is allowed to be photographed."
    )


class ApproveYouthProfileMutation(relay.ClientIDMutation):
    class Input:
        approval_token = graphene.String(
            required=True,
            description="This is the token with which a youth profile may be fetched for approval purposes."
        )
        approval_data = ApproveYouthProfileFields(
            required=True,
            description="The youth profile data to approve. This may contain modifications done by the approver."
        )

    youth_profile = graphene.Field(YouthProfileType)

    @classmethod
    @transaction.atomic
    def mutate_and_get_payload(cls, root, info, **input):
        youth_data = input.get("approval_data")
        token = input.get("approval_token")

        youth_profile = YouthProfile.objects.get(approval_token=token)

        for field, value in youth_data.items():
            setattr(youth_profile, field, value)

        try:
            email = youth_profile.profile.get_primary_email()
        except Email.DoesNotExist:
            raise ProfileHasNoPrimaryEmailError(
                "Cannot send email confirmation, youth profile has no primary email address."
            )

        youth_profile.approved_time = timezone.now()
        youth_profile.approval_token = ""  # invalidate
        youth_profile.save()
        send_notification(
            email=email.email,
            notification_type=NotificationType.YOUTH_PROFILE_CONFIRMED.value,
            context={"youth_profile": youth_profile},
        )
        return ApproveYouthProfileMutation(youth_profile=youth_profile)


class Query(graphene.ObjectType):
    # TODO: Add the complete list of error codes
    youth_profile = graphene.Field(
        YouthProfileType,
        profile_id=graphene.ID(),
        description="Get a youth profile by youth profile ID.\n\n**NOTE:** Currently this requires `superuser` "
                    "credentials. This is going to be changed at one point so that service-specific staff "
                    "credentials and service type are used, just like the rest of the admin-type queries.\n\n"
                    "Possible error codes:\n\n* `TODO`",
    )
    # TODO: Add the complete list of error codes
    youth_profile_by_approval_token = graphene.Field(
        YouthProfileType,
        token=graphene.String(),
        description="Get a youth profile by approval token. \n\nDoesn't require authentication.\n\nPossible "
                    "error codes:\n\n* `TODO`",
    )

    @login_required
    def resolve_youth_profile(self, info, **kwargs):
        profile_id = kwargs.get("profile_id")

        if profile_id is not None and not info.context.user.is_superuser:
            raise GraphQLError(_("Query by id not allowed for regular users."))

        if info.context.user.is_superuser:
            return YouthProfile.objects.get(profile_id=from_global_id(profile_id)[1])
        return YouthProfile.objects.get(profile__user=info.context.user)

    def resolve_youth_profile_by_approval_token(self, info, **kwargs):
        return YouthProfile.objects.get(approval_token=kwargs.get("token"))


class Mutation(graphene.ObjectType):
    # TODO: Add the complete list of error codes
    create_my_youth_profile = CreateMyYouthProfileMutation.Field(
        description="Creates a new youth profile and links it to the currently authenticated user's profile.\n\n"
                    "When the youth profile has been created, a notification is sent to the youth profile's approver "
                    "whose contact information is given in the input.\n\nRequires authentication.\n\nPossible error "
                    "codes:\n\n* `TODO`"
    )
    # TODO: Add the complete list of error codes
    update_my_youth_profile = UpdateMyYouthProfileMutation.Field(
        description="Updates the youth profile which belongs to the profile of the currently authenticated user.\n\n"
                    "The `resend_request_notification` parameter may be used to send a notification to the youth "
                    "profile's approver whose contact information is in the youth profile.\n\nRequires authentication."
                    "\n\nPossible error codes:\n\n* `TODO`"
    )
    # TODO: Add the complete list of error codes
    approve_youth_profile = ApproveYouthProfileMutation.Field(
        description="Fetches a youth profile using the given token, updates the data based on the given input data and"
                    "approves the youth profile so that it is considered active. A confirmation is sent to the youth"
                    "profile's email address after a successful approval.\n\nThe token is no longer valid after"
                    "it's been used to approve the youth profile.\n\nRequires authentication.\n\nPossible error "
                    "codes:\n\n* `PROFILE_HAS_NO_PRIMARY_EMAIL_ERROR`: Returned if the youth profile doesn't have a "
                    "primary email address.\n\n* `TODO`"
    )
