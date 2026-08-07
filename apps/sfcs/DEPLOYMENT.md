# SFCS manual deployment

From the workspace root:

```bash
scripts/deploy-agent.sh --app sfcs
```

Extra arguments after `--app sfcs` are passed through to `fly deploy`. The
script runs `fly deploy . --config apps/sfcs/fly.toml --build-arg
APP_PACKAGE=sfcs-agent --ha=false`. The config builds the root `Dockerfile`
via `dockerfile = "../../Dockerfile"` (paths in `fly.toml` resolve relative
to the config file, not the workspace root).

The app must use the `sfcs_*` WABA secret namespace and `SFCS_APP_URL` Ordelo configuration.

To follow the deployed app's runtime logs:

```bash
fly --config apps/sfcs/fly.toml logs
```
