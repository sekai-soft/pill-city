# pill-city
A social network reminiscent of Google+ with enhancements


## Prerequisites

0. [Open the project in VSCode using devcontainer](https://code.visualstudio.com/docs/devcontainers/containers#:~:text=Start%20VS%20Code%2C%20run%20the,set%20up%20the%20container%20for.)

1. Prepare environment files

   ```bash
   cp .example.env .env
   cp ./web/.env.development ./web/.env.development.local
   ```

## Run
``` shell
overmind s
```
The API will be running at `localhost:5000`


## Dump dummy data into server
Make sure you have the server running
``` shell
make dev-dump
```
Use ID `kele` and password `1234` to log in


## Run the web UI
See [README for web](./web/README.md)


## Run unit tests
``` shell
make test
```

## Security
Please send security findings to [`admin@ktachibana.party`](mailto:admin@ktachibana.party).
