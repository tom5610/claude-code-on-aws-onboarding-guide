
install uv and sync

```
uv sync
```

sample command to create Application Inference Profile

```
uv run main.py admin create-aip --name adrianl-claude-sonnet-3-7 --tags '{"Team": "cloud-engineering", "DeveloperId": "AdrianL"}'
```

to setup at client side

```
uv run main.py client setup --tags '{"Team": "cloud-engineering", "DeveloperId": "AdrianL"}'
```
