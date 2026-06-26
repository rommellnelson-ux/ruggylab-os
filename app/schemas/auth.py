from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    # Optionnel : un client qui ne conserve que le jeton d'accès peut tout de
    # même se déconnecter (révocation du jeton d'accès via l'en-tête Authorization).
    refresh_token: str | None = None
