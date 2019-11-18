import factory.random
import pytest
from django.contrib.auth.models import AnonymousUser
from graphene.test import Client as GraphQLClient

from open_city_profile.schema import schema
from open_city_profile.tests.factories import SuperuserFactory, UserFactory


@pytest.fixture(autouse=True)
def allow_global_access_to_test_db(transactional_db):
    pass


@pytest.fixture(autouse=True)
def set_random_seed():
    factory.random.reseed_random(666)


@pytest.fixture(autouse=True)
def email_setup(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def anon_user():
    return AnonymousUser()


@pytest.fixture
def superuser():
    return SuperuserFactory()


@pytest.fixture
def gql_client():
    gql_client = GraphQLClient(schema)
    return gql_client


@pytest.fixture
def anon_user_gql_client(anon_user):
    gql_client = GraphQLClient(schema)
    gql_client.user = anon_user
    return gql_client


@pytest.fixture
def user_gql_client(user):
    gql_client = GraphQLClient(schema)
    gql_client.user = user
    return gql_client


@pytest.fixture
def superuser_gql_client(superuser):
    gql_client = GraphQLClient(schema)
    gql_client.user = superuser
    return gql_client
