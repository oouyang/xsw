# build xsw (api)

```bash
docker compose -f compose.yml -f docker/build.yml up -d xsw --build
```

# build web (frontend)

```bash
docker compose -f compose.yml -f docker/build.yml up -d web --build
```
