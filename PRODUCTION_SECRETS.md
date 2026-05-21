# Production Secrets Configuration

This file provides quick-start instructions for configuring RuggyLab OS for production with secure secrets management.

## Quick Start

### Development (Local)

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and set your values
# For development, you can use simple passwords
SECRET_KEY=my-dev-secret-key-at-least-32-chars-long
FIRST_SUPERUSER_PASSWORD=my-dev-admin-password

# Start the application
python -m uvicorn app.main:app
```

### Production (AWS)

```bash
# 1. Create secrets in AWS Secrets Manager
aws secretsmanager create-secret \
  --name ruggylab/prod/secrets \
  --region us-east-1 \
  --secret-string '{
    "APP_SIGNING_KEY": "REPLACE_WITH_32_CHAR_MIN_RANDOM_VALUE",  # pragma: allowlist secret
    "ADMIN_INIT_VALUE": "REPLACE_WITH_32_CHAR_MIN_RANDOM_VALUE"  # pragma: allowlist secret
  }'
# Maps to env vars: APP_SIGNING_KEY → SECRET_KEY, ADMIN_INIT_VALUE → FIRST_SUPERUSER_PASSWORD

# 2. Export environment variables
export SECRET_MANAGER_TYPE=aws
export AWS_REGION=us-east-1
export AWS_SECRET_NAME=ruggylab/prod/secrets

# 3. Start the application
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Production (Azure)

```bash
# 1. Create secrets in Azure Key Vault
az keyvault secret set --vault-name ruggylab-vault \
  --name SECRET-KEY \
  --value "your-secure-random-key-32-chars-min"

# 2. Export environment variables
export SECRET_MANAGER_TYPE=azure
export AZURE_KEYVAULT_URL=https://ruggylab-vault.vault.azure.net/
export AZURE_TENANT_ID=your-tenant-id
export AZURE_CLIENT_ID=your-client-id
export AZURE_CLIENT_SECRET=your-client-secret

# 3. Start the application
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Production (Google Cloud)

```bash
# 1. Create secrets in GCP Secret Manager
echo -n "your-secure-random-key-32-chars-min" | \
  gcloud secrets create SECRET-KEY --data-file=-

# 2. Export environment variables
export SECRET_MANAGER_TYPE=gcp
export GCP_PROJECT_ID=your-project-id
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# 3. Start the application
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Generate Secure Secrets

```bash
# Generate SECRET_KEY (Python)
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate FIRST_SUPERUSER_PASSWORD (OpenSSL)
openssl rand -base64 32
```

## Supported Secret Managers

| Provider | Type | Requires | Production Ready |
|----------|------|----------|------------------|
| Environment Variables | `local` | None | ❌ Dev only |
| AWS Secrets Manager | `aws` | boto3 | ✅ Yes |
| Azure Key Vault | `azure` | azure-identity, azure-keyvault-secrets | ✅ Yes |
| Google Cloud Secret Manager | `gcp` | google-cloud-secret-manager | ✅ Yes |

## Installing Optional Dependencies

```bash
# AWS
pip install boto3

# Azure
pip install azure-identity azure-keyvault-secrets

# Google Cloud
pip install google-cloud-secret-manager

# All providers (for testing/development)
pip install boto3 azure-identity azure-keyvault-secrets google-cloud-secret-manager
```

## Complete Guide

See [docs/SECRETS_MANAGEMENT.md](../docs/SECRETS_MANAGEMENT.md) for comprehensive documentation including:

- Detailed setup instructions for each cloud provider
- IAM/RBAC configuration
- Docker and Kubernetes deployment examples
- Security best practices
- Troubleshooting guide

## Security Checklist

Before deploying to production:

- [ ] Generate secure SECRET_KEY (minimum 32 random characters)
- [ ] Generate secure FIRST_SUPERUSER_PASSWORD (minimum 32 random characters)
- [ ] Store secrets in a cloud secret manager (AWS, Azure, or GCP)
- [ ] Configure IAM/RBAC to restrict access to secrets
- [ ] Enable audit logging for secret access
- [ ] Remove or secure the `.env` file
- [ ] Set `SECRET_MANAGER_TYPE` environment variable
- [ ] Test secret loading before production deployment
- [ ] Set up automated secret rotation policy
- [ ] Monitor for unauthorized secret access attempts

## Environment Variables Reference

### Required for Secrets Manager Integration

| Variable | Required | Values | Example |
|----------|----------|--------|---------|
| `SECRET_MANAGER_TYPE` | No | `local`, `aws`, `azure`, `gcp` | `aws` |

### AWS Secrets Manager

| Variable | Required | Example |
|----------|----------|---------|
| `AWS_REGION` | When using AWS | `us-east-1` |
| `AWS_SECRET_NAME` | When using AWS | `ruggylab/prod/secrets` |
| `AWS_ACCESS_KEY_ID` | Sometimes* | - |
| `AWS_SECRET_ACCESS_KEY` | Sometimes* | - |

*Not needed if using IAM role (EC2, ECS, Lambda, EKS with IRSA)

### Azure Key Vault

| Variable | Required | Example |
|----------|----------|---------|
| `AZURE_KEYVAULT_URL` | Yes | `https://vault-name.vault.azure.net/` |
| `AZURE_TENANT_ID` | Yes | - |
| `AZURE_CLIENT_ID` | Yes | - |
| `AZURE_CLIENT_SECRET` | Yes | - |

### Google Cloud Secret Manager

| Variable | Required | Example |
|----------|----------|---------|
| `GCP_PROJECT_ID` | Yes | `my-project` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Yes | `/path/to/key.json` |

## Questions?

See [docs/SECRETS_MANAGEMENT.md](../docs/SECRETS_MANAGEMENT.md) for detailed documentation.
