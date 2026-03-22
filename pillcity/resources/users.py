import re
import werkzeug
from bson import ObjectId
from flask_restful import reqparse, Resource, fields, marshal_with
from flask_jwt_extended import jwt_required, get_jwt_identity
from pillcity.daos.user import find_user, update_profile_pic, update_avatar, get_users, update_display_name, \
    search_users, update_email, get_email, get_rss_token, rotate_rss_token, delete_rss_token, \
    get_rss_notifications_url, find_user_or_raise
from pillcity.daos.user_cache import get_in_user_cache_by_oid, get_users_in_user_cache
from pillcity.daos.post import create_post
from pillcity.daos.rss import notifying_action_value_to_rss_code
from pillcity.daos.media import create_media
from pillcity.utils.now import now_seconds
from .media import get_media_url_v2


class UserId(fields.Raw):
    def format(self, value):
        return get_in_user_cache_by_oid(value).user_id


class UserCreatedAtSeconds(fields.Raw):
    def format(self, value):
        return get_in_user_cache_by_oid(value).created_at


class UserAvatarV2(fields.Raw):
    def format(self, value):
        avatar_media = get_in_user_cache_by_oid(value).avatar
        if not avatar_media:
            return None
        return get_media_url_v2(avatar_media.id)


class UserProfilePic(fields.Raw):
    def format(self, value):
        return get_in_user_cache_by_oid(value).profile_pic


class UserDisplayName(fields.Raw):
    def format(self, value):
        return get_in_user_cache_by_oid(value).display_name


user_fields = {
    'id': UserId(attribute='id'),
    'created_at_seconds': UserCreatedAtSeconds(attribute='id'),
    'avatar_url_v2': UserAvatarV2(attribute='id'),
    'profile_pic': UserProfilePic(attribute='id'),
    'display_name': UserDisplayName(attribute='id')
}


class Me(Resource):
    @jwt_required()
    @marshal_with(user_fields)
    def get(self):
        user_id = get_jwt_identity()
        return find_user_or_raise(user_id)


my_avatar_parser = reqparse.RequestParser()
my_avatar_parser.add_argument('file', type=werkzeug.datastructures.FileStorage, location='files', required=True)
# use str 1 as True to avoid form data boolean messiness
my_avatar_parser.add_argument('update_post', type=str, required=True, location='form')


class MyAvatar(Resource):
    @jwt_required()
    def post(self):
        # check user
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return {'msg': f'User {user_id} is not found'}, 404

        args = my_avatar_parser.parse_args()
        file = args['file']
        update_post = args['update_post']

        # the resulting object name looks like avatars/kt-1627815711477.jpeg
        # avatars prefix is made explicitly public readable
        # because it's faster to read a user's metadata, and we are fine with all avatars being public
        # BUG: the suffix was previously now_ms() // 1_000_000, meaning the timestamps where at ~1/3 hour scale
        object_name_stem = f"avatars/{user_id}-{str(now_seconds())}"
        avatar_media = create_media(file, object_name_stem, user)
        if not avatar_media:
            return {'msg': f"Disallowed image type"}, 400

        update_avatar(user, avatar_media)
        if update_post == '1':
            create_post(
                user,
                content='',
                is_public=True,
                circles=[],
                reshareable=True,
                reshared_from=None,
                media_list=[avatar_media],
                mentioned_users=[],
                is_update_avatar=True,
                poll_choices=[],
                poll_choice_media_object_names=[],
                poll_close_by=None
            )


class MyProfilePic(Resource):
    @jwt_required()
    def patch(self, user_profile_pic):
        """
        Update User profile pic
        """
        # check user
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return {'msg': f'User {user_id} is not found'}, 404

        update_profile_pic(user, user_profile_pic)


my_display_name_parser = reqparse.RequestParser()
my_display_name_parser.add_argument('display_name', type=str, required=True)


class MyDisplayName(Resource):
    @jwt_required()
    def post(self):
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return {'msg': f'User {user_id} is not found'}, 404

        args = my_display_name_parser.parse_args()
        display_name = args['display_name']
        update_display_name(user, display_name)


my_email_parser = reqparse.RequestParser()
my_email_parser.add_argument('email', type=str, required=True)


class MyEmail(Resource):
    @jwt_required()
    def get(self):
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return {'msg': f'User {user_id} is not found'}, 404
        return {
            "email": get_email(user)
        }

    @jwt_required()
    def post(self):
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return {'msg': f'User {user_id} is not found'}, 404

        args = my_email_parser.parse_args()
        email = args['email']
        if re.fullmatch(r'(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))', email):
            if not update_email(user, email):
                return {'msg': 'Email taken'}, 409
            else:
                return {'msg': 'Success'}, 201
        else:
            return {'msg': 'Invalid email'}, 400


class IsFollowing(fields.Raw):
    def format(self, value):
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return False
        return ObjectId(value) in map(lambda u: u.id, user.followings)


class IsBlocking(fields.Raw):
    def format(self, value):
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return False
        return ObjectId(value) in map(lambda u: u.id, user.blocking)


user_with_following_and_blocking_fields = dict({
    'is_following': IsFollowing(attribute='id'),
    'is_blocking': IsBlocking(attribute='id'),
}, **user_fields)


class Users(Resource):
    @jwt_required()
    @marshal_with(user_with_following_and_blocking_fields)
    def get(self):
        """
        Get all users other than the logged in user
        """
        user_id = get_jwt_identity()
        # TODO: pretty inefficient because all Users needs to call get user by oid once more lol
        return get_users(user_id), 200


searched_user_parser = reqparse.RequestParser()
searched_user_parser.add_argument('keyword', type=str, required=True)


class SearchedUsers(Resource):
    @jwt_required()
    @marshal_with(user_with_following_and_blocking_fields)
    def post(self):
        """
        Get all users that match a keyword to the search criteria
        Currently the search criteria is either the user ID or the display name contains the keyword
        """
        args = searched_user_parser.parse_args()
        return search_users(args['keyword'])


class User(Resource):
    @jwt_required()
    @marshal_with(user_with_following_and_blocking_fields)
    def get(self, user_id):
        """
        Get a specific user by ID
        """
        user = find_user(user_id)
        if not user:
            return {'msg': f'User {user_id} is not found'}, 404
        return user


class UserFollowingCount(fields.Raw):
    def format(self, value):
        return len(get_in_user_cache_by_oid(value).followings)


class UserFollowerCount(fields.Raw):
    def format(self, value):
        count = 0
        for user in get_users_in_user_cache():
            if value in map(lambda u: u.id, user.followings):
                count += 1
        return count


user_following_counts_fields = {
    "following_count": UserFollowingCount(attribute='id'),
    "follower_count": UserFollowerCount(attribute='id')
}


class MyFollowingCounts(Resource):
    @jwt_required()
    @marshal_with(user_following_counts_fields)
    def get(self):
        user_id = get_jwt_identity()
        user = find_user_or_raise(user_id)
        return user


class MyFollowings(Resource):
    @jwt_required()
    @marshal_with(user_fields)
    def get(self):
        user_id = get_jwt_identity()
        user = find_user_or_raise(user_id)
        return user.followings


class MyBlocking(Resource):
    @jwt_required()
    @marshal_with(user_fields)
    def get(self):
        user_id = get_jwt_identity()
        user = find_user_or_raise(user_id)
        return user.blocking


class MyRssToken(Resource):
    @jwt_required()
    def get(self):
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return {'msg': f'User {user_id} is not found'}, 404

        return {
            "rss_token": get_rss_token(user),
            'rss_notifications_url': get_rss_notifications_url(user),
            'notifying_action_to_rss_code': notifying_action_value_to_rss_code
        }

    @jwt_required()
    def post(self):
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return {'msg': f'User {user_id} is not found'}, 404

        return {
            "rss_token": rotate_rss_token(user),
            'rss_notifications_url': get_rss_notifications_url(user),
            'notifying_action_to_rss_code': notifying_action_value_to_rss_code
        }, 201

    @jwt_required()
    def delete(self):
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return {'msg': f'User {user_id} is not found'}, 404

        delete_rss_token(user)
        return {
            "msg": "success"
        }, 201
