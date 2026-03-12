import os

from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restful import Resource, fields, marshal_with

from pillcity.daos.invitation_code import create_invitation_code, get_invitation_codes

admins = list(map(lambda s: s.strip(), os.getenv("ADMINS", "").split(",")))

invitation_code_fields = {"code": fields.String, "claimed": fields.Boolean}


class InvitationCodes(Resource):
    @jwt_required()
    @marshal_with(invitation_code_fields)
    def get(self):
        user_id = get_jwt_identity()
        if user_id not in admins:
            return {"msg": "Not an admin"}, 403
        return get_invitation_codes()


class InvitationCode(Resource):
    @jwt_required()
    def post(self):
        user_id = get_jwt_identity()
        if user_id not in admins:
            return {"msg": "Not an admin"}, 403
        return create_invitation_code()
