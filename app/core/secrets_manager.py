"""
Secrets Manager Integration

This module provides a unified interface for managing secrets from cloud
providers (AWS Secrets Manager, Azure Key Vault, Google Cloud Secret Manager).

Usage:
    from app.core.secrets_manager import SecretsManager

    manager = SecretsManager()
    secret_key = manager.get_secret("SECRET_KEY")
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseSecretsManager(ABC):
    """Abstract base class for secrets management providers."""

    @abstractmethod
    def get_secret(self, secret_name: str) -> str:
        """Retrieve a secret value from the provider."""
        pass

    @abstractmethod
    def get_secrets(self, secret_id: str) -> dict[str, str]:
        """Retrieve multiple secrets from a single secret object."""
        pass


class LocalSecretsManager(BaseSecretsManager):
    """Local secrets manager using environment variables."""

    def get_secret(self, secret_name: str) -> str:
        """Get secret from environment variables."""
        value = os.getenv(secret_name)
        if not value:
            raise ValueError(f"Secret '{secret_name}' not found in environment variables")
        return value

    def get_secrets(self, secret_id: str) -> dict[str, str]:
        """This provider doesn't support getting multiple secrets at once."""
        raise NotImplementedError("LocalSecretsManager does not support get_secrets")


class AWSSecretsManager(BaseSecretsManager):
    """AWS Secrets Manager integration."""

    def __init__(self, region: str | None = None) -> None:
        """Initialize AWS Secrets Manager client."""
        try:
            import boto3
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for AWS Secrets Manager. "
                "Install it with: pip install boto3"
            ) from exc

        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.client = boto3.client("secretsmanager", region_name=self.region)
        logger.info("AWS Secrets Manager initialized for region: %s", self.region)

    def get_secret(self, secret_name: str) -> str:
        """Get a single secret value from AWS Secrets Manager."""
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            if "SecretString" in response:
                return str(response["SecretString"])
            else:
                secret_binary = response.get("SecretBinary", b"")
                if isinstance(secret_binary, bytes):
                    return secret_binary.decode("utf-8")
                return str(secret_binary)
        except Exception as exc:
            logger.error("Failed to retrieve secret '%s' from AWS: %s", secret_name, exc)
            raise

    def get_secrets(self, secret_id: str) -> dict[str, str]:
        """Get multiple secrets from a JSON secret in AWS Secrets Manager."""
        try:
            response = self.client.get_secret_value(SecretId=secret_id)
            if "SecretString" in response:
                secrets_dict = json.loads(str(response["SecretString"]))
                return {k: str(v) for k, v in secrets_dict.items()}
            else:
                secrets_dict = json.loads(response["SecretBinary"].decode("utf-8"))
                return {k: str(v) for k, v in secrets_dict.items()}
        except Exception as exc:
            logger.error("Failed to retrieve secrets from AWS: %s", exc)
            raise


class AzureKeyVault(BaseSecretsManager):
    """Azure Key Vault integration."""

    def __init__(
        self,
        vault_url: str | None = None,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        """Initialize Azure Key Vault client."""
        try:
            from azure.identity import ClientSecretCredential
            from azure.keyvault.secrets import SecretClient
        except ImportError as exc:
            raise ImportError(
                "azure-identity and azure-keyvault-secrets are required for Azure Key Vault. "
                "Install them with: pip install azure-identity azure-keyvault-secrets"
            ) from exc

        self.vault_url = vault_url or os.getenv("AZURE_KEYVAULT_URL")
        if not self.vault_url:
            raise ValueError("AZURE_KEYVAULT_URL environment variable or vault_url parameter required")

        tenant_id = tenant_id or os.getenv("AZURE_TENANT_ID")
        client_id = client_id or os.getenv("AZURE_CLIENT_ID")
        client_secret_value = client_secret or os.getenv("AZURE_CLIENT_SECRET")

        if not all([tenant_id, client_id, client_secret_value]):
            raise ValueError("Azure credentials (tenant_id, client_id, client_secret) are required")

        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret_value,
        )
        self.client = SecretClient(vault_url=self.vault_url, credential=credential)
        logger.info("Azure Key Vault initialized for: %s", self.vault_url)

    def get_secret(self, secret_name: str) -> str:
        """Get a single secret from Azure Key Vault."""
        try:
            secret = self.client.get_secret(secret_name)
            return str(secret.value)
        except Exception as exc:
            logger.error("Failed to retrieve secret '%s' from Azure Key Vault: %s", secret_name, exc)
            raise

    def get_secrets(self, secret_id: str) -> dict[str, str]:
        """Get multiple secrets from a single secret in Azure Key Vault (assumes JSON format)."""
        try:
            secret = self.client.get_secret(secret_id)
            secrets_dict = json.loads(str(secret.value))
            return {k: str(v) for k, v in secrets_dict.items()}
        except Exception as exc:
            logger.error("Failed to retrieve secrets from Azure Key Vault: %s", exc)
            raise


class GoogleCloudSecretManager(BaseSecretsManager):
    """Google Cloud Secret Manager integration."""

    def __init__(self, project_id: str | None = None) -> None:
        """Initialize Google Cloud Secret Manager client."""
        try:
            from google.cloud import secretmanager
        except ImportError as exc:
            raise ImportError(
                "google-cloud-secret-manager is required for GCP Secret Manager. "
                "Install it with: pip install google-cloud-secret-manager"
            ) from exc

        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        if not self.project_id:
            raise ValueError("GCP_PROJECT_ID environment variable or project_id parameter required")

        self.client = secretmanager.SecretManagerServiceClient()
        logger.info("Google Cloud Secret Manager initialized for project: %s", self.project_id)

    def get_secret(self, secret_name: str) -> str:
        """Get a secret from Google Cloud Secret Manager."""
        try:
            name = f"projects/{self.project_id}/secrets/{secret_name}/versions/latest"
            response = self.client.access_secret_version(request={"name": name})
            return str(response.payload.data.decode("UTF-8"))
        except Exception as exc:
            logger.error("Failed to retrieve secret '%s' from GCP: %s", secret_name, exc)
            raise

    def get_secrets(self, secret_id: str) -> dict[str, str]:
        """Get multiple secrets from a JSON secret in GCP Secret Manager."""
        try:
            name = f"projects/{self.project_id}/secrets/{secret_id}/versions/latest"
            response = self.client.access_secret_version(request={"name": name})
            secrets_dict = json.loads(response.payload.data.decode("UTF-8"))
            return {k: str(v) for k, v in secrets_dict.items()}
        except Exception as exc:
            logger.error("Failed to retrieve secrets from GCP: %s", exc)
            raise


class SecretsManager:
    """Factory class for creating and managing secrets from various providers."""

    _instance: BaseSecretsManager | None = None

    @classmethod
    def initialize(cls, manager_type: str | None = None) -> None:
        """Initialize the secrets manager based on configuration."""
        manager_type = manager_type or os.getenv("SECRET_MANAGER_TYPE", "local")

        if manager_type == "aws":
            cls._instance = AWSSecretsManager(region=os.getenv("AWS_REGION"))
        elif manager_type == "azure":
            cls._instance = AzureKeyVault()
        elif manager_type == "gcp":
            cls._instance = GoogleCloudSecretManager()
        elif manager_type == "local":
            cls._instance = LocalSecretsManager()
        else:
            raise ValueError(f"Unknown secret manager type: {manager_type}")

        logger.info("Secrets manager initialized: %s", manager_type)

    @classmethod
    def get_instance(cls) -> BaseSecretsManager:
        """Get the initialized secrets manager instance."""
        if cls._instance is None:
            cls.initialize()
        if cls._instance is None:
            raise RuntimeError("Failed to initialize secrets manager")
        return cls._instance

    @classmethod
    def get_secret(cls, secret_name: str) -> str:
        """Get a secret from the configured provider."""
        return cls.get_instance().get_secret(secret_name)

    @classmethod
    def get_secrets(cls, secret_id: str) -> dict[str, str]:
        """Get multiple secrets from the configured provider."""
        return cls.get_instance().get_secrets(secret_id)


def load_secrets_from_manager(
    secret_manager_type: str | None = None,
    secret_id: str | None = None,
) -> dict[str, Any]:
    """
    Load all secrets from a cloud provider's secret object.

    Args:
        secret_manager_type: Type of secret manager (aws, azure, gcp, local)
        secret_id: ID/name of the secret object containing all secrets

    Returns:
        Dictionary of secrets loaded from the provider
    """
    if not secret_manager_type or not secret_id:
        return {}

    try:
        SecretsManager.initialize(secret_manager_type)
        return SecretsManager.get_secrets(secret_id)
    except Exception as exc:
        logger.error("Failed to load secrets from cloud manager: %s", exc)
        return {}
