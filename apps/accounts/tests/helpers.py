from apps.accounts.models import User
from apps.tenancy.models import College
from apps.tenancy.services import college_context, create_college

PASSWORD = "correct horse battery 42"


def make_college(code: str) -> College:
    return create_college(f"College {code.upper()}", code)


def make_user(
    college: College,
    username: str,
    password: str = PASSWORD,
    email: str = "",
    **fields: object,
) -> User:
    with college_context(college.id):
        return User.objects.create_user(username, password, college=college, email=email, **fields)
