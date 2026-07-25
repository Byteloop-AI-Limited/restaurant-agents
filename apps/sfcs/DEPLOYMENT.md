# SFCS manual deployment

From the workspace root:

```bash
fly deploy . \
  --config apps/sfcs/fly.toml \
  --dockerfile Dockerfile \
  --build-arg APP_PACKAGE=sfcs-agent \
  --ha=false
```

The app must use the `sfcs_*` WABA secret namespace and `SFCS_APP_URL` Ordelo configuration.
