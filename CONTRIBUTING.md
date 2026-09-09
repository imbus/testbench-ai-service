# Contributing

Thank you for considering contributing to TestBench AI Service! We appreciate your help in making this project even better. Please take a moment to read through this guide to understand how you can contribute effectively.

## Development Setup

To get started with development, follow these steps to clone the repository and set up your environment.

**1. Fork the repository**

Start by forking the repository to your own account.

**2.  Clone your forked repository**

After forking, clone your forked version of the repository to your local machine.

```bash
git clone https://github.com/imbus/testbench-ai-service.git
cd testbench-ai-service
```

**3. Set up the virtual environment**

Run the following command:

```bash
python -m venv .venv
```

**4. Activate the virtual environment**

- on macOS/Linux:
    ```bash
    source .venv/bin/activate
    ```
- on Windows:
    ```powershell
    .venv\Scripts\activate
    ```

**5. Install dev environment**

Run the following command:

```bash
pip install -e .[dev]
pre-commit install
```

## Running Tests

If you want to contribute code, it's important to ensure that everything works correctly. You can run the tests to make sure the code passes all the required checks.

**Run the unit tests (pytest):**
```bash
pytest tests/unit
```

## Web Console Frontend

The browser console served at `/admin` is a React + TypeScript app under
`frontend/`. It builds into `testbench_ai_service/static/admin/`, which is
git-ignored, so a fresh checkout has no console until you build it. Node 20+ is
required.

**Install the dependencies:**
```bash
cd frontend
npm install
```

**Run the dev server:**
```bash
npm run dev
```

It serves the console with hot reload and proxies `/admin/api` to a service
running on `http://127.0.0.1:8010`, so start the service separately with
`testbench-ai-service start`.

**Run the frontend tests (Vitest):**
```bash
npm test
```

**Build the console into the package:**
```bash
npm run build
```

Run the build before starting the service if you want to exercise the console
at `/admin` rather than through the dev server. `python build_binary.py` runs
`npm ci && npm run build` for you; pass `--skip-frontend` to package whatever is
already built.

## Code Style & Linting

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting, and [mypy](https://mypy-lang.org/) for static type checking.

**Check linting:**
```bash
ruff check src/
```

**Check types:**
```bash
mypy src/
```

Please ensure `ruff` and `mypy` pass with no errors before opening a pull request.

## Branching & Pull Requests

1. **Create a branch** from `main` with a descriptive name:
   - `feature/<short-description>` for new features
   - `fix/<short-description>` for bug fixes
   - `docs/<short-description>` for documentation changes

2. **Commit** your changes with clear, concise commit messages.

3. **Push** your branch and open a pull request against `main`.

4. Fill in the pull request description, referencing any related issues (e.g. `Closes #42`).

5. Ensure all CI checks pass before requesting a review.

## Reporting Bugs

Please open a [GitHub Issue](https://github.com/imbus/testbench-ai-service/issues) and include:

- **Version** — output of `testbench-ai-service --version`
- **Python version** — output of `python --version`
- **Operating system**
- **Steps to reproduce** the problem (for bugs)
- **Expected vs actual behavior**

## Requesting Features

Open a [GitHub Issue](https://github.com/imbus/testbench-ai-service/issues) and describe:

- The use case you are trying to solve.
- How you imagine the feature working.
- Any alternatives you have considered.