from pydantic import BaseModel


class Principal(BaseModel):
    """The authenticated caller behind a request.

    Holds the verified claims plus the original token, so downstream code can
    both trust who is calling (subject/claims) and forward the token to auth's
    on-behalf-of exchange (token).
    """

    subject: str
    token: str
    claims: dict
