import os
import uuid
from typing import List

import werkzeug
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restful import Resource, fields, marshal_with, reqparse

from pillcity.daos.media import create_media, get_media, get_media_page
from pillcity.daos.user import find_user
from pillcity.models.media import Media

GetMediaPageCount = 4


# Cache structure within Redis
# "mediaUrl" -> object_name -> "media url"(space)"media url expire time in seconds"


def get_media_url(object_name: str) -> str:
    """
    Get the publicly accessible URL to a media
    """
    # todo: duplicated with get_rss_notifications_url
    api_domain = os.environ["API_DOMAIN"]
    protocol = "https"
    # todo: lol so hack
    if "localhost:" in api_domain:
        protocol = "http"

    return f"{protocol}://{api_domain}/p/{object_name}"


def get_media_url_v2(object_name: str) -> dict:
    """
    Get a dict representing a media that could have been processed (or not)
    """
    media = get_media(object_name)
    if not media.processed:
        return {"original_url": get_media_url(media.id), "processed": False}
    return {
        "original_url": get_media_url(media.id),
        "processed": True,
        "processed_url": get_media_url(media.get_processed_object_name()),
        "width": media.width,
        "height": media.height,
        "dominant_color_hex": media.dominant_color_hex,
    }


class MediaUrlV2(fields.Raw):
    def format(self, object_name: str):
        return get_media_url_v2(object_name)


class MediaUrlsV2(fields.Raw):
    def format(self, media_list: List[Media]):
        if not media_list:
            return []
        return list(map(lambda m: get_media_url_v2(m.id), media_list))


media_fields = {
    "object_name": fields.String(attribute="id"),
    "media_url_v2": MediaUrlV2(attribute="id"),
}


post_media_parser = reqparse.RequestParser()
post_media_parser.add_argument(
    "file", type=werkzeug.datastructures.FileStorage, location="files", required=True
)


get_media_parser = reqparse.RequestParser()
get_media_parser.add_argument("page", type=int, required=True, location="args")


class MediaResource(Resource):
    @jwt_required()
    def post(self):
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return {"msg": f"User {user_id} is not found"}, 404

        args = post_media_parser.parse_args()
        media_file = args["file"]
        object_name_stem = f"media/{uuid.uuid4()}"
        media_object = create_media(media_file, object_name_stem, user)
        if not media_object:
            return {"msg": f"Blacklisted image type"}, 400
        return {
            "object_name": media_object.id,
        }, 201

    @jwt_required()
    @marshal_with(media_fields)
    def get(self):
        user_id = get_jwt_identity()
        user = find_user(user_id)
        if not user:
            return {"msg": f"User {user_id} is not found"}, 404

        args = get_media_parser.parse_args()
        page_number = args["page"]
        if page_number < 1:
            return {"msg": f"Invalid page number"}, 400

        return get_media_page(user, page_number - 1, GetMediaPageCount), 200


def check_media_object_names(media_object_names: List[str], limit: int) -> List[Media]:
    media_objects = []
    for media_object_name in media_object_names[:limit]:
        media_object = get_media(media_object_name)
        if media_object:
            media_objects.append(media_object)
    return media_objects
