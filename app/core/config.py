import logging
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _load_secret_from_manager(secret_name: str, default: str) -> str:
    """
    Load a secret from the configured secrets manager.

    First tries to load from environment variables, then from cloud provider
    if SECRET_MANAGER_TYPE is configured.
    """
    # Try environment variable first
    env_value = os.getenv(secret_name)
    if env_value:
        return env_value

    # Try cloud secrets manager if configured
    manager_type = os.getenv("SECRET_MANAGER_TYPE")
    if manager_type and manager_type != "local":
        try:
            from app.core.secrets_manager import SecretsManager

            SecretsManager.initialize(manager_type)
            return SecretsManager.get_secret(secret_name)
        except Exception as exc:
            logger.warning(
                "Failed to load secret '%s' from cloud manager: %s. Using default.",
                secret_name,
                exc,
            )

    return default


DEFAULT_SECRET_KEY = _load_secret_from_manager("SECRET_KEY", "")
DEFAULT_FIRST_SUPERUSER_PASSWORD = _load_secret_from_manager("FIRST_SUPERUSER_PASSWORD", "")


class Settings(BaseSettings):
    APP_NAME: str = "RuggyLab OS"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = "sqlite:///./ruggylab_os.db"
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    FIRST_SUPERUSER: str = "admin"
    FIRST_SUPERUSER_PASSWORD: str = DEFAULT_FIRST_SUPERUSER_PASSWORD
    FIRST_SUPERUSER_FULL_NAME: str = "RuggyLab Administrator"
    # Toutes les interfaces d'équipement sont fail-closed par défaut. Leur
    # activation requiert un profil identifié, un protocole confirmé et une
    # qualification documentée.
    ENABLE_DH36_LISTENER: bool = False
    ENABLE_DH36_INGESTION: bool = False
    # ── Rôle du process (séparation web / tâches de fond) ───────────────────────
    # Détermine quelles tâches de fond ce process exécute, afin d'éviter les
    # duplications quand plusieurs workers web tournent (listener DH36 qui bind un
    # port, purge des jetons planifiée…). Valeurs :
    #   "all"              : tout dans un seul process (dev / mono-poste) [défaut]
    #   "web"              : API/UI + fan-out WebSocket, AUCUN singleton
    #   "scheduler"        : tâches planifiées (purge des jetons)
    #   "analyzer-gateway" : listener DH36 (un seul exemplaire — bind un port)
    # En prod multi-worker : app=web + un service scheduler + un service
    # analyzer-gateway (même image, commandes différentes). Cf. docker-compose.yml.
    PROCESS_ROLE: str = "all"
    # Fichier de battement du process scheduler : réécrit toutes les ~30 s, il
    # permet au healthcheck compose de sonder la fraîcheur (cf. app/scheduler.py).
    # /tmp est le seul emplacement toujours inscriptible par l'utilisateur non-root
    # du conteneur ; simple marqueur de vivacité, aucune donnée sensible.
    SCHEDULER_HEARTBEAT_FILE: str = "/tmp/ruggylab_scheduler.heartbeat"  # noqa: S108  # nosec B108
    ANALYZER_GATEWAY_HEARTBEAT_FILE: str = "/tmp/ruggylab_analyzer_gateway.heartbeat"  # noqa: S108  # nosec B108
    # Fichier de log applicatif. None (défaut) = stdout uniquement — indispensable
    # en conteneur : l'utilisateur non-root ne peut pas créer /app/logs, et Docker
    # assure de toute façon collecte et rotation. Sur un poste nu (Windows), mettre
    # LOG_FILE=logs/app.log dans .env pour retrouver le fichier local.
    LOG_FILE: str | None = None
    TESTING: bool = False
    # Validation non bloquante par défaut : un effectif réduit ne permet pas une
    # double validation quotidienne. La publication / le compte-rendu reste
    # possible sans validation (document « provisoire »), validée a posteriori.
    # Mettre à True pour imposer la validation avant publication (ISO 15189 strict).
    REQUIRE_VALIDATION_FOR_RELEASE: bool = False
    DH36_LISTENER_HOST: str = "127.0.0.1"  # Changed from 0.0.0.0 for security
    DH36_LISTENER_PORT: int = 5001
    BASE_DATA_DIR: str = "data"
    MICROSCOPY_STORAGE_DIR: str = "data/microscopy"
    MALARIA_MODEL_PATH: str = "models/malaria_mobilenetv2"
    MALARIA_ANALYSIS_AUTORUN: bool = False

    # Rate limiting and abuse protection
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_BLOCK_SECONDS: int = 60
    LOGIN_RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT_REQUESTS: int = 10
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300
    LOGIN_RATE_LIMIT_BLOCK_SECONDS: int = 300
    REDIS_URL: str | None = None
    METRICS_SERVER_ENABLED: bool = True

    # HTTP security header settings
    SECURITY_HEADERS_ENABLED: bool = True
    HSTS_ENABLED: bool = True
    HSTS_MAX_AGE_SECONDS: int = 63_072_000
    HSTS_INCLUDE_SUBDOMAINS: bool = True
    HSTS_PRELOAD: bool = True
    REFERRER_POLICY: str = "no-referrer"
    FRAME_OPTIONS: str = "DENY"
    PERMISSIONS_POLICY: str = "geolocation=(), microphone=(), camera=()"

    # CORS settings
    CORS_ENABLED: bool = True
    CORS_ALLOW_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: list[str] = ["Authorization", "Content-Type", "X-Request-ID"]

    # User quota settings
    USER_QUOTA_ENABLED: bool = True
    USER_QUOTA_REQUESTS: int = 1000
    USER_QUOTA_WINDOW_SECONDS: int = 3600  # 1 hour
    USER_QUOTA_BLOCK_SECONDS: int = 3600

    # Caching settings
    CACHE_ENABLED: bool = True
    CACHE_DEFAULT_TTL_SECONDS: int = 300  # 5 minutes
    CACHE_BACKEND: str = "memory"  # "memory" or "redis"

    # Compression settings
    COMPRESSION_ENABLED: bool = True
    COMPRESSION_MIN_SIZE_BYTES: int = 500

    # Pagination settings
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Notifications
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_FROM: str = "alertes@ruggylab.local"
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_STARTTLS: bool = False
    NOTIFICATION_WEBHOOK_TIMEOUT_SECONDS: int = 10
    REPORT_DELIVERY_OUTPUT_DIR: str = "data/report_delivery/pdf"
    REPORT_DELIVERY_FHIR_DIR: str = "data/report_delivery/fhir"
    REPORT_DELIVERY_EMAIL_TO: str | None = None

    # Analyzer middleware ingestion (ASTM/automates -> RuggyLab REST).
    # ANALYZER_API_KEY must be set before enabling the /analyzer/results endpoint.
    # ANALYZER_ALLOWED_IPS can stay empty when network controls are handled by firewall/VLAN.
    ANALYZER_API_KEY: str = ""
    ANALYZER_ALLOWED_IPS: list[str] = []
    ANALYZER_HMAC_SECRET: str | None = None
    ANALYZER_SIGNATURE_MAX_SKEW_SECONDS: int = 300

    # Listener TCP « aveugle » (capture brute des trames automates -> Redis).
    # Filet de sécurité avant parseur (Dymind DH36, manuel d'interfaçage en
    # attente) : les trames sont archivées telles quelles dans une liste Redis.
    # Cf. app/services/interfacing/raw_tcp_listener.py. Requiert REDIS_URL.
    ANALYZER_RAW_LISTENER_ENABLED: bool = False
    ANALYZER_RAW_LISTENER_HOST: str = "127.0.0.1"  # jamais 0.0.0.0 par défaut (cf. DH36)
    ANALYZER_RAW_LISTENER_PORT: int = 9000
    ANALYZER_RAW_ACK_MODE: str = "ack"  # "ack" (ACK 0x06) | "silent" | "close"
    # Un listener par automate (routage par port, cf. services/analyzers/registry).
    # Hématologie = Dymind DH36, Biochimie = Dymind, Immuno = Anbio Bioscann.
    ANALYZER_HEMATOLOGY_ENABLED: bool = False
    ANALYZER_HEMATOLOGY_PORT: int = 9000
    ANALYZER_BIOCHEMISTRY_ENABLED: bool = False
    ANALYZER_BIOCHEMISTRY_PORT: int = 9001
    ANALYZER_IMMUNO_ENABLED: bool = False
    ANALYZER_IMMUNO_PORT: int = 9002
    ANALYZER_RAW_QUEUE_KEY: str = "raw_analyzer_frames"
    ANALYZER_RAW_QUEUE_MAXLEN: int = 100_000
    ANALYZER_RAW_MAX_FRAME_BYTES: int = 1_048_576
    ANALYZER_RAW_IDLE_TIMEOUT_SECONDS: float = 300.0

    # Trusted reverse-proxy IPs.
    # X-Forwarded-For is only trusted when the direct client IP is in this list.
    # Example: ["127.0.0.1", "10.0.0.1"]
    # Leave empty (default) to never trust X-Forwarded-For (safest for direct exposure).
    TRUSTED_PROXY_IPS: list[str] = []

    # ONMCI — Ordre National des Médecins de Côte d'Ivoire
    ONMCI_SECRET_KEY: str = "change-me-use-a-32-char-secret-key"  # noqa: S105
    ONMCI_API_URL: str | None = None  # None = vérification locale seulement
    ONMCI_TIMEOUT_SECONDS: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def runs_web(self) -> bool:
        """Ce process sert l'API/UI et le fan-out WebSocket."""
        return self.PROCESS_ROLE in ("web", "all")

    @property
    def runs_scheduler(self) -> bool:
        """Ce process exécute les tâches planifiées (purge des jetons…)."""
        return self.PROCESS_ROLE in ("scheduler", "all")

    @property
    def runs_analyzer_gateway(self) -> bool:
        """Ce process exécute le listener d'automates DH36 (exemplaire unique)."""
        return self.PROCESS_ROLE in ("analyzer-gateway", "all")

    @property
    def has_default_secret_key(self) -> bool:
        return self.SECRET_KEY == DEFAULT_SECRET_KEY

    @property
    def has_default_superuser_password(self) -> bool:
        return self.FIRST_SUPERUSER_PASSWORD == DEFAULT_FIRST_SUPERUSER_PASSWORD

    @property
    def requires_security_hardening(self) -> bool:
        weak_secret = len(self.SECRET_KEY) < 32 or "change_me" in self.SECRET_KEY.lower()
        weak_admin_password = (
            len(self.FIRST_SUPERUSER_PASSWORD) < 16
            or "change_me" in self.FIRST_SUPERUSER_PASSWORD.lower()
        )
        return weak_secret or weak_admin_password


settings = Settings()
