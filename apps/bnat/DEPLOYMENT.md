# Burger Nation manual deployment

From the workspace root:

```bash
scripts/deploy-agent.sh --app bnat
```

Extra arguments after `--app bnat` are passed through to `fly deploy`. The
script runs `fly deploy . --config apps/bnat/fly.toml --build-arg
APP_PACKAGE=bnat-agent --ha=false`. The config builds the root `Dockerfile`
via `dockerfile = "../../Dockerfile"` (paths in `fly.toml` resolve relative
to the config file, not the workspace root).

The app must use the `bnat_*` WABA secret namespace and `BNAT_APP_URL` Ordelo configuration.

To follow the deployed app's runtime logs:

```bash
fly --config apps/bnat/fly.toml logs
```

To import only the AWS bootstrap credentials from a local environment file,
name the AWS Secrets Manager secret explicitly:

```bash
FLY_AWS_SECRET_NAME=agent-env \
  apps/bnat/fly_deploy_env_secrets.sh
```

The script intentionally has no default secret name.
