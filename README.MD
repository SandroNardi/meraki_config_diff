## PyWebIO Framework Example for Meraki

This repository is a minimal example that shows how to build a PyWebIO app on top of the reusable `meraki_tools` library. The `meraki_tools` folder is its own standalone project (maintained separately) and is included here for convenience to demonstrate how to extend and use it in an application.

### What you get
- A simple PyWebIO web app (`app.py`) that starts a local server.
- A UI layer (`project_ui.py`) wired to business logic (`project_logic.py`).
- The reusable `meraki_tools` package for Meraki Dashboard interactions and UI helpers.

### Prerequisites
- Python 3.10+
- A Cisco Meraki Dashboard API key with appropriate permissions

### Installation
1. Create and activate a virtual environment (recommended).
2. Install dependencies:
   
   ```bash
   pip install -r requirements.txt
   ```

### Configuration
Set your Meraki API key as an environment variable before running:

```bash
# Windows PowerShell
$env:MK_CSM_KEY = "<YOUR_API_KEY>"

# macOS/Linux bash
export MK_CSM_KEY="<YOUR_API_KEY>"
```

Optionally, you can pre-fill other parameters in `app.py` via `app_setup_param`.

### Run the app
```bash
python app.py
```
The server starts on `http://localhost:8080` by default.

### Project structure (high level)
- `app.py`: boots the PyWebIO server and app
- `project_ui.py`: user interface flow (menus, prompts)
- `project_logic.py`: example business logic using Meraki Dashboard client
- `meraki_tools/`: reusable library (maintained as a separate project)

### About meraki_tools as a separate project
`meraki_tools` is designed to be versioned and maintained independently (e.g., a separate Git repository). In this example, it is embedded under the same workspace so you can see how to import and extend it. For long-term maintenance, consider including it as a Git subtree, submodule, or a pip-installable package from its own repo.

### Extending this example
1. Add new features in `project_logic.py` that call methods from `meraki_tools.meraki_api_utils.MerakiAPIWrapper`.
2. Expose new actions in `project_ui.py` and wire buttons to your logic.
3. Keep generic helpers inside `meraki_tools` so they can be reused across projects.

### License
See `LICENSE` for details.
