# Vendoring

This folder is designed to be copied or zipped as a single unit.

## Portability Rules

- Keep the whole folder together
- Do not replace vendored imports with parent-repo imports
- Keep settings relative
- Avoid machine-specific source paths in code
- Generated exports belong in the global library root, not in the package folder

## Before Shipping

1. Run `python smoke_test.py`
2. Run `python app.py --health`
3. Remove `__pycache__` folders if you do not want them in the archive
4. Zip the folder root, not individual files

## After Unzipping Elsewhere

1. Install Python requirements if needed:

```powershell
pip install -r requirements.txt
```

2. Run the self-test:

```powershell
python smoke_test.py
```

3. Start the MCP server:

```powershell
python mcp_server.py
```
