import os
from typing import List, Optional, Union

from mongoengine import NotUniqueError
from werkzeug.security import check_password_hash, generate_password_hash

from pillcity.models import Media, NotifyingAction, User
from pillcity.utils.make_uuid import make_dashless_uuid
from pillcity.utils.profiling import timer

from .exceptions import BadRequest, NotFound, UnauthorizedAccess
from .media import delete_media, use_media
from .notification import create_notification
from .user_cache import (
    get_in_user_cache_by_user_id,
    get_users_in_user_cache,
    set_in_user_cache,
)

AvailableProfilePics = [
    "pill1.png",
    "pill2.png",
    "pill3.png",
    "pill4.png",
    "pill5.png",
    "pill6.png",
]


def sign_up(
    user_id: str,
    password: str,
    display_name: Optional[str] = None,
    email: Optional[str] = None,
) -> bool:
    """
    Signs up a user

    :param user_id: Unique user ID
    :param password: Password
    :param display_name: Display name
    :param email: Email
    :return: Whether creation is successful. If False, id is already taken
    """
    new_user = User()
    new_user.user_id = user_id
    new_user.password = generate_password_hash(password)
    if display_name:
        new_user.display_name = display_name
    if email:
        new_user.email = email
    try:
        new_user.save()
        if os.getenv("OFFICIAL", None):
            official_user_id = os.getenv("OFFICIAL")
            official_user = find_user(official_user_id)
            if official_user:
                follow(new_user, official_user)
        set_in_user_cache(new_user)
    except NotUniqueError:
        return False
    return True


def sign_in(user_id, password):
    """
    Attempts to sign in a user

    :param (str) user_id: user id
    :param (str) password: password
    :return (User|bool): Whether the user exists
    :exception (RuntimeError): If more than one user for the user id is found
    """
    user = get_in_user_cache_by_user_id(user_id)
    if not user:
        return False
    if not check_password_hash(user.password, password):
        return False
    return user


@timer
def find_user(user_id: str) -> Union[User, bool]:
    """
    Finds the user

    :param user_id: user id
    :return: Whether the user exists
    """
    return get_in_user_cache_by_user_id(user_id)


def find_user_or_raise(user_id: str) -> User:
    """
    Finds the user, or otherwise raise
    """
    user = find_user(user_id)
    if not user:
        raise NotFound()
    return user


def get_users(user_id):
    """
    Get all other users besides the current user

    :param (str) user_id: user id of the current user
    :return (List[User]): All other users besides the current user
    """
    return list(filter(lambda u: u.user_id != user_id, get_users_in_user_cache()))


def search_users(keyword: str) -> List[User]:
    """
    Search for users by a keyword.

    :param keyword: The keyword
    :return: List of matching users
    """
    if not keyword:
        return []
    keyword = keyword.lower()
    matched_users = []
    for user in get_users_in_user_cache():
        if keyword in user.user_id.lower() or (
            user.display_name and keyword in user.display_name.lower()
        ):
            matched_users.append(user)
    return matched_users


def follow(self: User, user: User):
    """
    Follow a user

    :param self: The acting user
    :param user: the followed user
    """
    if user in self.followings or user in self.blocking:
        raise BadRequest()
    self.followings.append(user)
    self.save()
    set_in_user_cache(self)
    create_notification(
        self=self,
        notifying_href="",
        notifying_summary="",
        notifying_action=NotifyingAction.Follow,
        notified_href="",
        notified_summary="",
        owner=user,
    )


def unfollow(self: User, user: User):
    """
    Remove a following

    :param self: The acting user
    :param user: the unfollowed user
    """
    if user not in self.followings:
        raise BadRequest()
    self.followings = list(filter(lambda u: u.id != user.id, self.followings))
    self.save()
    set_in_user_cache(self)


def update_profile_pic(self, profile_pic):
    """
    Update a user's profile picture

    :param (User) self: The acting user
    :param (str) profile_pic: The picked profile picture
    """
    if profile_pic in AvailableProfilePics:
        self.profile_pic = profile_pic
        self.save()
        set_in_user_cache(self)
    else:
        raise UnauthorizedAccess()


def update_avatar(self: User, avatar_media: Media):
    """
    Update a user's avatar

    :param self: The acting user
    :param avatar_media: The new avatar
    """
    if self.avatar:
        delete_media(self.avatar)
    use_media(avatar_media)
    self.avatar = avatar_media
    self.save()
    set_in_user_cache(self)


def update_display_name(self: User, display_name: str):
    """
    Update a user's display name

    :param self: The acting user
    :param display_name: New display name
    """
    self.display_name = display_name
    self.save()
    set_in_user_cache(self)


def check_email(email: str) -> bool:
    """
    Check whether an email address is available

    :param email: Checked email
    :return: Whether an email address is available
    """
    users = get_users_in_user_cache()
    for user in users:
        if user.email == email:
            return False
    return True


def update_email(self: User, email: str) -> bool:
    """
    Update a user's email

    :param self: The acting user
    :param email: New email
    :return Whether this email is already taken
    """
    if not check_email(email):
        return False
    self.email = email
    self.save()
    set_in_user_cache(self)
    return True


def get_email(self: User) -> Optional[str]:
    """
    Get a user's email

    :param self: The acting user
    """
    user = get_in_user_cache_by_user_id(self.user_id)
    if not user:
        return
    return user.email


def get_rss_token(self: User) -> Optional[str]:
    """
    Get a user's RSS token

    :param self: The acting user
    :return: The user's RSS token
    """
    user = get_in_user_cache_by_user_id(self.user_id)
    if not user:
        return
    return user.rss_token


def get_rss_notifications_url(self: User, types: str = "") -> str:
    api_domain = os.environ["API_DOMAIN"]
    protocol = "https"
    # todo: lol so hack
    if "localhost:" in api_domain:
        protocol = "http"
    # todo: this is duplicate with the actual path in app.py
    base_url = f"{protocol}://{api_domain}/rss/{self.user_id}/notifications?token={self.rss_token}"
    if not types:
        return base_url
    return base_url + f"&types={types}"


def rotate_rss_token(self: User) -> str:
    """
    Rotate a user's RSS token

    :param self: The acting user
    :return: The new RSS token
    """
    new_token = make_dashless_uuid()
    if get_user_by_rss_token(new_token):
        raise Exception("Duplicate RSS token. Please retry.")

    self.rss_token = new_token
    self.save()
    set_in_user_cache(self)
    return new_token


def delete_rss_token(self: User):
    """
    Rotate a user's RSS token

    :param self: The acting user
    """
    self.rss_token = None
    self.save()
    set_in_user_cache(self)


def get_user_by_rss_token(token: str) -> Optional[User]:
    """
    Get a user by RSS token

    :param token: The queried RSS token
    :return: The user found
    """
    for user in get_users_in_user_cache():
        if user.rss_token == token:
            return user
    return None


def block(self: User, user: User):
    """
    Block a user

    :param self: The acting user
    :param user: the blocked user
    """
    if user in self.blocking or user in self.followings:
        raise BadRequest()
    self.blocking.append(user)
    self.save()
    set_in_user_cache(self)


def unblock(self: User, user: User):
    """
    Unblock a user

    :param self: The acting user
    :param user: the unblocked user
    """
    if user not in self.blocking:
        raise BadRequest()
    self.blocking = list(filter(lambda u: u.id != user.id, self.blocking))
    self.save()
    set_in_user_cache(self)


def find_ghost_user_or_raise() -> User:
    ghost_user_id = os.environ["GHOST"]
    ghost_user = find_user(ghost_user_id)
    if not ghost_user:
        raise RuntimeError(f"Ghost user {ghost_user_id} does not exist")
    return ghost_user
