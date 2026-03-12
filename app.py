import logging
import os
import re
from os import urandom

from dotenv import load_dotenv

load_dotenv()  # reads variables from a .env file and sets them in os.environ

import sentry_sdk
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, stream_with_context
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token
from flask_restful import Api
from mongoengine import connect
from sentry_sdk.integrations.flask import FlaskIntegration

from pillcity.daos.invitation_code import check_invitation_code, claim_invitation_code
from pillcity.daos.rss import (
    get_rss_notifications_xml,
    notifying_action_to_rss_code,
    rss_code_to_notifying_action,
)
from pillcity.daos.user import check_email, get_user_by_rss_token, sign_in, sign_up
from pillcity.daos.user_cache import populate_user_cache
from pillcity.resources.blocks import Blocks
from pillcity.resources.circles import Circle, CircleMember, CircleName, Circles
from pillcity.resources.comments import Comment, Comments, NestedComment, NestedComments
from pillcity.resources.followings import Following
from pillcity.resources.invitations_codes import (
    InvitationCode,
    InvitationCodes,
)
from pillcity.resources.link_preview import LinkPreview
from pillcity.resources.media import MediaResource
from pillcity.resources.media_sets import (
    MediaSet,
    MediaSetMedia,
    MediaSetName,
    MediaSetPublic,
    MediaSets,
)
from pillcity.resources.notifications import (
    NotificationRead,
    Notifications,
    NotificationsAllRead,
)
from pillcity.resources.password_reset import ForgetPassword, ResetPassword
from pillcity.resources.poll import Vote
from pillcity.resources.posts import Home, Post, PostMedia, Posts, Profile
from pillcity.resources.reactions import Reaction, Reactions
from pillcity.resources.users import (
    Me,
    MyAvatar,
    MyBlocking,
    MyDisplayName,
    MyEmail,
    MyFollowingCounts,
    MyFollowings,
    MyProfilePic,
    MyRssToken,
    SearchedUsers,
    User,
    Users,
)
from pillcity.utils.now import now_seconds
from pillcity.utils.s3 import get_s3_client

logging.basicConfig(level=logging.INFO)

# Sentry
if os.getenv("SENTRY_DSN"):
    logging.info("Enabling sentry")
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[FlaskIntegration()],
        # no performance monitoring
        traces_sample_rate=0,
    )
else:
    logging.info("Not enabling sentry")

# Flask app
app = Flask(__name__)
app.secret_key = urandom(24)
max_mb_per_media = 40
app.config["MAX_CONTENT_LENGTH"] = max_mb_per_media * 1024 * 1024
app.config["BUNDLE_ERRORS"] = True

# Database & Caches
connect(host=os.environ["MONGODB_URI"])
populate_user_cache()

# JWT
access_token_expires = int(os.environ["JWT_ACCESS_TOKEN_EXPIRES"])
app.config["JWT_SECRET_KEY"] = os.environ["JWT_SECRET_KEY"]
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = access_token_expires
JWTManager(app)

# CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Open Registration
is_open_registration = os.environ.get("OPEN_REGISTRATION", "false") == "true"
if is_open_registration:
    logging.info("Open registration")
else:
    logging.info("Invite-only")

# Git commit
git_commit = os.getenv("GIT_COMMIT", None)
if git_commit:
    git_commit = git_commit[:7]
logging.info(f"Git commit {git_commit}")


# Other routes
@app.route("/", methods=["GET"])
def _root():
    return "pill.city api"


@app.route("/api/signIn", methods=["POST"])
def _sign_in():
    """
    Signs in a user by giving out access token
    """
    if not request.is_json:
        return jsonify({"msg": "Missing JSON in request"}), 400
    user_id = request.json.get("id", None)
    password = request.json.get("password", None)
    if not user_id:
        return jsonify({"msg": "ID is required"}), 400
    if not password:
        return jsonify({"msg": "Password is required"}), 400
    user = sign_in(user_id, password)
    if not user:
        return jsonify({"msg": "Invalid id or password"}), 401
    access_token = create_access_token(identity=user_id)
    return jsonify(
        {"access_token": access_token, "expires": now_seconds() + access_token_expires}
    ), 200


def check_user_id(user_id):
    if len(user_id) > 15:
        return False
    if not re.match("^[A-Za-z\\d_-]+$", user_id):
        return False
    return True


@app.route("/api/signUp", methods=["POST"])
def _sign_up():
    """
    Signs up a new user
    """
    user_id = request.json.get("id", None)
    password = request.json.get("password", None)
    display_name = request.json.get("display_name", None)
    email = request.json.get("email", None)
    if not user_id:
        return jsonify({"msg": "ID is required"}), 400
    if not check_user_id(user_id):
        return jsonify({"msg": "Invalid ID"}), 400
    if not password:
        return jsonify({"msg": "Password is required"}), 400
    if not is_open_registration:
        invitation_code = request.json.get("invitation_code", None)
        if not invitation_code:
            return jsonify({"msg: Invitation code is required"}), 403
        if not check_invitation_code(invitation_code):
            return jsonify({"msg": "Invalid invitation code"}), 403
        if not claim_invitation_code(invitation_code):
            return jsonify({"msg": "Failed to claim invitation code"}), 500
    if email and not check_email(email):
        return {"msg": f"Email {email} is already taken"}, 409
    successful = sign_up(user_id, password, display_name, email)
    if successful:
        return {"id": user_id}, 201
    else:
        return {"msg": f"ID {user_id} is already taken"}, 409


@app.route("/api/isOpenRegistration", methods=["GET"])
def _is_open_registration():
    return {"is_open_registration": is_open_registration}


@app.route("/api/gitCommit")
def _git_commit():
    return {"git_commit": git_commit}


# RSS routes
@app.route("/rss/<string:user_id>/notifications")
def _rss_notifications(user_id: str):
    token = request.args.get("token", None)
    if not token:
        return f"No RSS token provided", 400
    user = get_user_by_rss_token(token)
    if not user or user.user_id != user_id:
        return f"User with RSS token {token} is not found", 404
    rss_codes = request.args.get("types", None)
    if not rss_codes:
        types = notifying_action_to_rss_code.keys()
    else:
        types = set(
            map(
                lambda rc: rss_code_to_notifying_action[rc],
                filter(lambda rc: rc in rss_code_to_notifying_action, rss_codes),
            )
        )
    xml = get_rss_notifications_xml(user, types, rss_codes)
    return xml, 200, {"Content-Type": "application/atom+xml; charset=utf-8"}


# Media Proxy
@app.route("/p/<path:object_name>")
def _media_proxy(object_name: str):
    s3_client, s3_bucket_name = get_s3_client()

    return Response(
        stream_with_context(
            s3_client.get_object(Bucket=s3_bucket_name, Key=object_name)[
                "Body"
            ].iter_chunks()
        ),
        mimetype="application/octet-stream",
    )


# API routes
errors = {
    "UnauthorizedAccess": {
        "status": 401,
    },
    "BadRequest": {
        "status": 400,
    },
    "NotFound": {
        "status": 404,
    },
    "Conflict": {"status": 409},
    "ExpiredSignatureError": {"status": 401},
}
api = Api(app, errors=errors)

api.add_resource(MyAvatar, "/api/me/avatar")
api.add_resource(MyProfilePic, "/api/me/profilePic/<string:user_profile_pic>")
api.add_resource(MyDisplayName, "/api/me/displayName")
api.add_resource(MyEmail, "/api/me/email")
api.add_resource(MyFollowingCounts, "/api/me/followingCounts")
api.add_resource(MyFollowings, "/api/me/followings")
api.add_resource(MyBlocking, "/api/me/blocking")
api.add_resource(Me, "/api/me")

api.add_resource(Users, "/api/users")
api.add_resource(User, "/api/user/<string:user_id>")
api.add_resource(SearchedUsers, "/api/users/search")

api.add_resource(Profile, "/api/profile/<string:profile_user_id>")
api.add_resource(Home, "/api/home")

api.add_resource(
    NestedComment,
    "/api/posts/<string:post_id>/comment/<string:comment_id>/comment"
    "/<string:nested_comment_id>",
)
api.add_resource(
    NestedComments, "/api/posts/<string:post_id>/comment/<string:comment_id>/comment"
)
api.add_resource(Comment, "/api/posts/<string:post_id>/comment/<string:comment_id>")
api.add_resource(Comments, "/api/posts/<string:post_id>/comment")
api.add_resource(Reactions, "/api/posts/<string:post_id>/reactions")
api.add_resource(Reaction, "/api/posts/<string:post_id>/reaction/<string:reaction_id>")
api.add_resource(Posts, "/api/posts")
api.add_resource(PostMedia, "/api/post/<string:post_id>/media")
api.add_resource(Post, "/api/post/<string:post_id>")
api.add_resource(MediaResource, "/api/media")
api.add_resource(Vote, "/api/post/<string:post_id>/poll/<string:choice_id>")

api.add_resource(Circles, "/api/circles")
api.add_resource(CircleName, "/api/circle/<string:circle_id>/name")
api.add_resource(
    CircleMember, "/api/circle/<string:circle_id>/membership/<string:member_user_id>"
)
api.add_resource(Circle, "/api/circle/<string:circle_id>")

api.add_resource(Following, "/api/following/<string:following_user_id>")
api.add_resource(Blocks, "/api/block/<string:blocking_user_id>")

api.add_resource(NotificationRead, "/api/notification/<string:notification_id>/read")
api.add_resource(NotificationsAllRead, "/api/notifications/read")
api.add_resource(Notifications, "/api/notifications")

api.add_resource(InvitationCodes, "/api/invitationCodes")
api.add_resource(InvitationCode, "/api/invitationCode")

api.add_resource(LinkPreview, "/api/linkPreview")

api.add_resource(ForgetPassword, "/api/forgetPassword")
api.add_resource(ResetPassword, "/api/resetPassword")

api.add_resource(MyRssToken, "/api/rssToken")

api.add_resource(MediaSets, "/api/mediaSets")
api.add_resource(MediaSetName, "/api/mediaSet/<string:media_set_id>/name")
api.add_resource(MediaSetPublic, "/api/mediaSet/<string:media_set_id>/public")
api.add_resource(MediaSetMedia, "/api/mediaSet/<string:media_set_id>/media")
api.add_resource(MediaSet, "/api/mediaSet/<string:media_set_id>")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
