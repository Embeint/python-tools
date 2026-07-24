# Regenerating the API Client

1. Download the latest API specification from https://api.infuse-iot.com/docs
2. Delete the previous API client: `rm -r ./src/infuse-iot/api_client`
3. Generate API client into the root directory: `openapi-python-client generate --path ./infuse-api.yaml`
4. Move API client to desired directory: `mv infuse-api-client/infuse_api_client/ ./src/infuse_iot/api_client/`
5. Remove extraneous files: `rm -r infuse-api-client`
6. Restore previous `README.md`

Some of these steps can possibly be automated with the `openapi-python-client` `--config` parameter in the future.
