import graphene
from django.db import transaction
from django.db.utils import IntegrityError
from graphene import relay
from graphene_django.types import DjangoObjectType
from graphql_jwt.decorators import login_required

from open_city_profile.exceptions import ServiceAlreadyExistsError

from .enums import ServiceType
from .models import AllowedDataField, Service, ServiceConnection

AllowedServiceType = graphene.Enum.from_enum(
    ServiceType, description=lambda e: e.label if e else ""
)


class AllowedDataFieldNode(DjangoObjectType):
    label = graphene.String()

    class Meta:
        model = AllowedDataField
        interfaces = (relay.Node,)


class ServiceNode(DjangoObjectType):
    type = AllowedServiceType(source="service_type")
    title = graphene.String()
    description = graphene.String()

    class Meta:
        model = Service
        filter_fields = []
        interfaces = (relay.Node,)


class ServiceConnectionType(DjangoObjectType):
    class Meta:
        model = ServiceConnection
        fields = ("service", "created_at", "enabled")
        filter_fields = []
        interfaces = (relay.Node,)


class ServiceInput(graphene.InputObjectType):
    type = AllowedServiceType()


class ServiceConnectionInput(graphene.InputObjectType):
    service = ServiceInput(required=True)
    enabled = graphene.Boolean()


class AddServiceConnectionMutation(relay.ClientIDMutation):
    class Input:
        service_connection = ServiceConnectionInput(required=True)

    service_connection = graphene.Field(ServiceConnectionType)

    @classmethod
    @login_required
    @transaction.atomic
    def mutate_and_get_payload(cls, root, info, **input):
        service_connection_data = input.pop("service_connection")
        service_data = service_connection_data.get("service")
        service_type = service_data.get("type")
        service = Service.objects.get(service_type=service_type)
        try:
            service_connection = ServiceConnection.objects.create(
                profile=info.context.user.profile,
                service=service,
                enabled=service_connection_data.get("enabled", True),
            )
        except IntegrityError:
            raise ServiceAlreadyExistsError("Service connection already exists")
        return AddServiceConnectionMutation(service_connection=service_connection)


class Mutation(graphene.ObjectType):
    add_service_connection = AddServiceConnectionMutation.Field(
        description="Connect the currently authenticated user's profile to the given service.\n\nRequires "
        "authentication.\n\nPossible error codes:\n\n* `SERVICE_CONNECTION_ALREADY_EXISTS_ERROR`: "
        "Returned if the currently authenticated user's profile is already connected to the given service."
    )
