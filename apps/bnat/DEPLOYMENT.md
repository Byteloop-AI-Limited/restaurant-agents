# Burger Nation manual deployment

From the workspace root:

```bash
fly deploy . \
  --config apps/bnat/fly.toml \
  --dockerfile Dockerfile \
  --build-arg APP_PACKAGE=bnat-agent \
  --ha=false
```

The app must use the `bnat_*` WABA secret namespace and `BNAT_APP_URL` Ordelo configuration.

To import only the AWS bootstrap credentials from a local environment file,
name the AWS Secrets Manager secret explicitly:

```bash
FLY_AWS_SECRET_NAME=agent-env \
  apps/bnat/fly_deploy_env_secrets.sh
```

The script intentionally has no default secret name.
