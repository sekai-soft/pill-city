from typing import List, Union

from bson import ObjectId

from pillcity.models import User
from pillcity.utils.profiling import timer

from .cache import r

RUserByUserId = "userByUserId"
RUserByOid = "userByOid"

# Cache structure within Redis
# "userByUserId" -> user_id  -> serialized user
# "userByOid"    -> str(oid) -> serialized user


def set_in_user_cache(user: User):
    r.hset(RUserByUserId, user.user_id, user.to_json())
    r.hset(RUserByOid, str(user.id), user.to_json())


@timer
def get_in_user_cache_by_user_id(user_id: str) -> Union[User, bool]:
    r_user = r.hget(RUserByUserId, user_id)
    if not r_user:
        return False
    r_user = r_user.decode("utf-8")
    return User.from_json(r_user)


@timer
def get_in_user_cache_by_oid(oid: ObjectId) -> Union[User, bool]:
    r_user = r.hget(RUserByOid, str(oid))
    if not r_user:
        return False
    r_user = r_user.decode("utf-8")
    return User.from_json(r_user)


@timer
def populate_user_cache():
    for user in User.objects():
        set_in_user_cache(user)


def get_users_in_user_cache() -> List[User]:
    res = []
    for oid, r_user in r.hgetall(RUserByOid).items():
        r_user = r_user.decode("utf-8")
        res.append(User.from_json(r_user))
    return list(sorted(res, key=lambda u: u.id))
