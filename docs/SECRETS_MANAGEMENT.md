# Secrets Management Guide

This guide explains how to securely manage sensitive configuration values (like API keys, passwords, and database credentials) in RuggyLab OS for different environments.

## Overview

RuggyLab OS supports multiple secret management approaches:

1. **Local Environment Variables** (Development only)
2. **AWS Secrets Manager** (Recommended for AWS deployments)
3. **Azure Key Vault** (Recommended for Azure deployments)
4. **Google Cloud Secret Manager** (Recommended for GCP deployments)

## Development Environment

For local development, use environment variables in a `.env` file:

```bash
# Copy the example file
cp .env.example .env

# Edit .env and set your development secrets
nano .env
```

**Important**: Never commit the `.env` file to version control. It's already in `.gitignore`.

## Production Deployment

For production, **never** store secrets in `.env` files or hardcode them. Use a cloud secret management service.

### AWS Secrets Manager

#### 1. Create a Secret in AWS

```bash
aws secretsmanager create-secret \
  --name ruggylab/prod/secrets \
  --region us-east-1 \
  --secret-string '{
    "SECRET_KEY": "your-generated-secret-key-here",
    "FIRST_SUPERUSER_PASSWORD": "your-strong-password-here",
    "DATABASE_URL": "postgresql://user:password@host:5432/ruggylab"
  }'
```

#### 2. Configure IAM Permissions

Create an IAM policy for your application:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:ruggylab/*"
    }
  ]
}
```

#### 3. Deploy with AWS Credentials

```bash
# Set environment variables for AWS
export SECRET_MANAGER_TYPE=aws
export AWS_REGION=us-east-1
export AWS_SECRET_NAME=ruggylab/prod/secrets
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key

# Or use IAM role if running on EC2/ECS
# The SDK will automatically use the attached role

# Start the application
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### 4. Install AWS Dependencies

```bash
pip install boto3
```

### Azure Key Vault

#### 1. Create a Key Vault

```bash
az keyvault create \
  --resource-group myResourceGroup \
  --name ruggylab-vault \
  --location eastus
```

#### 2. Add Secrets

```bash
az keyvault secret set \
  --vault-name ruggylab-vault \
  --name SECRET-KEY \
  --value "your-generated-secret-key-here"

az keyvault secret set \
  --vault-name ruggylab-vault \
  --name FIRST-SUPERUSER-PASSWORD \
  --value "your-strong-password-here"

az keyvault secret set \
  --vault-name ruggylab-vault \
  --name DATABASE-URL \
  --value "postgresql://user:password@host:5432/ruggylab"
```

#### 3. Create Service Principal

```bash
az ad sp create-for-rbac \
  --name ruggylab-app \
  --role Reader \
  --scopes /subscriptions/{subscription-id}/resourceGroups/{resource-group}/providers/Microsoft.KeyVault/vaults/ruggylab-vault
```

#### 4. Deploy with Azure Credentials

```bash
# Set environment variables
export SECRET_MANAGER_TYPE=azure
export AZURE_KEYVAULT_URL=https://ruggylab-vault.vault.azure.net/
export AZURE_TENANT_ID=your-tenant-id
export AZURE_CLIENT_ID=your-client-id
export AZURE_CLIENT_SECRET=your-client-secret

# Start the application
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### 5. Install Azure Dependencies

```bash
pip install azure-identity azure-keyvault-secrets
```

### Google Cloud Secret Manager

#### 1. Create Project and Enable API

```bash
gcloud projects create ruggylab-prod
gcloud services enable secretmanager.googleapis.com --project=ruggylab-prod
```

#### 2. Create Secrets

```bash
echo -n "your-generated-secret-key-here" | \
  gcloud secrets create SECRET-KEY \
  --data-file=- \
  --project=ruggylab-prod

echo -n "your-strong-password-here" | \
  gcloud secrets create FIRST-SUPERUSER-PASSWORD \
  --data-file=- \
  --project=ruggylab-prod

echo -n "postgresql://user:password@host:5432/ruggylab" | \
  gcloud secrets create DATABASE-URL \
  --data-file=- \
  --project=ruggylab-prod
```

#### 3. Create Service Account

```bash
gcloud iam service-accounts create ruggylab-app \
  --project=ruggylab-prod

# Grant Secret Accessor role
gcloud projects add-iam-policy-binding ruggylab-prod \
  --member=serviceAccount:ruggylab-app@ruggylab-prod.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

#### 4. Deploy with GCP Credentials

```bash
# Create and download service account key
gcloud iam service-accounts keys create key.json \
  --iam-account=ruggylab-app@ruggylab-prod.iam.gserviceaccount.com \
  --project=ruggylab-prod

# Set environment variables
export SECRET_MANAGER_TYPE=gcp
export GCP_PROJECT_ID=ruggylab-prod
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json

# Start the application
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### 5. Install GCP Dependencies

```bash
pip install google-cloud-secret-manager
```

## Generating Secure Secrets

### Generate SECRET_KEY

```bash
# Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# OpenSSL
openssl rand -base64 32
```

### Generate Strong Passwords

```bash
# Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Using openssl
openssl rand -base64 24
```

## Docker Deployment

### With AWS Secrets Manager

```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir boto3

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# Run with AWS credentials
docker run \
  -e SECRET_MANAGER_TYPE=aws \
  -e AWS_REGION=us-east-1 \
  -e AWS_SECRET_NAME=ruggylab/prod/secrets \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  -p 8000:8000 \
  ruggylab-os:latest
```

### With Docker Secrets (Docker Swarm)

```bash
# Create secrets
echo "your-secret-key" | docker secret create SECRET_KEY -
echo "your-password" | docker secret create FIRST_SUPERUSER_PASSWORD -

# Deploy with docker-compose
docker service create \
  --secret SECRET_KEY \
  --secret FIRST_SUPERUSER_PASSWORD \
  -e "SECRET_KEY_FILE=/run/secrets/SECRET_KEY" \
  -e "FIRST_SUPERUSER_PASSWORD_FILE=/run/secrets/FIRST_SUPERUSER_PASSWORD" \
  -p 8000:8000 \
  ruggylab-os:latest
```

### Update config.py to read from secret files:

```python
def _load_secret_from_file(secret_name: str, default: str) -> str:
    """Load secret from Docker/Kubernetes secret file."""
    file_path = f"/run/secrets/{secret_name}"
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return f.read().strip()
    return default
```

## Kubernetes Deployment

### Using Kubernetes Secrets

```bash
# Create namespace
kubectl create namespace ruggylab

# Create secrets
kubectl create secret generic ruggylab-secrets \
  --from-literal=SECRET_KEY="your-generated-key" \
  --from-literal=FIRST_SUPERUSER_PASSWORD="your-password" \
  -n ruggylab

# Or from files
kubectl create secret generic ruggylab-secrets \
  --from-file=SECRET_KEY \
  --from-file=FIRST_SUPERUSER_PASSWORD \
  -n ruggylab
```

### Kubernetes Deployment YAML

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ruggylab-api
  namespace: ruggylab
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ruggylab-api
  template:
    metadata:
      labels:
        app: ruggylab-api
    spec:
      containers:
      - name: api
        image: ruggylab-os:latest
        ports:
        - containerPort: 8000
        env:
        - name: SECRET_MANAGER_TYPE
          value: "local"
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: ruggylab-secrets
              key: SECRET_KEY
        - name: FIRST_SUPERUSER_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ruggylab-secrets
              key: FIRST_SUPERUSER_PASSWORD
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: ruggylab-secrets
              key: DATABASE_URL
        livenessProbe:
          httpGet:
            path: /
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

### With AWS Secrets Manager via IRSA (IAM Roles for Service Accounts)

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: ruggylab-sa
  namespace: ruggylab
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT_ID:role/ruggylab-role

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ruggylab-api
  namespace: ruggylab
spec:
  template:
    spec:
      serviceAccountName: ruggylab-sa
      containers:
      - name: api
        image: ruggylab-os:latest
        env:
        - name: SECRET_MANAGER_TYPE
          value: "aws"
        - name: AWS_REGION
          value: "us-east-1"
        - name: AWS_SECRET_NAME
          value: "ruggylab/prod/secrets"
```

## Security Best Practices

1. **Never commit secrets to version control**
   - Use `.gitignore` to exclude `.env` files
   - Review git history for accidental commits

2. **Use strong secrets**
   - Minimum 32 characters for API keys
   - Minimum 16 characters for passwords
   - Use random generation, not predictable patterns

3. **Rotate secrets regularly**
   - Set up automated rotation (AWS, Azure, GCP support this)
   - Update dependent systems during rotation
   - Monitor access logs

4. **Use appropriate access controls**
   - Use IAM roles and policies
   - Limit secret access to necessary services
   - Enable audit logging

5. **Monitor secret usage**
   - Enable CloudTrail (AWS), Activity Logs (Azure), Cloud Audit Logs (GCP)
   - Alert on unauthorized access
   - Review access patterns

6. **Use separate secrets per environment**
   - Development: local `.env` file
   - Staging: cloud secret manager with limited access
   - Production: cloud secret manager with strict access controls

## Troubleshooting

### "Secret not found" errors

```bash
# AWS: Verify secret exists
aws secretsmanager get-secret-value --secret-id ruggylab/prod/secrets

# Azure: Verify access
az keyvault secret list --vault-name ruggylab-vault

# GCP: Verify access
gcloud secrets list --project=ruggylab-prod
```

### Permission denied errors

```bash
# AWS: Check IAM policy
aws iam get-role-policy --role-name ruggylab-role --policy-name ruggylab-policy

# Azure: Check role assignment
az role assignment list --scope /subscriptions/{id}/resourceGroups/{rg}/providers/Microsoft.KeyVault/vaults/{vault}

# GCP: Check IAM binding
gcloud projects get-iam-policy ruggylab-prod --flatten="bindings[].members" --filter="bindings.role:roles/secretmanager.secretAccessor"
```

## Reference

- [AWS Secrets Manager Documentation](https://docs.aws.amazon.com/secretsmanager/)
- [Azure Key Vault Documentation](https://learn.microsoft.com/en-us/azure/key-vault/)
- [Google Cloud Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
