# Frontend Tests

Frontend tests are executed by the CI workflow when a root `package.json` exists.

Recommended scripts:

```json
{
  "scripts": {
    "lint": "eslint .",
    "test": "vitest run",
    "build": "vite build",
    "test:e2e": "playwright test"
  }
}
```

The workflow detects these scripts before running them, so repositories without a
frontend package continue to pass the backend checks.
