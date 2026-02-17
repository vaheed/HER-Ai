# Folder Reference: .github/workflows

## Purpose

CI/CD automation for tests, image builds, and docs deployment.

## Files

- `.github/workflows/ci.yml`

## Pipeline Summary

1. Test job (`pytest -q`)
2. Multi-image build/push to GHCR (`her-bot`, `her-dashboard`, `her-sandbox`)
3. MkDocs build and GitHub Pages deployment on `main`

## Validation

Check workflow runs in GitHub Actions and verify published images/docs artifacts after successful pipelines.
