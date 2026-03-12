# pill-city
A social network reminiscent of Google+ with enhancements

## Prerequisites
Prepare environment files

```bash
cp .example.env .env
cp ./web/.env.development ./web/.env.development.local
```

## Run
``` shell
overmind s
```
The API will be running at `localhost:5000`

## Run the web UI
See [README for web](./web/README.md)

## Run unit tests
``` shell
uv run --dev pytest
```

## Security
Please send security findings to [`admin@ktachibana.party`](mailto:admin@ktachibana.party).
