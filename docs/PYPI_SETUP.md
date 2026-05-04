# PyPI Trusted Publisher setup

The release workflow at `.github/workflows/release.yml` publishes `cegm-broker` to PyPI via OIDC ("Trusted Publisher"). No API tokens are stored in the repo or in GitHub Actions secrets.

This is a **one-time human setup** on the PyPI side. Until it's done, every `git push origin v*` will build and upload artifacts to GitHub Releases successfully, but the `Publish to PyPI` job will fail with:

```
* invalid-publisher: valid token, but no corresponding publisher (Publisher with matching claims was not found)
```

That's expected — it just means the OIDC handshake succeeded but PyPI doesn't yet have a record telling it to trust this exact `(repo, workflow, environment)` triple.

## One-time setup

1. **Sign in to https://pypi.org** with the `dwgx` account (or whichever account will own the project).

2. Visit **[Publishing → Add a new pending publisher](https://pypi.org/manage/account/publishing/)**.

3. Fill in:

   | Field                  | Value                  |
   |------------------------|------------------------|
   | PyPI Project Name      | `cegm-broker`          |
   | Owner                  | `dwgx`                 |
   | Repository name        | `CEGM`                 |
   | Workflow filename      | `release.yml`          |
   | Environment name       | `pypi`                 |

4. Click **Add**. PyPI will create a pending publisher — the project doesn't exist yet, so the binding is "pending the first push".

5. Re-run the release workflow:

   ```powershell
   gh workflow run release.yml --ref v0.1.0a1
   ```

   Or push a new tag (e.g. `v0.1.0a2`) — any tagged push triggers it.

6. The first successful publish completes the binding. Future tags publish automatically.

## TestPyPI (optional)

The workflow has a TestPyPI job that runs only on manual `workflow_dispatch`. Mirror the steps above against [test.pypi.org](https://test.pypi.org) using environment name `testpypi`. Then:

```powershell
gh workflow run release.yml --ref main -f target=testpypi
```

## Interim install path

While PyPI is being configured, end users can install directly from the GitHub Release wheel:

```powershell
pip install https://github.com/dwgx/CEGM/releases/download/v0.1.0a1/cegm_broker-0.1.0a1-py3-none-any.whl
# or, isolated tool install
uv tool install https://github.com/dwgx/CEGM/releases/download/v0.1.0a1/cegm_broker-0.1.0a1-py3-none-any.whl
```

This works because the release's wheel asset is a public download — no auth needed. Once PyPI is live, the simpler `pip install cegm-broker` / `uv tool install cegm-broker` paths take over.
