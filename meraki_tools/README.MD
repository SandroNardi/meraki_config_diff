## meraki_tools (Reusable Library)

`meraki_tools` is a reusable Python package that wraps Cisco Meraki Dashboard operations and provides PyWebIO helpers for building small apps quickly. It is intended to be maintained as a separate project and consumed by applications (like the example in the repository root).

### Modules
- `meraki_api_utils.py`: `MerakiAPIWrapper` with helpers for API key management, organizations, networks, and parameter checks.
- `meraki_ui.py`: `PyWebIOApp` helpers for UI scaffolding, app setup prompts, nav, logging panel, and style loading.
- `my_logging.py`: simple in-memory logging and a logger factory.

### Install (as a package in other projects)
You can package and publish this folder or install directly from a Git URL. For local development, add the parent project to your venv in editable mode:

```bash
pip install -e .
```

If you split `meraki_tools` to its own repository, you can install it via:

```bash
pip install git+https://<your-host>/<your-user>/meraki_tools@<branch-or-tag>
```

### Usage (quick start)
```python
from meraki_tools.meraki_api_utils import MerakiAPIWrapper

api = MerakiAPIWrapper()
api.setup_application_parameters({"api_key": True, "organization_id": True}, {"organization_id": "<ORG_ID>"})
orgs = api.list_organizations()
```

For PyWebIO scaffolding, see the example app in the repository root (`app.py`) using `PyWebIOApp` from `meraki_ui.py`.

### Keeping this as a separate project
This folder should ideally live in its own repository. You have a few options to consume it here:

1) Subtree (single working tree, history squashed):
```bash
git subtree add --prefix=meraki_tools <repository-url> <branch> --squash
git subtree pull --prefix=meraki_tools <repository-url> <branch> --squash
```

2) Submodule (pinned ref, separate working tree):
```bash
git submodule add <repository-url> meraki_tools
git submodule update --init --recursive
```

3) Package dependency: publish `meraki_tools` and install with pip (preferred for consumers).

Choose the model that best fits your maintenance workflow. For most app consumers, packaging or a Git URL install is simplest. For contributors who iterate on both the app and the library, subtrees or submodules can work well.