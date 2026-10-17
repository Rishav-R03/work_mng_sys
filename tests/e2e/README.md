# End-To-End Tests

End-to-end tests are executed by the CI workflow when both a root `package.json`
and a `test:e2e` npm script exist.

For a browser-based frontend, Playwright is the recommended default:

```json
{
  "scripts": {
    "test:e2e": "playwright test"
  },
  "devDependencies": {
    "@playwright/test": "^1.48.0"
  }
}
```

The CI workflow installs Playwright browsers only when the e2e script is present.
